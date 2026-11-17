"""Segmentación determinista de texto en unidades con offsets de caracteres.

Las unidades de los prompts son las "instrucciones" que se pueden citar; las
unidades de la respuesta son los trozos mínimos que se atribuyen. Como los
offsets se calculan aquí (y no los devuelve el modelo), las citas que se
muestran son siempre literales.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Fin de frase seguido de espacio y de algo que parece el inicio de otra frase.
_SENTENCE_BREAK = re.compile(r"(?<=[.!?…])[\"'»)\]]*\s+(?=[\"'«(¿¡\[]?[A-ZÁÉÍÓÚÜÑ0-9])")
_FENCE = re.compile(r"^\s*(```|~~~)")
# Un corte no es fin de frase si el trozo es sólo un marcador de lista ("1.",
# "a)") o termina en una abreviatura habitual ("Sr.", "p. ej.", "e.g.").
_LIST_MARKER = re.compile(r"^\s*(\d+|[A-Za-z])[.)]$")
_ABBREVIATION = re.compile(
    r"(?:^|[\s(])(sr|sra|srta|dr|dra|d|dña|ud|uds|etc|p|ej|pág|págs|núm|aprox|vs|cf|mr|mrs|ms|"
    r"e\.g|i\.e|approx|no|art|cap|fig|vol)\.$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Unit:
    """Un trozo de texto identificado y localizado en su texto de origen."""

    id: str
    origin: str  # "system", "user" o "response"
    start: int
    end: int
    text: str


def _line_spans(text: str) -> list[tuple[int, int]]:
    spans = []
    pos = 0
    for line in text.splitlines(keepends=True):
        spans.append((pos, pos + len(line.rstrip("\r\n"))))
        pos += len(line)
    return spans


def _split_sentences(text: str, start: int, end: int) -> list[tuple[int, int]]:
    chunk = text[start:end]
    spans = []
    cursor = 0
    for match in _SENTENCE_BREAK.finditer(chunk):
        spans.append((start + cursor, start + match.start()))
        cursor = match.end()
    spans.append((start + cursor, end))
    merged: list[tuple[int, int]] = []
    for span in spans:
        prev = text[merged[-1][0] : merged[-1][1]] if merged else ""
        if merged and (_LIST_MARKER.match(prev) or _ABBREVIATION.search(prev)):
            merged[-1] = (merged[-1][0], span[1])
        else:
            merged.append(span)
    return merged


def _strip(text: str, start: int, end: int) -> tuple[int, int] | None:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return (start, end) if end > start else None


def segment(text: str, origin: str, prefix: str) -> list[Unit]:
    """Divide ``text`` en unidades (líneas, viñetas y frases).

    - Cada línea no vacía es al menos una unidad (las viñetas y los títulos
      suelen ser instrucciones independientes).
    - Las líneas largas se dividen además en frases.
    - Un bloque de código delimitado con ``` es una sola unidad.
    """
    raw: list[tuple[int, int]] = []
    lines = _line_spans(text)
    i = 0
    while i < len(lines):
        start, end = lines[i]
        if _FENCE.match(text[start:end]):
            j = i + 1
            while j < len(lines) and not _FENCE.match(text[lines[j][0] : lines[j][1]]):
                j += 1
            block_end = lines[min(j, len(lines) - 1)][1]
            raw.append((start, block_end))
            i = j + 1
            continue
        raw.extend(_split_sentences(text, start, end))
        i += 1

    units: list[Unit] = []
    for span in raw:
        stripped = _strip(text, *span)
        if stripped is None:
            continue
        s, e = stripped
        units.append(Unit(f"{prefix}{len(units) + 1}", origin, s, e, text[s:e]))
    return units


def remove_unit(text: str, unit: Unit) -> str:
    """Devuelve ``text`` sin la unidad (para la verificación por ablación)."""
    before, after = text[: unit.start], text[unit.end :]
    if before.endswith(" ") and after.startswith(" "):
        after = after[1:]
    return before + after
