"""API REST de PromptBlame (FastAPI), para CI, evaluaciones y otros servicios.

Instala el extra y arranca el servidor::

    pip install "promptblame[api]"
    promptblame serve --port 8000        # documentación interactiva en /docs

Endpoints (todos reciben y devuelven JSON):

- ``GET  /health``
- ``POST /generate``           respuesta del servicio a un par de prompts.
- ``POST /attribute``          atribución por bloques (genera la respuesta si no se envía).
- ``POST /rewrite``            nueva versión del system prompt.
- ``POST /dead-instructions``  instrucciones nunca citadas en N ejecuciones.

Seguridad:

- Las API keys de los proveedores se leen **sólo** del entorno del servidor (o
  de su ``.env``); nunca viajan en la petición.
- La URL del endpoint compatible también sale del entorno
  (``OPENAI_COMPATIBLE_BASE_URL``): un cliente no puede hacer que el servidor
  llame a una URL arbitraria.
- Si se define ``PROMPTBLAME_API_TOKEN``, todas las rutas salvo ``/health``
  exigen ``Authorization: Bearer <token>``. Defínelo siempre que el servidor
  no escuche sólo en ``127.0.0.1``.
"""

from __future__ import annotations

import functools
import hmac
import os
from typing import Any, Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from . import __version__
from .attribution import Attribution, attribute, verify_by_ablation
from .config import load_env, settings
from .dead import scan_dead_instructions
from .llm import LLM, PROVIDERS, LLMError
from .rewrite import rewrite_system_prompt, unified_diff

ProviderId = Literal["anthropic", "openai", "gemini", "compatible"]
Effort = Literal["low", "medium", "high", "xhigh", "max"]
Language = Literal["en", "es"]

MAX_TEXT = 200_000
"""Límite de caracteres por campo de texto, para no aceptar peticiones desmesuradas."""


class ModelConfig(BaseModel):
    """Proveedor, modelo y esfuerzo. Lo que no se indique sale del entorno (``.env``)."""

    provider: ProviderId | None = None
    model: str | None = Field(default=None, max_length=200)
    effort: Effort | None = None


class PromptPair(BaseModel):
    system_prompt: str = Field(..., max_length=MAX_TEXT)
    user_prompt: str = Field(..., max_length=MAX_TEXT)
    service: ModelConfig = ModelConfig()


class AttributeRequest(PromptPair):
    response: str | None = Field(default=None, max_length=MAX_TEXT, description="Omit it to generate one.")
    judge: ModelConfig = ModelConfig()
    instructions: str = Field("", max_length=20_000, description="Custom attribution criteria.")
    language: Language = "en"
    ablation: bool = False
    max_ablation: int = Field(8, ge=1, le=30)


class RewriteRequest(AttributeRequest):
    improvement: str = Field(..., min_length=1, max_length=20_000)
    criteria_in_rewrite: bool = True


class DeadRequest(BaseModel):
    system_prompt: str = Field(..., max_length=MAX_TEXT)
    user_prompts: list[str] = Field(..., min_length=1, max_length=100)
    runs_per_prompt: int = Field(1, ge=1, le=10)
    threshold: float = Field(0.0, ge=0.0, le=1.0)
    service: ModelConfig = ModelConfig()
    judge: ModelConfig = ModelConfig()
    instructions: str = Field("", max_length=20_000)
    language: Language = "en"


def _resolve(config: ModelConfig, role: str) -> tuple[LLM, str]:
    cfg = settings()
    defaults = cfg.service if role == "service" else cfg.judge
    provider = config.provider or defaults.provider
    if config.model:
        model = config.model
    elif provider == defaults.provider:
        model = defaults.model
    else:
        model = PROVIDERS[provider].models[0]
    effort = config.effort or defaults.effort
    llm = LLM(model=model, provider=provider, base_url=cfg.base_url if provider == "compatible" else None)
    return llm, effort


def _check_token(authorization: str | None = Header(None)) -> None:
    token = os.environ.get("PROMPTBLAME_API_TOKEN", "")
    if not token:
        return
    scheme, _, value = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(value.strip(), token):
        raise HTTPException(status_code=401, detail="Invalid or missing bearer token.")


def _attribution(req: AttributeRequest) -> tuple[Attribution, LLM, str]:
    service, service_effort = _resolve(req.service, "service")
    judge, judge_effort = _resolve(req.judge, "judge")
    response = req.response
    if response is None:
        response = service.text(req.system_prompt, req.user_prompt, effort=service_effort)
    attr = attribute(
        judge,
        req.system_prompt,
        req.user_prompt,
        response,
        effort=judge_effort,
        instructions=req.instructions,
        language=req.language,
    )
    if req.ablation and attr.blocks:
        verify_by_ablation(service, attr, effort=service_effort, max_sources=req.max_ablation)
    return attr, judge, judge_effort


def create_app() -> FastAPI:
    """Crea la aplicación FastAPI (carga antes el ``.env`` del directorio de trabajo)."""
    load_env()
    app = FastAPI(
        title="PromptBlame",
        version=__version__,
        description="Attribute each part of an LLM response to the prompt instruction that produced it.",
    )
    auth = [Depends(_check_token)]

    def guarded(fn: Any) -> Any:
        """Convierte ``LLMError`` en 502 (fallo del proveedor) y ``ValueError`` en 422."""

        @functools.wraps(fn)
        def wrapper(req: Any) -> Any:
            try:
                return fn(req)
            except LLMError as exc:
                raise HTTPException(status_code=502, detail=str(exc)) from exc
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc

        return wrapper

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.post("/generate", dependencies=auth)
    @guarded
    def generate(req: PromptPair) -> dict[str, Any]:
        """Genera la respuesta del servicio."""
        service, effort = _resolve(req.service, "service")
        return {"response": service.text(req.system_prompt, req.user_prompt, effort=effort)}

    @app.post("/attribute", dependencies=auth)
    @guarded
    def attribute_endpoint(req: AttributeRequest) -> dict[str, Any]:
        """Atribuye cada bloque de la respuesta a las instrucciones de los prompts."""
        attr, _, _ = _attribution(req)
        return attr.to_dict()

    @app.post("/rewrite", dependencies=auth)
    @guarded
    def rewrite(req: RewriteRequest) -> dict[str, Any]:
        """Genera una nueva versión del system prompt a partir de la atribución."""
        attr, judge, effort = _attribution(req)
        result = rewrite_system_prompt(
            judge,
            attr,
            req.improvement,
            effort=effort,
            instructions=req.instructions if req.criteria_in_rewrite else "",
            language=req.language,
        )
        return {
            "attribution": attr.to_dict(),
            "new_system_prompt": result.new_system_prompt,
            "changes": result.changes,
            "summary": result.summary,
            "diff": unified_diff(req.system_prompt, result.new_system_prompt, language=req.language),
        }

    @app.post("/dead-instructions", dependencies=auth)
    @guarded
    def dead_instructions(req: DeadRequest) -> dict[str, Any]:
        """Detecta instrucciones del system prompt que no se citan en ninguna ejecución."""
        service, service_effort = _resolve(req.service, "service")
        judge, judge_effort = _resolve(req.judge, "judge")
        report = scan_dead_instructions(
            service,
            judge,
            req.system_prompt,
            req.user_prompts,
            runs_per_prompt=req.runs_per_prompt,
            threshold=req.threshold,
            service_effort=service_effort,
            judge_effort=judge_effort,
            instructions=req.instructions,
            language=req.language,
        )
        return report.to_dict()

    return app
