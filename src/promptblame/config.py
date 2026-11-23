"""Configuración desde variables de entorno y desde un fichero ``.env``.

La interfaz, la CLI y la API REST llaman a :func:`load_env` al arrancar: si en
el directorio de trabajo (o en uno superior) hay un ``.env``, sus variables se
cargan en ``os.environ`` sin pisar las que ya existen. Así las API keys y los
ajustes de proveedor y modelo quedan listos sin escribirlos cada vez.

Las variables reconocidas están documentadas en ``.env.example``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from .attribution import LANGUAGES
from .llm import DEFAULT_BASE_URL, DEFAULT_PROVIDER, EFFORTS, PROVIDERS

_TRUE = {"1", "true", "yes", "on", "si", "sí"}
_FALSE = {"0", "false", "no", "off"}


def load_env(path: str | None = None) -> str | None:
    """Carga un ``.env`` en ``os.environ`` sin pisar variables ya definidas.

    Sin ``path`` busca ``.env`` desde el directorio de trabajo hacia arriba.
    Devuelve la ruta cargada o ``None`` si no hay fichero (o si falta
    ``python-dotenv``, que es una dependencia del paquete).
    """
    try:
        from dotenv import find_dotenv, load_dotenv
    except ImportError:  # pragma: no cover - python-dotenv es una dependencia
        return None
    found = path or find_dotenv(usecwd=True)
    if not found or not os.path.isfile(found):
        return None
    load_dotenv(found, override=False)
    return found


def _get(name: str) -> str | None:
    value = os.environ.get(name, "").strip()
    return value or None


def env_bool(name: str, default: bool = False) -> bool:
    value = (_get(name) or "").lower()
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    return default


def env_int(name: str, default: int, low: int, high: int) -> int:
    try:
        value = int(_get(name) or "")
    except ValueError:
        return default
    return min(high, max(low, value))


def _provider(name: str) -> str:
    value = (_get(name) or "").lower()
    return value if value in PROVIDERS else DEFAULT_PROVIDER


def _effort(name: str, default: str) -> str:
    value = (_get(name) or "").lower()
    return value if value in EFFORTS else default


@dataclass(frozen=True)
class RoleSettings:
    """Proveedor, modelo y esfuerzo de un papel (servicio o juez)."""

    provider: str
    model: str
    effort: str


@dataclass(frozen=True)
class Settings:
    service: RoleSettings
    judge: RoleSettings
    base_url: str
    language: str | None
    ablation: bool
    max_ablation: int


def _role(prefix: str, default_effort: str) -> RoleSettings:
    provider = _provider(f"PROMPTBLAME_{prefix}_PROVIDER")
    model = _get(f"PROMPTBLAME_{prefix}_MODEL") or PROVIDERS[provider].models[0]
    return RoleSettings(provider, model, _effort(f"PROMPTBLAME_{prefix}_EFFORT", default_effort))


def settings() -> Settings:
    """Ajustes por defecto leídos del entorno (después de :func:`load_env`).

    Los valores no válidos se ignoran y se usa el valor predeterminado.
    """
    language = (_get("PROMPTBLAME_LANGUAGE") or "").lower()
    return Settings(
        service=_role("SERVICE", "medium"),
        judge=_role("JUDGE", "high"),
        base_url=_get("OPENAI_COMPATIBLE_BASE_URL") or DEFAULT_BASE_URL,
        language=language if language in LANGUAGES else None,
        ablation=env_bool("PROMPTBLAME_ABLATION"),
        max_ablation=env_int("PROMPTBLAME_MAX_ABLATION", 8, 1, 30),
    )


__all__ = ["RoleSettings", "Settings", "env_bool", "env_int", "load_env", "settings"]
