"""Vista HTML de la atribución: respuesta en bloques de colores y citas enlazadas."""

from __future__ import annotations

from html import escape

from .attribution import Attribution, Block

PALETTE = [
    "#ffd6a5", "#caffbf", "#9bf6ff", "#bdb2ff", "#ffc6ff",
    "#fdffb6", "#a0c4ff", "#ffadad", "#b9fbc0", "#f1c0e8",
]
NO_SOURCE = "#e5e7eb"
ORIGIN_LABEL = {"system": "System prompt", "user": "User prompt"}


def block_color(block: Block, index: int) -> str:
    return PALETTE[index % len(PALETTE)] if block.sources else NO_SOURCE


def _ablation_badge(effect: float | None, verified: bool | None) -> str:
    if effect is None:
        return ""
    cls, label = ("ok", "confirmada") if verified else ("ko", "no confirmada")
    return f'<span class="badge {cls}" title="Caída de similitud al quitar la instrucción">ablación: {label} ({effect:.2f})</span>'


def _response_html(attribution: Attribution) -> str:
    parts, cursor = [], 0
    for i, block in enumerate(attribution.blocks):
        parts.append(escape(attribution.response[cursor : block.start]))
        parts.append(
            f'<span class="blk" data-b="{block.id}" style="background:{block_color(block, i)}">'
            f'<sup>{block.id}</sup>{escape(block.text)}</span>'
        )
        cursor = block.end
    parts.append(escape(attribution.response[cursor:]))
    return "".join(parts)


def _card_html(block: Block, index: int) -> str:
    color = block_color(block, index)
    if block.sources:
        quotes = "".join(
            f'<div class="quote"><div class="meta"><b>{link.unit.id}</b> · {ORIGIN_LABEL[link.unit.origin]}'
            f' · confianza {link.confidence} {_ablation_badge(link.ablation_effect, link.verified)}</div>'
            f'<blockquote>{escape(link.unit.text)}</blockquote></div>'
            for link in block.sources
        )
    else:
        quotes = '<div class="none">Sin instrucción de origen: conocimiento propio del modelo.</div>'
    explanation = f'<div class="why">{escape(block.explanation)}</div>' if block.explanation else ""
    return (
        f'<div class="card" data-b="{block.id}" id="card-{block.id}" style="border-left-color:{color}">'
        f'<div class="title"><span class="dot" style="background:{color}"></span>{block.id}</div>'
        f"{quotes}{explanation}</div>"
    )


CSS = """
* { box-sizing: border-box; }
body { margin: 0; font-family: "Source Sans Pro", system-ui, sans-serif; font-size: 15px; color: #1f2937; }
.wrap { display: grid; grid-template-columns: minmax(0, 1.25fr) minmax(0, 1fr); gap: 20px; }
.col { max-height: 680px; overflow-y: auto; padding: 4px 8px 4px 0; }
.resp { white-space: pre-wrap; line-height: 1.75; }
.blk { border-radius: 4px; padding: 1px 2px; cursor: pointer; transition: outline .1s; }
.blk sup { font-size: 10px; color: #6b7280; margin-right: 2px; font-weight: 600; }
.blk.on, .card.on { outline: 2px solid #111827; }
.card { border: 1px solid #e5e7eb; border-left: 6px solid; border-radius: 6px; padding: 8px 10px; margin-bottom: 10px; cursor: pointer; }
.title { font-weight: 700; margin-bottom: 4px; display: flex; align-items: center; gap: 6px; }
.dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; border: 1px solid #9ca3af; }
.meta { font-size: 12px; color: #4b5563; }
blockquote { margin: 2px 0 8px; padding: 4px 8px; background: #f9fafb; border-left: 3px solid #d1d5db; white-space: pre-wrap; }
.why { font-size: 13px; color: #374151; font-style: italic; }
.none { font-size: 13px; color: #6b7280; }
.badge { font-size: 11px; border-radius: 10px; padding: 1px 6px; margin-left: 4px; }
.badge.ok { background: #dcfce7; color: #166534; } .badge.ko { background: #fee2e2; color: #991b1b; }
h4 { margin: 4px 0 8px; }
.unused { margin-top: 14px; font-size: 13px; }
.unused li { margin-bottom: 4px; }
"""

JS = """
const all = (id) => document.querySelectorAll('[data-b="' + id + '"]');
document.querySelectorAll('[data-b]').forEach((el) => {
  const id = el.dataset.b;
  el.addEventListener('mouseenter', () => all(id).forEach((x) => x.classList.add('on')));
  el.addEventListener('mouseleave', () => all(id).forEach((x) => x.classList.remove('on')));
  el.addEventListener('click', () => {
    const target = el.classList.contains('blk') ? document.getElementById('card-' + id)
                                                : document.querySelector('.blk[data-b="' + id + '"]');
    if (target) target.scrollIntoView({behavior: 'smooth', block: 'center'});
  });
});
"""


def attribution_html(attribution: Attribution) -> str:
    """Documento HTML autocontenido con la vista de atribución."""
    cards = "".join(_card_html(b, i) for i, b in enumerate(attribution.blocks))
    unused = attribution.unused_sources
    unused_html = ""
    if unused:
        items = "".join(
            f"<li><b>{u.id}</b> ({ORIGIN_LABEL[u.origin]}): {escape(u.text)}</li>" for u in unused
        )
        unused_html = (
            '<div class="unused"><h4>Instrucciones sin efecto visible</h4>'
            f"<ul>{items}</ul></div>"
        )
    return (
        f"<!DOCTYPE html><html><head><meta charset='utf-8'><style>{CSS}</style></head><body>"
        '<div class="wrap">'
        f'<div class="col"><h4>Respuesta</h4><div class="resp">{_response_html(attribution)}</div></div>'
        f'<div class="col"><h4>Origen de cada bloque</h4>{cards}{unused_html}</div>'
        f"</div><script>{JS}</script></body></html>"
    )
