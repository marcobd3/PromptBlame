"""Pruebas de seguridad y de robustez frente a entradas no confiables."""

import sys
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import promptblame
from promptblame.attribution import Attribution, attribute, parse_judgement
from promptblame.llm import LLM, LLMError, env_api_key
from promptblame.render import attribution_html
from promptblame.rewrite import parse_rewrite

APP = str(Path(__file__).parent.parent / "app.py")
SECRET = "sk-ant-secreta-de-prueba"


def test_env_api_key_is_not_sent_to_the_browser(monkeypatch):
    """La key del entorno no se precarga en el campo (su valor llega al navegador)."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", SECRET)
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    field = at.text_input(key="api_key_anthropic")
    assert field.value == ""
    assert SECRET not in repr(field.proto)


def test_llm_reads_key_from_environment(monkeypatch):
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "clave-local")
    assert env_api_key("compatible") == "clave-local"
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "clave-google")
    assert env_api_key("gemini") == "clave-google"


def test_llm_repr_does_not_include_secrets(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", SECRET)
    llm = LLM()
    assert SECRET not in repr(llm)
    assert SECRET not in str(vars(llm).get("api_key", ""))


@pytest.mark.parametrize("url", ["file:///etc/passwd", "localhost:11434", "ftp://x/v1", "http://"])
def test_base_url_must_be_http(url):
    with pytest.raises(LLMError, match="base URL"):
        LLM(model="llama3.3", provider="compatible", base_url=url, client=object())


def test_base_url_accepts_http_and_https():
    for url in ("http://localhost:11434/v1", "https://openrouter.ai/api/v1"):
        assert LLM(model="m", provider="compatible", base_url=url, client=object()).base_url == url


def test_parse_judgement_discards_malformed_items():
    data = {
        "segments": [
            "no es un objeto",
            {"id": 3, "sources": []},
            {"id": "R1", "sources": "S1", "explanation": None},
            {"id": "R2", "sources": [{"id": "S1", "confidence": "alta"}, {"confidence": "baja"}, 7]},
        ]
    }
    judged = parse_judgement(data)
    assert judged == {
        "R1": {"sources": [], "explanation": ""},
        "R2": {"sources": [{"id": "S1", "confidence": "alta"}], "explanation": ""},
    }
    assert parse_judgement({"segments": "x"}) == {}


def test_attribute_survives_malformed_judge_output():
    class Judge:
        def json(self, system, user, schema, effort="high"):
            return {"segments": [{"id": "R1", "sources": [{"id": "S99", "confidence": "<script>"}]}, None]}

    attr = attribute(Judge(), "Saluda.", "Hola", "¡Hola!")  # type: ignore[arg-type]
    assert len(attr.blocks) == 1
    assert attr.blocks[0].sources == []


def test_parse_rewrite_coerces_types():
    result = parse_rewrite(
        {"new_system_prompt": 5, "changes": [{"target": "S1", "action": "nueva"}, "x"], "summary": ["no"]}
    )
    assert result.new_system_prompt == ""
    assert result.summary == ""
    assert result.changes == [{"target": "S1", "action": "nueva", "description": "", "reason": ""}]


def test_html_view_escapes_prompt_and_response_content():
    payload = '<img src=x onerror="alert(1)"><script>alert(2)</script>'

    class Judge:
        def json(self, system, user, schema, effort="high"):
            return {"segments": [{"id": "R1", "sources": [{"id": "S1", "confidence": "alta"}], "explanation": payload}]}

    attr: Attribution = attribute(Judge(), payload, "Hola", payload)  # type: ignore[arg-type]
    html = attribution_html(attr, theme='dark" onload="alert(3)')
    assert "<img" not in html
    assert "<script>alert" not in html
    assert 'onload="alert(3)' not in html
    assert "&lt;script&gt;" in html


def test_public_api():
    assert promptblame.__version__
    for name in promptblame.__all__:
        assert hasattr(promptblame, name), name


def test_cli_runs_packaged_app(monkeypatch):
    from promptblame import cli

    seen: list[list[str]] = []

    def fake_main() -> int:
        seen.append(list(sys.argv))
        return 0

    monkeypatch.setattr(sys, "argv", ["promptblame"])
    monkeypatch.setattr("streamlit.web.cli.main", fake_main)
    assert cli.main(["--server.port", "8600"]) == 0
    assert seen == [["streamlit", "run", str(cli.APP_PATH), *cli.DEFAULT_ARGS, "--server.port", "8600"]]
    assert cli.APP_PATH.is_file()
