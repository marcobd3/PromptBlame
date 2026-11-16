"""Atribución de la respuesta a instrucciones del system prompt y del user prompt.

Funciona con modelos cerrados (sin acceso a logits ni a pesos) de cualquier
proveedor admitido en ``llm.py`` en dos pasos:

1. **Atribución por juez LLM.** Los prompts y la respuesta se segmentan de forma
   determinista en unidades numeradas (S1…, U1…, R1…). Un modelo juez
   recibe todas las unidades y decide, para cada unidad de la respuesta, de qué
   instrucciones procede. Las unidades contiguas con las mismas fuentes se
   agrupan en bloques.
2. **Verificación por ablación (opcional).** Al estilo de ContextCite, pero a
   nivel de instrucción: para cada instrucción citada se regenera la respuesta
   sin ella y se mide cuánto cambia cada bloque que la cita respecto a una
   regeneración de control con el prompt completo. Si al quitar la instrucción
   el bloque desaparece o cambia mucho, la atribución queda confirmada.
"""

from __future__ import annotations

import difflib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from .llm import LLM
from .segmentation import Unit, remove_unit, segment

CONFIDENCES = ["alta", "media", "baja"]

ATTRIBUTION_SCHEMA = {
    "type": "object",
    "properties": {
        "segments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "sources": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "confidence": {"type": "string", "enum": CONFIDENCES},
                            },
                            "required": ["id", "confidence"],
                            "additionalProperties": False,
                        },
                    },
                    "explanation": {"type": "string"},
                },
                "required": ["id", "sources", "explanation"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["segments"],
    "additionalProperties": False,
}

ATTRIBUTION_SYSTEM = """Eres un analista de atribución de prompts. Recibes las \
instrucciones numeradas de un system prompt (S1, S2…) y de un user prompt (U1, \
U2…), y la respuesta que un modelo de lenguaje generó con ellos, dividida en \
segmentos numerados (R1, R2…).

Para cada segmento de la respuesta indica qué instrucciones lo causaron: las \
que piden ese contenido, fijan su formato, tono, idioma, extensión o \
restricciones, o aportan los datos que aparecen en él. Reglas:
- Devuelve exactamente un elemento por cada segmento R, en el mismo orden.
- Cita sólo identificadores que existan. Ordena las fuentes de más a menos \
influyente y cita como máximo cuatro.
- confidence: "alta" si la instrucción exige claramente ese contenido, "media" \
si lo favorece, "baja" si la relación es indirecta.
- Si el segmento procede del conocimiento general del modelo y no de ninguna \
instrucción, deja sources vacío.
- explanation: una frase breve en español que explique el vínculo."""


@dataclass
class SourceLink:
    unit: Unit
    confidence: str
    # Resultado de la ablación (None si no se ha verificado).
    ablation_effect: float | None = None

    @property
    def verified(self) -> bool | None:
        if self.ablation_effect is None:
            return None
        return self.ablation_effect >= ABLATION_THRESHOLD


@dataclass
class Block:
    id: str
    start: int
    end: int
    text: str
    segment_ids: list[str]
    sources: list[SourceLink]
    explanation: str


@dataclass
class Attribution:
    system_prompt: str
    user_prompt: str
    response: str
    sources: list[Unit]
    segments: list[Unit]
    blocks: list[Block]
    ablation_done: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def unused_sources(self) -> list[Unit]:
        """Instrucciones que ningún bloque cita (posiblemente ignoradas)."""
        used = {link.unit.id for b in self.blocks for link in b.sources}
        return [u for u in self.sources if u.id not in used]

    def source(self, unit_id: str) -> Unit | None:
        return next((u for u in self.sources if u.id == unit_id), None)


ABLATION_THRESHOLD = 0.15


def prompt_units(system_prompt: str, user_prompt: str) -> list[Unit]:
    return segment(system_prompt, "system", "S") + segment(user_prompt, "user", "U")


def _format_units(units: list[Unit]) -> str:
    return "\n".join(f"[{u.id}] {u.text}" for u in units) or "(vacío)"


def build_attribution_request(sources: list[Unit], segments: list[Unit]) -> str:
    system_units = [u for u in sources if u.origin == "system"]
    user_units = [u for u in sources if u.origin == "user"]
    return (
        "<system_prompt>\n" + _format_units(system_units) + "\n</system_prompt>\n\n"
        "<user_prompt>\n" + _format_units(user_units) + "\n</user_prompt>\n\n"
        "<respuesta>\n" + _format_units(segments) + "\n</respuesta>"
    )


def merge_blocks(
    response: str, segments: list[Unit], judged: dict[str, dict], sources: list[Unit]
) -> list[Block]:
    """Agrupa segmentos contiguos de un mismo párrafo con las mismas fuentes en bloques."""
    by_id = {u.id: u for u in sources}
    blocks: list[Block] = []
    for seg in segments:
        item = judged.get(seg.id, {"sources": [], "explanation": ""})
        links: list[SourceLink] = []
        for src in item.get("sources", []):
            unit = by_id.get(src.get("id"))
            if unit and all(link.unit.id != unit.id for link in links):
                conf = src.get("confidence") if src.get("confidence") in CONFIDENCES else "media"
                links.append(SourceLink(unit, conf))
        key = [link.unit.id for link in links]
        prev = blocks[-1] if blocks else None
        same_paragraph = prev is not None and "\n\n" not in response[prev.end : seg.start]
        if same_paragraph and [link.unit.id for link in prev.sources] == key:
            prev.end = seg.end
            prev.text = response[prev.start : prev.end]
            prev.segment_ids.append(seg.id)
            explanation = item.get("explanation", "").strip()
            if explanation and explanation not in prev.explanation:
                prev.explanation = f"{prev.explanation} {explanation}".strip()
            for link, new in zip(prev.sources, links):
                link.confidence = min(link.confidence, new.confidence, key=CONFIDENCES.index)
            continue
        blocks.append(
            Block(
                id=f"B{len(blocks) + 1}",
                start=seg.start,
                end=seg.end,
                text=seg.text,
                segment_ids=[seg.id],
                sources=links,
                explanation=item.get("explanation", "").strip(),
            )
        )
    return blocks


def attribute(
    llm: LLM, system_prompt: str, user_prompt: str, response: str, effort: str = "high"
) -> Attribution:
    """Atribuye cada bloque de ``response`` a las instrucciones de los prompts."""
    sources = prompt_units(system_prompt, user_prompt)
    segments = segment(response, "response", "R")
    result = Attribution(system_prompt, user_prompt, response, sources, segments, [])
    if not segments:
        return result
    data = llm.json(
        ATTRIBUTION_SYSTEM, build_attribution_request(sources, segments), ATTRIBUTION_SCHEMA, effort=effort
    )
    judged = {item["id"]: item for item in data.get("segments", []) if "id" in item}
    missing = [s.id for s in segments if s.id not in judged]
    if missing:
        result.notes.append(f"El juez no devolvió atribución para: {', '.join(missing)}.")
    result.blocks = merge_blocks(response, segments, judged, sources)
    return result


# --- Verificación por ablación -------------------------------------------------


def _sentences(text: str) -> list[str]:
    return [u.text for u in segment(text, "response", "X")] or [text]


def similarity(block_text: str, other_response: str) -> float:
    """Cuánto del bloque sigue presente en otra respuesta (0 = nada, 1 = igual).

    Para cada frase del bloque se busca la frase más parecida de la otra
    respuesta y se promedia. Es una medida léxica, barata y determinista.
    """
    others = _sentences(other_response) if other_response.strip() else []
    if not others:
        return 0.0
    scores = []
    for sentence in _sentences(block_text):
        best = 0.0
        for other in others:
            matcher = difflib.SequenceMatcher(None, sentence.lower(), other.lower(), autojunk=False)
            if matcher.real_quick_ratio() <= best or matcher.quick_ratio() <= best:
                continue
            best = max(best, matcher.ratio())
        scores.append(best)
    return sum(scores) / len(scores)


def verify_by_ablation(
    llm: LLM,
    attribution: Attribution,
    effort: str = "medium",
    max_sources: int = 8,
    max_workers: int = 4,
) -> Attribution:
    """Regenera la respuesta quitando cada instrucción citada y mide el efecto.

    El efecto de quitar la fuente S sobre el bloque B es
    ``sim(B, control) - sim(B, sin S)``, donde *control* es una regeneración con
    el prompt completo. Restar el control descuenta la variación natural entre
    dos generaciones del mismo prompt.
    """
    cited: list[Unit] = []
    for block in attribution.blocks:
        for link in block.sources:
            if link.unit not in cited:
                cited.append(link.unit)
    if not cited:
        return attribution
    if len(cited) > max_sources:
        attribution.notes.append(
            f"Ablación limitada a las {max_sources} instrucciones más citadas de {len(cited)}."
        )
        counts = {u.id: sum(u in [l.unit for l in b.sources] for b in attribution.blocks) for u in cited}
        cited = sorted(cited, key=lambda u: -counts[u.id])[:max_sources]

    def run(unit: Unit | None) -> str:
        system, user = attribution.system_prompt, attribution.user_prompt
        if unit is not None and unit.origin == "system":
            system = remove_unit(system, unit)
        elif unit is not None:
            user = remove_unit(user, unit)
        if not user.strip():
            user = "(sin mensaje)"
        return llm.text(system, user, effort=effort)

    jobs: list[Unit | None] = [None, *cited]
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        outputs = list(pool.map(run, jobs))
    control, ablated = outputs[0], dict(zip((u.id for u in cited), outputs[1:]))

    for block in attribution.blocks:
        base = similarity(block.text, control)
        for link in block.sources:
            if link.unit.id in ablated:
                drop = base - similarity(block.text, ablated[link.unit.id])
                link.ablation_effect = round(max(0.0, drop), 3)
    attribution.ablation_done = True
    return attribution
