"""Envoltorio mínimo sobre la API de Claude (SDK oficial ``anthropic``)."""

from __future__ import annotations

import json
from typing import Any

import anthropic

DEFAULT_MODEL = "claude-opus-5-5"

# Modelos que se ofrecen en la interfaz. El primero es el predeterminado.
MODELS = [
    "claude-opus-5-5",
    "claude-fable-5-2",
    "claude-sonnet-5-5",
    "claude-haiku-5-5",
]

EFFORTS = ["low", "medium", "high", "xhigh", "max"]

# Modelos que aceptan el parámetro ``fallbacks`` en el servidor: si el
# clasificador de seguridad rechaza la petición, la API la reintenta con otro
# modelo dentro de la misma llamada.
_FALLBACK_MODELS = {"claude-opus-5-5", "claude-fable-5-2", "claude-sonnet-5-5"}
_FALLBACK_BETA = "server-side-fallback-2026-07-01"


class LLMError(RuntimeError):
    """Error comprensible para mostrar en la interfaz."""


class LLM:
    """Hace llamadas de texto y de JSON estructurado a un modelo de Claude."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        client: Any | None = None,
        api_key: str | None = None,
        use_fallbacks: bool = True,
    ) -> None:
        self.model = model
        self.client = client or anthropic.Anthropic(api_key=api_key or None)
        self.use_fallbacks = use_fallbacks

    def _create(self, **kwargs: Any) -> Any:
        params: dict[str, Any] = {"model": self.model, "max_tokens": 16000, **kwargs}
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
            raise LLMError(f"Error de la API ({exc.status_code}): {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMError("No se pudo conectar con la API de Anthropic.") from exc

        if response.stop_reason == "refusal":
            raise LLMError("El modelo rechazó la petición por motivos de seguridad.")
        if response.stop_reason == "max_tokens":
            raise LLMError("La respuesta se cortó por exceder max_tokens.")
        return response

    @staticmethod
    def _text(response: Any) -> str:
        return "".join(b.text for b in response.content if getattr(b, "type", None) == "text")

    def text(self, system: str, user: str, effort: str = "medium") -> str:
        """Genera una respuesta libre al par (system prompt, user prompt)."""
        kwargs: dict[str, Any] = {
            "messages": [{"role": "user", "content": user}],
            "output_config": {"effort": effort},
        }
        if system.strip():
            kwargs["system"] = system
        return self._text(self._create(**kwargs))

    def json(self, system: str, user: str, schema: dict, effort: str = "high") -> dict:
        """Devuelve un objeto JSON que cumple ``schema`` (structured outputs)."""
        response = self._create(
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={
                "effort": effort,
                "format": {"type": "json_schema", "schema": schema},
            },
        )
        raw = self._text(response)
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LLMError("El modelo devolvió un JSON no válido.") from exc
