"""Prueba de humo de la interfaz con Streamlit AppTest y la API simulada."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

from promptblame.llm import LLM


def fake_text(self, system, user, effort="medium"):
    return "Lo siento por el retraso. ¿Me das tu número de pedido? ¿Te ayudo en algo más?"


def fake_json(self, system, user, schema, effort="high"):
    if "new_system_prompt" in schema["properties"]:
        return {"new_system_prompt": "Nuevo prompt.", "changes": [], "summary": "Hecho."}
    return {
        "segments": [
            {"id": "R1", "sources": [{"id": "S2", "confidence": "alta"}], "explanation": "Tono."},
            {"id": "R2", "sources": [{"id": "S4", "confidence": "alta"}], "explanation": "Pide pedido."},
            {"id": "R3", "sources": [{"id": "S6", "confidence": "alta"}], "explanation": "Ofrece ayuda."},
        ]
    }


def test_app_end_to_end(monkeypatch):
    monkeypatch.setattr(LLM, "text", fake_text)
    monkeypatch.setattr(LLM, "json", fake_json)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")

    at = AppTest.from_file(str(Path(__file__).parent.parent / "app.py"), default_timeout=30).run()
    assert not at.exception

    at.button[0].click().run()  # Generar respuesta
    assert at.text_area(key="response").value.startswith("Lo siento")

    at.button[1].click().run()  # Ver atribución
    assert not at.exception
    assert at.session_state.attribution is not None
    assert len(at.session_state.attribution.blocks) == 3

    at.text_area[3].input("Más breve").run()  # mejora (pestaña 2)
    gen = next(b for b in at.button if b.label.startswith("Generar nueva versión"))
    gen.click().run()
    assert at.session_state.rewrite.new_system_prompt == "Nuevo prompt."
    adopt = next(b for b in at.button if b.label.startswith("Usar esta versión"))
    adopt.click().run()
    assert at.text_area(key="system_prompt").value == "Nuevo prompt."
    assert at.session_state.versions
