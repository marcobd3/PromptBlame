"""Prueba de humo de la interfaz con Streamlit AppTest y la API simulada."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

from promptblame.llm import LLM


def fake_text(self, system, user, effort="medium"):
    return "Lo siento por el retraso. ¿Me das tu número de pedido? ¿Te ayudo en algo más?"


json_calls = []


def fake_json(self, system, user, schema, effort="high"):
    json_calls.append((system, schema))
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
    # Pestaña 1: entrada a la izquierda, salida a la derecha y, debajo, la atribución con sus criterios.
    tab1 = at.tabs[0]
    assert [t.key for t in tab1.columns[0].text_area] == ["system_prompt", "user_prompt"]
    assert [t.key for t in tab1.columns[1].text_area] == ["response"]
    assert at.tabs[0].label.startswith("1 · Response")  # inglés por defecto
    keys = [t.key for t in at.tabs[0].text_area]
    assert keys == ["system_prompt", "user_prompt", "response", "judge_instructions"]
    assert not at.expander  # los criterios ya no van en un desplegable sobre las pestañas

    at.button[0].click().run()  # Generar respuesta
    assert at.text_area(key="response").value.startswith("Lo siento")

    at.button[1].click().run()  # Ver atribución
    assert not at.exception
    assert at.session_state.attribution is not None
    assert len(at.session_state.attribution.blocks) == 3

    at.text_area(key="judge_instructions").input("Sé estricto con la confianza.").run()
    assert at.session_state.attribution is None  # cambiar los criterios invalida la atribución
    at.checkbox(key="instructions_in_rewrite").uncheck().run()

    next(t for t in at.text_area if t.label == "What do you want to improve?").input("Más breve").run()
    gen = next(b for b in at.button if b.label.startswith("Generate new system prompt"))
    gen.click().run()
    assert at.session_state.rewrite.new_system_prompt == "Nuevo prompt."
    assert at.session_state.attribution.instructions == "Sé estricto con la confianza."
    judge_systems = [s for s, schema in json_calls if "segments" in schema["properties"]]
    rewrite_systems = [s for s, schema in json_calls if "new_system_prompt" in schema["properties"]]
    assert "Sé estricto con la confianza." in judge_systems[-1]
    assert "Sé estricto con la confianza." not in rewrite_systems[-1]
    adopt = next(b for b in at.button if b.label.startswith("Use this version"))
    adopt.click().run()
    assert at.text_area(key="system_prompt").value == "Nuevo prompt."
    assert at.session_state.versions


def test_app_with_other_providers(monkeypatch):
    """Servicio con OpenAI y juez con Gemini: se construyen con su proveedor."""
    built = []
    original_init = LLM.__init__

    def spy_init(self, *args, **kwargs):
        kwargs.setdefault("client", object())
        original_init(self, *args, **kwargs)
        built.append((self.provider, self.model))

    monkeypatch.setattr(LLM, "__init__", spy_init)
    monkeypatch.setattr(LLM, "text", fake_text)
    monkeypatch.setattr(LLM, "json", fake_json)

    at = AppTest.from_file(str(Path(__file__).parent.parent / "app.py"), default_timeout=30).run()
    at.selectbox(key="gen_provider").set_value("openai").run()
    at.selectbox(key="judge_provider").set_value("gemini").run()
    assert not at.exception
    assert at.text_input(key="api_key_openai") is not None
    assert at.text_input(key="api_key_gemini") is not None

    at.button[0].click().run()
    at.button[1].click().run()
    assert not at.exception
    assert ("openai", "gpt-6.1-sol") in built
    assert ("gemini", "gemini-4-argon") in built


def test_root_app_uses_repo_code(monkeypatch, tmp_path):
    """``streamlit run app.py`` ejecuta el código de src/, no un paquete instalado antiguo."""
    import sys

    stale = tmp_path / "promptblame"
    stale.mkdir()
    (stale / "__init__.py").write_text("")
    (stale / "app.py").write_text("import streamlit as st\nst.write('VERSION ANTIGUA')\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    for name in [m for m in sys.modules if m == "promptblame" or m.startswith("promptblame.")]:
        monkeypatch.delitem(sys.modules, name)

    at = AppTest.from_file(str(Path(__file__).parent.parent / "app.py"), default_timeout=30).run()
    assert not at.exception
    assert not any("VERSION ANTIGUA" in m.value for m in at.markdown)
    assert at.text_area(key="judge_instructions") is not None


def test_app_in_spanish(monkeypatch):
    """Con el idioma en español, la interfaz, los ejemplos y el juez van en español."""
    monkeypatch.setattr(LLM, "text", fake_text)
    monkeypatch.setattr(LLM, "json", fake_json)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")

    at = AppTest.from_file(str(Path(__file__).parent.parent / "app.py"), default_timeout=30).run()
    assert "online bicycle shop" in at.text_area(key="system_prompt").value
    at.selectbox(key="lang").set_value("es").run()
    assert not at.exception
    assert at.tabs[0].label.startswith("1 · Respuesta")
    assert "tienda online de bicicletas" in at.text_area(key="system_prompt").value
    assert at.text_area(key="judge_instructions").label == "Instrucciones de atribución (opcional)"

    json_calls.clear()
    at.button[0].click().run()
    at.button[1].click().run()
    assert at.session_state.attribution.language == "es"
    assert "escrita en español" in json_calls[-1][0]
