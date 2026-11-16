"""Llamadas de texto y de JSON estructurado a distintos proveedores de LLM.

Proveedores admitidos:

- ``anthropic``: Claude, con el SDK oficial ``anthropic`` (predeterminado).
- ``openai``: OpenAI, con el SDK ``openai`` (Chat Completions).
- ``gemini``: Google Gemini, con el SDK ``google-genai``.
- ``compatible``: cualquier endpoint compatible con la API de OpenAI (Ollama,
  OpenRouter, Mistral, Groq, vLLM, LM Studio…), indicando su URL base.

Los SDK de OpenAI y de Google se importan sólo cuando se usan, así que no hace
falta instalarlos si se trabaja únicamente con Claude.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

import anthropic

EFFORTS = ["low", "medium", "high", "xhigh", "max"]


@dataclass(frozen=True)
class Provider:
    id: str
    label: str
    # Modelos sugeridos en la interfaz (se puede escribir cualquier otro). El
    # primero es el predeterminado.
    models: list[str]
    # Variables de entorno de las que se lee la API key, por orden.
    env_keys: list[str] = field(default_factory=list)
    # Si el proveedor tiene un ajuste equivalente al esfuerzo de razonamiento.
    supports_effort: bool = True
    # Si hace falta indicar la URL base del endpoint.
    needs_base_url: bool = False
    # Si la API key es obligatoria (los servidores locales no la piden).
    key_required: bool = True
    # Nombre corto para etiquetas («API key de …»).
    short: str = ""


PROVIDERS: dict[str, Provider] = {
    p.id: p
    for p in [
        Provider(
            "anthropic",
            "Anthropic (Claude)",
            ["claude-opus-5-5", "claude-fable-5-2", "claude-sonnet-5-5", "claude-haiku-5-5"],
            ["ANTHROPIC_API_KEY"],
            short="Anthropic",
        ),
        Provider(
            "openai",
            "OpenAI",
            ["gpt-6.1-sol", "gpt-6-astra", "gpt-6.1-terra", "gpt-6-luna"],
            ["OPENAI_API_KEY"],
            short="OpenAI",
        ),
        Provider(
            "gemini",
            "Google Gemini",
            ["gemini-4-argon", "gemini-3.1-pro-preview", "gemini-3.8-flash", "gemini-3.5-flash-lite"],
            ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
            short="Gemini",
        ),
        Provider(
            "compatible",
            "Compatible con OpenAI (Ollama, OpenRouter, Mistral…)",
            ["llama3.3", "qwen3", "mistral-large-latest"],
            ["OPENAI_COMPATIBLE_API_KEY"],
            supports_effort=False,
            needs_base_url=True,
            key_required=False,
            short="endpoint compatible",
        ),
    ]
}

DEFAULT_PROVIDER = "anthropic"
DEFAULT_BASE_URL = "http://localhost:11434/v1"  # Ollama

# Compatibilidad con código que importaba estas constantes.
MODELS = PROVIDERS["anthropic"].models
DEFAULT_MODEL = MODELS[0]

# Modelos de Claude que aceptan el parámetro ``fallbacks`` en el servidor: si
# el clasificador de seguridad rechaza la petición, la API la reintenta con
# otro modelo dentro de la misma llamada.
_FALLBACK_MODELS = {"claude-opus-5-5", "claude-fable-5-2", "claude-sonnet-5-5"}
_FALLBACK_BETA = "server-side-fallback-2026-07-01"
_MAX_TOKENS = 16000


class LLMError(RuntimeError):
    """Error comprensible para mostrar en la interfaz."""


def extract_json(raw: str) -> dict:
    """Interpreta la salida del modelo como un objeto JSON.

    Tolera vallas de código (```json … ```) y texto alrededor del objeto, que
    aparecen con modelos o endpoints sin salida estructurada estricta.
    """
    text = raw.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise LLMError("El modelo devolvió un JSON no válido.") from None
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise LLMError("El modelo devolvió un JSON no válido.") from exc
    if not isinstance(data, dict):
        raise LLMError("El modelo devolvió un JSON no válido (se esperaba un objeto).")
    return data


def _schema_instructions(schema: dict) -> str:
    return (
        "\n\nResponde únicamente con un objeto JSON válido, sin texto adicional ni "
        "vallas de código, que cumpla este JSON Schema:\n" + json.dumps(schema, ensure_ascii=False)
    )


class LLM:
    """Hace llamadas de texto y de JSON estructurado a un modelo de un proveedor."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        client: Any | None = None,
        api_key: str | None = None,
        use_fallbacks: bool = True,
        provider: str = DEFAULT_PROVIDER,
        base_url: str | None = None,
    ) -> None:
        if provider not in PROVIDERS:
            raise LLMError(f"Proveedor desconocido: «{provider}».")
        self.provider = provider
        self.model = model.strip()
        if not self.model:
            raise LLMError("Indica un modelo.")
        self.use_fallbacks = use_fallbacks
        self.base_url = (base_url or "").strip() or None
        self.client = client or self._make_client(api_key or None)

    # --- Clientes -----------------------------------------------------------

    def _make_client(self, api_key: str | None) -> Any:
        if self.provider == "anthropic":
            try:
                return anthropic.Anthropic(api_key=api_key)
            except anthropic.AnthropicError as exc:
                raise LLMError("Falta la API key de Anthropic.") from exc
        if self.provider in ("openai", "compatible"):
            try:
                import openai
            except ImportError as exc:
                raise LLMError("Falta el paquete «openai»: pip install openai") from exc
            if self.provider == "compatible":
                if not self.base_url:
                    raise LLMError("Indica la URL base del endpoint compatible con OpenAI.")
                # El SDK exige una key aunque los servidores locales no la usen.
                return openai.OpenAI(api_key=api_key or "sin-key", base_url=self.base_url)
            try:
                return openai.OpenAI(api_key=api_key)
            except openai.OpenAIError as exc:
                raise LLMError("Falta la API key de OpenAI.") from exc
        try:
            from google import genai
        except ImportError as exc:
            raise LLMError("Falta el paquete «google-genai»: pip install google-genai") from exc
        try:
            return genai.Client(api_key=api_key)
        except ValueError as exc:
            raise LLMError("Falta la API key de Gemini.") from exc

    # --- API pública ----------------------------------------------------------

    def text(self, system: str, user: str, effort: str = "medium") -> str:
        """Genera una respuesta libre al par (system prompt, user prompt)."""
        return self._generate(system, user, effort, schema=None)

    def json(self, system: str, user: str, schema: dict, effort: str = "high") -> dict:
        """Devuelve un objeto JSON que cumple ``schema`` (salida estructurada)."""
        return extract_json(self._generate(system, user, effort, schema=schema))

    def _generate(self, system: str, user: str, effort: str, schema: dict | None) -> str:
        if self.provider == "anthropic":
            return self._anthropic(system, user, effort, schema)
        if self.provider in ("openai", "compatible"):
            return self._openai(system, user, effort, schema)
        return self._gemini(system, user, effort, schema)

    # --- Anthropic ------------------------------------------------------------

    def _anthropic(self, system: str, user: str, effort: str, schema: dict | None) -> str:
        output_config: dict[str, Any] = {"effort": effort}
        if schema is not None:
            output_config["format"] = {"type": "json_schema", "schema": schema}
        params: dict[str, Any] = {
            "model": self.model,
            "max_tokens": _MAX_TOKENS,
            "messages": [{"role": "user", "content": user}],
            "output_config": output_config,
        }
        if system.strip():
            params["system"] = system
        if self.use_fallbacks and self.model in _FALLBACK_MODELS:
            params["betas"] = [_FALLBACK_BETA]
            params["fallbacks"] = "default"
        try:
            response = self.client.beta.messages.create(**params)
        except anthropic.AuthenticationError as exc:
            raise LLMError("La API key de Anthropic no es válida.") from exc
        except anthropic.NotFoundError as exc:
            raise LLMError(f"El modelo «{self.model}» no está disponible.") from exc
        except anthropic.RateLimitError as exc:
            raise LLMError("Límite de uso alcanzado; espera un momento y reintenta.") from exc
        except anthropic.APIStatusError as exc:
            raise LLMError(f"Error de la API de Anthropic ({exc.status_code}): {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMError("No se pudo conectar con la API de Anthropic.") from exc

        if response.stop_reason == "refusal":
            raise LLMError("El modelo rechazó la petición por motivos de seguridad.")
        if response.stop_reason == "max_tokens":
            raise LLMError("La respuesta se cortó por exceder max_tokens.")
        return "".join(b.text for b in response.content if getattr(b, "type", None) == "text")

    # --- OpenAI y compatibles ---------------------------------------------------

    def _openai_effort(self, effort: str) -> str | None:
        """``reasoning_effort`` sólo para modelos de razonamiento de OpenAI."""
        if self.provider != "openai":
            return None
        name = self.model.lower()
        if name.startswith(("gpt-5", "gpt-6", "gpt-7", "o1", "o3", "o4")) and "chat" not in name:
            return effort
        return None

    def _openai(self, system: str, user: str, effort: str, schema: dict | None) -> str:
        import openai

        label = "OpenAI" if self.provider == "openai" else f"el endpoint {self.base_url}"
        messages: list[dict[str, str]] = []
        if system.strip():
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})
        params: dict[str, Any] = {"model": self.model, "messages": messages}
        reasoning = self._openai_effort(effort)
        if reasoning:
            params["reasoning_effort"] = reasoning

        # Para JSON se prueba de más a menos estricto, porque no todos los
        # endpoints compatibles admiten ``json_schema``.
        attempts: list[dict[str, Any]] = [params]
        if schema is not None:
            strict = {
                **params,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"name": "respuesta", "schema": schema, "strict": True},
                },
            }
            loose_messages = [dict(m) for m in messages]
            if loose_messages[0]["role"] == "system":
                loose_messages[0]["content"] += _schema_instructions(schema)
            else:
                loose_messages.insert(0, {"role": "system", "content": _schema_instructions(schema).strip()})
            loose = {**params, "messages": loose_messages}
            attempts = [strict, {**loose, "response_format": {"type": "json_object"}}]
            if self.provider == "compatible":
                attempts.append(loose)

        for i, attempt in enumerate(attempts):
            try:
                response = self.client.chat.completions.create(**attempt)
                break
            except openai.BadRequestError as exc:
                if i == len(attempts) - 1:
                    raise LLMError(f"Petición rechazada por {label}: {exc.message}") from exc
            except openai.AuthenticationError as exc:
                raise LLMError(f"La API key de {label} no es válida.") from exc
            except openai.NotFoundError as exc:
                raise LLMError(f"El modelo «{self.model}» no está disponible en {label}.") from exc
            except openai.RateLimitError as exc:
                raise LLMError("Límite de uso alcanzado; espera un momento y reintenta.") from exc
            except openai.APIStatusError as exc:
                raise LLMError(f"Error de {label} ({exc.status_code}): {exc.message}") from exc
            except openai.APIConnectionError as exc:
                raise LLMError(f"No se pudo conectar con {label}.") from exc

        if not response.choices:
            raise LLMError("El modelo no devolvió ninguna respuesta.")
        choice = response.choices[0]
        if getattr(choice.message, "refusal", None):
            raise LLMError("El modelo rechazó la petición por motivos de seguridad.")
        if choice.finish_reason == "length":
            raise LLMError("La respuesta se cortó por exceder el máximo de tokens.")
        if choice.finish_reason == "content_filter":
            raise LLMError("El filtro de contenido del proveedor bloqueó la respuesta.")
        return choice.message.content or ""

    # --- Google Gemini ------------------------------------------------------------

    def _gemini_thinking(self, effort: str) -> dict | None:
        """``thinking_level`` para Gemini 3 y posteriores (2.x usa presupuestos)."""
        if not re.match(r"gemini-([3-9]|\d{2,})", self.model):
            return None
        level = {"low": "LOW", "medium": "MEDIUM"}.get(effort, "HIGH")
        return {"thinking_level": level}

    def _gemini(self, system: str, user: str, effort: str, schema: dict | None) -> str:
        from google.genai import errors

        config: dict[str, Any] = {}
        if system.strip():
            config["system_instruction"] = system
        thinking = self._gemini_thinking(effort)
        if thinking:
            config["thinking_config"] = thinking
        if schema is not None:
            config["response_mime_type"] = "application/json"
            config["response_json_schema"] = schema
        try:
            response = self.client.models.generate_content(model=self.model, contents=user, config=config)
        except errors.APIError as exc:
            code = getattr(exc, "code", None)
            if code in (401, 403):
                raise LLMError("La API key de Gemini no es válida o no tiene permiso.") from exc
            if code == 404:
                raise LLMError(f"El modelo «{self.model}» no está disponible en Gemini.") from exc
            if code == 429:
                raise LLMError("Límite de uso alcanzado; espera un momento y reintenta.") from exc
            raise LLMError(f"Error de la API de Gemini ({code}): {getattr(exc, 'message', exc)}") from exc
        except Exception as exc:  # red caída, DNS, timeouts… (el SDK no los envuelve)
            raise LLMError(f"No se pudo llamar a la API de Gemini: {exc}") from exc

        feedback = getattr(response, "prompt_feedback", None)
        if feedback is not None and getattr(feedback, "block_reason", None):
            raise LLMError("Gemini bloqueó la petición por motivos de seguridad.")
        candidates = getattr(response, "candidates", None) or []
        if candidates:
            reason = str(getattr(candidates[0], "finish_reason", "") or "")
            if reason.endswith("MAX_TOKENS"):
                raise LLMError("La respuesta se cortó por exceder el máximo de tokens.")
            if reason.endswith(("SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII")):
                raise LLMError("Gemini bloqueó la respuesta por motivos de seguridad.")
        return response.text or ""
