"""Instrucciones muertas: partes del system prompt que nunca se citan.

Una instrucción que no aparece como causa de ningún bloque en ninguna de N
respuestas probablemente no está haciendo nada y cuesta tokens en cada
llamada. Este módulo:

1. Genera N respuestas (varios user prompts y/o varias ejecuciones de cada
   uno) y atribuye cada una con el juez, o agrega atribuciones que ya tengas.
2. Cuenta en cuántas ejecuciones se cita cada instrucción del system prompt.
3. Propone una versión recortada del system prompt sin las instrucciones que
   nunca se citaron y estima los tokens que ahorra.

Ojo: «nunca citada» no es «inútil». Una regla de seguridad o para casos raros
sólo actúa cuando el caso aparece; por eso conviene usar user prompts variados
y revisar la propuesta antes de adoptarla.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from .attribution import DEFAULT_LANGUAGE, Attribution, attribute
from .llm import LLM, LLMError
from .segmentation import Unit, segment

CHARS_PER_TOKEN = 4
"""Aproximación de caracteres por token para estimar el ahorro (sin tokenizador)."""


def estimate_tokens(text: str) -> int:
    """Estimación aproximada de tokens (unos 4 caracteres por token)."""
    stripped = text.strip()
    return max(1, round(len(stripped) / CHARS_PER_TOKEN)) if stripped else 0


@dataclass
class InstructionUsage:
    unit: Unit
    # Ejecuciones en las que algún bloque cita la instrucción.
    cited_runs: int
    runs: int
    # Bloques que la citan, sumando todas las ejecuciones.
    cited_blocks: int = 0

    @property
    def rate(self) -> float:
        return round(self.cited_runs / self.runs, 3) if self.runs else 0.0

    @property
    def tokens(self) -> int:
        return estimate_tokens(self.unit.text)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.unit.id,
            "text": self.unit.text,
            "cited_runs": self.cited_runs,
            "runs": self.runs,
            "cited_blocks": self.cited_blocks,
            "rate": self.rate,
            "tokens": self.tokens,
        }


@dataclass
class DeadInstructionReport:
    system_prompt: str
    usage: list[InstructionUsage]
    runs: int
    # Instrucciones citadas en una fracción de ejecuciones <= ``threshold`` (0 = nunca).
    threshold: float = 0.0
    attributions: list[Attribution] = field(default_factory=list)
    # Ejecuciones que fallaron (mensaje de error), si se generaron aquí.
    errors: list[str] = field(default_factory=list)

    @property
    def dead(self) -> list[InstructionUsage]:
        """Instrucciones que (casi) nunca se citan, en el orden del system prompt."""
        return [u for u in self.usage if u.rate <= self.threshold]

    @property
    def trimmed_system_prompt(self) -> str:
        return trim_system_prompt(self.system_prompt, [u.unit for u in self.dead])

    @property
    def tokens_before(self) -> int:
        return estimate_tokens(self.system_prompt)

    @property
    def tokens_after(self) -> int:
        return estimate_tokens(self.trimmed_system_prompt)

    @property
    def tokens_saved(self) -> int:
        return max(0, self.tokens_before - self.tokens_after)

    def to_dict(self) -> dict[str, Any]:
        return {
            "runs": self.runs,
            "threshold": self.threshold,
            "usage": [u.to_dict() for u in self.usage],
            "dead": [u.unit.id for u in self.dead],
            "trimmed_system_prompt": self.trimmed_system_prompt,
            "tokens_before": self.tokens_before,
            "tokens_after": self.tokens_after,
            "tokens_saved": self.tokens_saved,
            "errors": list(self.errors),
        }


def trim_system_prompt(system_prompt: str, units: Sequence[Unit]) -> str:
    """Quita las unidades del system prompt y las líneas que se quedan vacías.

    Las líneas que ya estaban vacías (separadores de párrafo) se conservan,
    salvo que queden dos seguidas.
    """
    if not units:
        return system_prompt
    removed = [False] * len(system_prompt)
    for unit in units:
        for i in range(unit.start, unit.end):
            removed[i] = True
    lines: list[str] = []
    pos = 0
    for raw in system_prompt.splitlines(keepends=True):
        line = raw.rstrip("\r\n")
        kept = "".join(ch for i, ch in enumerate(line, pos) if not removed[i])
        pos += len(raw)
        was_blank = not line.strip()
        if not was_blank and not kept.strip():
            continue  # la línea entera era instrucción muerta
        if was_blank:
            lines.append("")
        elif kept == line:
            lines.append(line)
        else:
            # Al quitar una frase de en medio quedan espacios de sobra.
            indent = line[: len(line) - len(line.lstrip())]
            lines.append(indent + " ".join(kept.split()))
    # Sin líneas en blanco duplicadas ni al principio o al final.
    cleaned: list[str] = []
    for line in lines:
        if not line and (not cleaned or not cleaned[-1]):
            continue
        cleaned.append(line)
    while cleaned and not cleaned[-1]:
        cleaned.pop()
    return "\n".join(cleaned)


def dead_instructions(attributions: Sequence[Attribution], threshold: float = 0.0) -> DeadInstructionReport:
    """Agrega varias atribuciones del mismo system prompt y detecta las instrucciones muertas.

    ``threshold`` es la fracción máxima de ejecuciones en que puede citarse una
    instrucción para considerarla muerta (0 = nunca citada; 0.2 = en el 20 % o
    menos).
    """
    if not attributions:
        raise ValueError("At least one attribution is needed.")
    system_prompt = attributions[0].system_prompt
    if any(a.system_prompt != system_prompt for a in attributions):
        raise ValueError("All attributions must share the same system prompt.")
    units = segment(system_prompt, "system", "S")
    usage = []
    for unit in units:
        per_run = [sum(any(link.unit.id == unit.id for link in b.sources) for b in a.blocks) for a in attributions]
        usage.append(InstructionUsage(unit, sum(1 for n in per_run if n), len(attributions), sum(per_run)))
    return DeadInstructionReport(system_prompt, usage, len(attributions), threshold, list(attributions))


def scan_dead_instructions(
    service: LLM,
    judge: LLM,
    system_prompt: str,
    user_prompts: Sequence[str],
    runs_per_prompt: int = 1,
    threshold: float = 0.0,
    service_effort: str = "medium",
    judge_effort: str = "high",
    instructions: str = "",
    language: str = DEFAULT_LANGUAGE,
    max_workers: int = 4,
    on_progress: Callable[[int, int], None] | None = None,
) -> DeadInstructionReport:
    """Genera ``len(user_prompts) * runs_per_prompt`` respuestas, las atribuye y agrega.

    Cada ejecución hace dos llamadas: una al servicio y otra al juez. Las
    ejecuciones que fallan se anotan en ``errors`` y no cuentan; si fallan
    todas, se lanza ``LLMError``.
    """
    prompts = [p for p in user_prompts if p.strip()]
    if not prompts:
        raise ValueError("At least one user prompt is needed.")
    jobs = [p for p in prompts for _ in range(max(1, runs_per_prompt))]
    done = 0
    lock = threading.Lock()

    def run(user_prompt: str) -> Attribution | str:
        nonlocal done
        try:
            response = service.text(system_prompt, user_prompt, effort=service_effort)
            result: Attribution | str = attribute(
                judge,
                system_prompt,
                user_prompt,
                response,
                effort=judge_effort,
                instructions=instructions,
                language=language,
            )
        except LLMError as exc:
            result = str(exc)
        with lock:
            done += 1
            current = done
        if on_progress is not None:
            on_progress(current, len(jobs))
        return result

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        results = list(pool.map(run, jobs))
    attributions = [r for r in results if isinstance(r, Attribution)]
    errors = [r for r in results if isinstance(r, str)]
    if not attributions:
        raise LLMError(errors[0] if errors else "No run succeeded.")
    report = dead_instructions(attributions, threshold)
    report.errors = errors
    return report


def split_user_prompts(text: str) -> list[str]:
    """Separa varios user prompts escritos en un mismo texto con líneas ``---``."""
    prompts: list[str] = []
    current: list[str] = []
    for line in text.splitlines():
        if line.strip() == "---":
            prompts.append("\n".join(current).strip())
            current = []
        else:
            current.append(line)
    prompts.append("\n".join(current).strip())
    return [p for p in prompts if p]
