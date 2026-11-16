import json
from types import SimpleNamespace

import pytest

from promptblame.attribution import attribute, merge_blocks, similarity, verify_by_ablation
from promptblame.llm import LLM, LLMError
from promptblame.render import attribution_html
from promptblame.rewrite import attribution_report, rewrite_system_prompt, unified_diff
from promptblame.segmentation import remove_unit, segment

SYSTEM = """Eres un asistente de cocina.
- Responde siempre en español.
- Usa listas numeradas para los pasos."""
USER = "¿Cómo hago una tortilla de patatas? Somos cuatro."
RESPONSE = """Aquí tienes la receta para cuatro personas.

1. Pela y corta las patatas.
2. Fríelas a fuego lento.

¡Buen provecho!"""


class FakeMessages:
    def __init__(self, handler):
        self.handler = handler
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        text, stop = self.handler(kwargs)
        return SimpleNamespace(
            stop_reason=stop, content=[SimpleNamespace(type="text", text=text)]
        )


def fake_llm(handler, model="claude-opus-5-5"):
    messages = FakeMessages(handler)
    client = SimpleNamespace(beta=SimpleNamespace(messages=messages))
    return LLM(model=model, client=client), messages


# --- Segmentación ---------------------------------------------------------------


def test_segment_offsets_are_exact():
    units = segment(SYSTEM, "system", "S")
    assert [u.id for u in units] == ["S1", "S2", "S3"]
    for u in units:
        assert SYSTEM[u.start : u.end] == u.text
    assert units[1].text == "- Responde siempre en español."


def test_segment_splits_sentences_and_keeps_code_blocks():
    text = "Primera frase. ¿Segunda? Sí.\n```python\nx = 1. y = 2\n```\nFin."
    texts = [u.text for u in segment(text, "response", "R")]
    assert texts[:3] == ["Primera frase.", "¿Segunda?", "Sí."]
    assert texts[3].startswith("```python") and texts[3].endswith("```")
    assert texts[4] == "Fin."


def test_remove_unit():
    units = segment("Uno. Dos. Tres.", "user", "U")
    assert remove_unit("Uno. Dos. Tres.", units[1]) == "Uno. Tres."


# --- Atribución -----------------------------------------------------------------


def judge_handler(kwargs):
    request = kwargs["messages"][0]["content"]
    assert "[S2] - Responde siempre en español." in request
    assert "[U2] Somos cuatro." in request
    segments = [
        {"id": "R1", "sources": [{"id": "U2", "confidence": "alta"}, {"id": "S2", "confidence": "media"}], "explanation": "Cuatro personas."},
        {"id": "R2", "sources": [{"id": "S3", "confidence": "alta"}, {"id": "U1", "confidence": "alta"}], "explanation": "Pasos numerados."},
        {"id": "R3", "sources": [{"id": "S3", "confidence": "media"}, {"id": "U1", "confidence": "alta"}], "explanation": "Más pasos."},
        {"id": "R4", "sources": [{"id": "S99", "confidence": "alta"}], "explanation": ""},
    ]
    return json.dumps({"segments": segments}), "end_turn"


def test_attribute_merges_contiguous_segments_and_drops_unknown_ids():
    llm, messages = fake_llm(judge_handler)
    attr = attribute(llm, SYSTEM, USER, RESPONSE)
    call = messages.calls[0]
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert call["fallbacks"] == "default"

    assert [b.segment_ids for b in attr.blocks] == [["R1"], ["R2", "R3"], ["R4"]]
    steps = attr.blocks[1]
    assert steps.text == "1. Pela y corta las patatas.\n2. Fríelas a fuego lento."
    assert [link.unit.id for link in steps.sources] == ["S3", "U1"]
    assert attr.blocks[2].sources == []  # S99 no existe
    assert [u.id for u in attr.unused_sources] == ["S1"]


def test_missing_segments_are_reported():
    llm, _ = fake_llm(lambda kw: (json.dumps({"segments": []}), "end_turn"))
    attr = attribute(llm, SYSTEM, USER, RESPONSE)
    assert all(b.sources == [] for b in attr.blocks)
    assert "R1" in attr.notes[0]


def test_merge_blocks_keeps_order_of_response():
    segs = segment(RESPONSE, "response", "R")
    blocks = merge_blocks(RESPONSE, segs, {}, [])
    # Sin fuentes, los segmentos se agrupan por párrafo.
    assert [b.text for b in blocks] == [p for p in RESPONSE.split("\n\n")]


# --- Ablación -------------------------------------------------------------------


def test_similarity():
    assert similarity("Pela las patatas.", "Primero, pela las patatas.") > 0.7
    assert similarity("Pela las patatas.", "Hoy hace sol en Madrid.") < 0.5
    assert similarity("Algo.", "") == 0.0


def test_verify_by_ablation_confirms_real_dependencies():
    llm, _ = fake_llm(judge_handler)
    attr = attribute(llm, SYSTEM, USER, RESPONSE)

    def generator(kwargs):
        system = kwargs.get("system", "")
        user = kwargs["messages"][0]["content"]
        if "listas numeradas" not in system:  # sin S3 los pasos cambian
            return "Aquí tienes la receta para cuatro personas. Pela, corta y fríe todo junto. ¡Buen provecho!", "end_turn"
        if "cuatro" not in user:  # sin U2 cambia la primera frase
            return RESPONSE.replace("para cuatro personas", "básica"), "end_turn"
        return RESPONSE, "end_turn"

    gen, calls = fake_llm(generator)
    verify_by_ablation(gen, attr, max_sources=10)
    assert attr.ablation_done
    assert len(calls.calls) == 1 + 4  # control + S2, S3, U1, U2

    first, steps = attr.blocks[0], attr.blocks[1]
    effects = {link.unit.id: link for link in first.sources + steps.sources}
    assert effects["S3"].verified is True
    assert effects["U2"].verified is True
    assert effects["S2"].verified is False


# --- Reescritura y vista ----------------------------------------------------------


def test_rewrite_uses_attribution_map():
    llm, _ = fake_llm(judge_handler)
    attr = attribute(llm, SYSTEM, USER, RESPONSE)

    def rewriter(kwargs):
        request = kwargs["messages"][0]["content"]
        assert "<mapa_de_atribucion>" in request and "Instrucciones sin efecto visible: S1" in request
        assert "Más corto" in request
        payload = {
            "new_system_prompt": SYSTEM + "\n- Sé breve.",
            "changes": [{"target": "nueva", "action": "nueva", "description": "Brevedad", "reason": "Pedido"}],
            "summary": "Añade brevedad.",
        }
        return json.dumps(payload), "end_turn"

    rw_llm, _ = fake_llm(rewriter)
    result = rewrite_system_prompt(rw_llm, attr, "Más corto")
    assert result.new_system_prompt.endswith("- Sé breve.")
    assert "+- Sé breve." in unified_diff(SYSTEM, result.new_system_prompt)
    assert "B2" in attribution_report(attr)


def test_html_contains_blocks_quotes_and_escapes():
    llm, _ = fake_llm(judge_handler)
    attr = attribute(llm, SYSTEM, USER + " <b>", RESPONSE)
    html = attribution_html(attr)
    assert html.count('class="blk"') == len(attr.blocks)
    assert 'id="card-B2"' in html
    assert "Usa listas numeradas para los pasos." in html
    assert "&lt;b&gt;" in html or "<b>" not in USER
    assert "Instrucciones sin efecto visible" in html


# --- LLM -------------------------------------------------------------------------


def test_refusal_raises_readable_error():
    llm, _ = fake_llm(lambda kw: ("", "refusal"))
    with pytest.raises(LLMError, match="rechazó"):
        llm.text("s", "u")


def test_no_fallbacks_for_models_without_support():
    llm, messages = fake_llm(lambda kw: ("hola", "end_turn"), model="claude-haiku-5-5")
    assert llm.text("", "u") == "hola"
    call = messages.calls[0]
    assert "fallbacks" not in call and "system" not in call
    assert call["output_config"] == {"effort": "medium"}


def test_segment_does_not_split_list_markers_or_abbreviations():
    texts = [u.text for u in segment("1. Pela las patatas. Luego sálalas.\nHabla con el Sr. Pérez.", "r", "R")]
    assert texts == ["1. Pela las patatas.", "Luego sálalas.", "Habla con el Sr. Pérez."]


def test_html_theme_class():
    llm, _ = fake_llm(judge_handler)
    attr = attribute(llm, SYSTEM, USER, RESPONSE)
    assert '<body class="dark" data-theme="dark">' in attribution_html(attr, theme="dark")
    assert "<body>" in attribution_html(attr)
    assert "body.dark" in attribution_html(attr)
