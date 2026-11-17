"""Vista HTML de la atribución: respuesta en bloques de colores y citas enlazadas."""

from __future__ import annotations

from html import escape

from .attribution import DEFAULT_LANGUAGE, Attribution, Block

PALETTE = [
    "#ffd6a5",
    "#caffbf",
    "#9bf6ff",
    "#bdb2ff",
    "#ffc6ff",
    "#fdffb6",
    "#a0c4ff",
    "#ffadad",
    "#b9fbc0",
    "#f1c0e8",
]
NO_SOURCE = "#e5e7eb"
ORIGIN_LABEL = {"system": "System prompt", "user": "User prompt"}

TEXTS = {
    "en": {
        "confirmed": "confirmed",
        "not_confirmed": "not confirmed",
        "ablation": "ablation",
        "ablation_title": "Similarity drop when the instruction is removed",
        "confidence": "confidence",
        "conf_alta": "high",
        "conf_media": "medium",
        "conf_baja": "low",
        "no_source": "No source instruction: the model's own knowledge.",
        "unused": "Instructions with no visible effect",
        "response": "Response",
        "origin": "Source of each block",
    },
    "es": {
        "confirmed": "confirmada",
        "not_confirmed": "no confirmada",
        "ablation": "ablación",
        "ablation_title": "Caída de similitud al quitar la instrucción",
        "confidence": "confianza",
        "conf_alta": "alta",
        "conf_media": "media",
        "conf_baja": "baja",
        "no_source": "Sin instrucción de origen: conocimiento propio del modelo.",
        "unused": "Instrucciones sin efecto visible",
        "response": "Respuesta",
        "origin": "Origen de cada bloque",
    },
}


def _texts(language: str) -> dict[str, str]:
    return TEXTS.get(language, TEXTS[DEFAULT_LANGUAGE])


def block_color(block: Block, index: int) -> str:
    return PALETTE[index % len(PALETTE)] if block.sources else NO_SOURCE


def _ablation_badge(effect: float | None, verified: bool | None, tx: dict[str, str]) -> str:
    if effect is None:
        return ""
    cls, label = ("ok", tx["confirmed"]) if verified else ("ko", tx["not_confirmed"])
    return f'<span class="badge {cls}" title="{tx["ablation_title"]}">{tx["ablation"]}: {label} ({effect:.2f})</span>'


def _response_html(attribution: Attribution) -> str:
    parts, cursor = [], 0
    for i, block in enumerate(attribution.blocks):
        parts.append(escape(attribution.response[cursor : block.start]))
        parts.append(
            f'<span class="blk" data-b="{block.id}" style="background:{block_color(block, i)}">'
            f"<sup>{block.id}</sup>{escape(block.text)}</span>"
        )
        cursor = block.end
    parts.append(escape(attribution.response[cursor:]))
    return "".join(parts)


def _card_html(block: Block, index: int, tx: dict[str, str]) -> str:
    color = block_color(block, index)
    if block.sources:
        quotes = "".join(
            f'<div class="quote"><div class="meta"><b>{link.unit.id}</b> · {ORIGIN_LABEL[link.unit.origin]}'
            f" · {tx['confidence']} {tx.get('conf_' + link.confidence, link.confidence)}"
            f" {_ablation_badge(link.ablation_effect, link.verified, tx)}</div>"
            f"<blockquote>{escape(link.unit.text)}</blockquote></div>"
            for link in block.sources
        )
    else:
        quotes = f'<div class="none">{tx["no_source"]}</div>'
    explanation = f'<div class="why">{escape(block.explanation)}</div>' if block.explanation else ""
    return (
        f'<div class="card" data-b="{block.id}" id="card-{block.id}" style="border-left-color:{color}">'
        f'<div class="title"><span class="dot" style="background:{color}"></span>{block.id}</div>'
        f"{quotes}{explanation}</div>"
    )


CSS = """
:root {
  --fg: #1f2937; --muted: #4b5563; --soft: #6b7280; --border: #e5e7eb; --rule: #d1d5db;
  --quote-bg: #f9fafb; --card-bg: transparent; --focus: #111827; --blk-fg: #111827;
  --ok-bg: #dcfce7; --ok-fg: #166534; --ko-bg: #fee2e2; --ko-fg: #991b1b;
}
body.dark {
  --fg: #e5e7eb; --muted: #c4c9d4; --soft: #9ca3af; --border: #3f4451; --rule: #565c6b;
  --quote-bg: #262a35; --card-bg: #1c1f27; --focus: #f9fafb; --blk-fg: #111827;
  --ok-bg: #14532d; --ok-fg: #bbf7d0; --ko-bg: #7f1d1d; --ko-fg: #fecaca;
}
* { box-sizing: border-box; }
html, body { background: transparent; }
body { margin: 0; font-family: "Source Sans Pro", system-ui, sans-serif; font-size: 15px; color: var(--fg); }
.wrap { display: grid; grid-template-columns: minmax(0, 1.25fr) minmax(0, 1fr); gap: 20px; }
.col { max-height: 640px; overflow-y: auto; padding: 4px 8px 4px 0; }
.resp { white-space: pre-wrap; line-height: 1.75; }
.blk { border-radius: 4px; padding: 1px 2px; cursor: pointer; color: var(--blk-fg); }
.blk sup { font-size: 10px; color: #4b5563; margin-right: 2px; font-weight: 600; }
.blk.on, .card.on { outline: 2px solid var(--focus); }
.card { background: var(--card-bg); border: 1px solid var(--border); border-left: 6px solid; border-radius: 6px; padding: 8px 10px; margin-bottom: 10px; cursor: pointer; }
.title { font-weight: 700; margin-bottom: 4px; display: flex; align-items: center; gap: 6px; }
.dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; border: 1px solid var(--soft); }
.meta { font-size: 12px; color: var(--muted); }
blockquote { margin: 2px 0 8px; padding: 4px 8px; background: var(--quote-bg); border-left: 3px solid var(--rule); white-space: pre-wrap; }
.why { font-size: 13px; color: var(--muted); font-style: italic; }
.none { font-size: 13px; color: var(--soft); }
.badge { font-size: 11px; border-radius: 10px; padding: 1px 6px; margin-left: 4px; }
.badge.ok { background: var(--ok-bg); color: var(--ok-fg); } .badge.ko { background: var(--ko-bg); color: var(--ko-fg); }
h4 { margin: 4px 0 8px; }
.unused { margin-top: 14px; font-size: 13px; }
.unused li { margin-bottom: 4px; }
"""

JS = """
// Ajusta el tema al de Streamlit leyendo el fondo de la página padre (el
// iframe srcdoc comparte origen). Si no se puede, se queda el tema del servidor
// o, sin él, el del sistema operativo.
function applyTheme() {
  let dark = null;
  try {
    const app = window.parent.document.querySelector('.stApp') || window.parent.document.body;
    const m = getComputedStyle(app).backgroundColor.match(/\\d+(\\.\\d+)?/g);
    if (m && m.length >= 3) dark = (0.299 * m[0] + 0.587 * m[1] + 0.114 * m[2]) < 128;
  } catch (e) {}
  if (dark === null && !document.body.dataset.theme) {
    dark = window.matchMedia('(prefers-color-scheme: dark)').matches;
  }
  if (dark !== null) document.body.classList.toggle('dark', dark);
}
applyTheme();
try {
  new MutationObserver(applyTheme).observe(window.parent.document.head, {childList: true, subtree: true});
} catch (e) {}
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


def attribution_html(attribution: Attribution, theme: str | None = None, language: str | None = None) -> str:
    """Documento HTML autocontenido con la vista de atribución.

    ``theme`` ("light" o "dark") es el tema que Streamlit detectó; en el
    navegador se corrige leyendo el fondo real de la página. ``language``
    ("en" o "es") es el idioma de los textos; por defecto, el de la atribución.
    """
    tx = _texts(language or attribution.language)
    body_attrs = f' class="{theme}" data-theme="{theme}"' if theme in ("light", "dark") else ""
    cards = "".join(_card_html(b, i, tx) for i, b in enumerate(attribution.blocks))
    unused = attribution.unused_sources
    unused_html = ""
    if unused:
        items = "".join(f"<li><b>{u.id}</b> ({ORIGIN_LABEL[u.origin]}): {escape(u.text)}</li>" for u in unused)
        unused_html = f'<div class="unused"><h4>{tx["unused"]}</h4><ul>{items}</ul></div>'
    return (
        f"<!DOCTYPE html><html lang='{language or attribution.language}'><head><meta charset='utf-8'><style>{CSS}</style></head><body{body_attrs}>"
        '<div class="wrap">'
        f'<div class="col"><h4>{tx["response"]}</h4><div class="resp">{_response_html(attribution)}</div></div>'
        f'<div class="col"><h4>{tx["origin"]}</h4>{cards}{unused_html}</div>'
        f"</div><script>{JS}</script></body></html>"
    )
