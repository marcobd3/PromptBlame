"""Tests de .env, confianza por bloque, puntuación causal, instrucciones muertas, CLI y API REST."""

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest

from promptblame import cli
from promptblame.api import create_app
from promptblame.attribution import Attribution, Block, SourceLink, attribute, verify_by_ablation
from promptblame.config import load_env, settings
from promptblame.dead import (
    dead_instructions,
    estimate_tokens,
    scan_dead_instructions,
    split_user_prompts,
    trim_system_prompt,
)
from promptblame.llm import LLM, LLMError
from promptblame.render import attribution_html
from promptblame.segmentation import segment

APP = str(Path(__file__).parent.parent / "app.py")

SYSTEM = """Eres un asistente de soporte.
Responde en español.
Nunca hables de política.
Termina ofreciendo ayuda."""

ENV_VARS = [
    "PROMPTBLAME_SERVICE_PROVIDER",
    "PROMPTBLAME_SERVICE_MODEL",
    "PROMPTBLAME_SERVICE_EFFORT",
    "PROMPTBLAME_JUDGE_PROVIDER",
    "PROMPTBLAME_JUDGE_MODEL",
    "PROMPTBLAME_JUDGE_EFFORT",
    "PROMPTBLAME_LANGUAGE",
    "PROMPTBLAME_ABLATION",
    "PROMPTBLAME_MAX_ABLATION",
    "PROMPTBLAME_API_TOKEN",
    "OPENAI_COMPATIBLE_BASE_URL",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    """Sin variables de PromptBlame y en un directorio sin .env.

    ``load_env`` escribe en ``os.environ`` por su cuenta, así que el entorno se
    restaura entero al terminar para no contaminar otros tests.
    """
    saved = dict(os.environ)
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    yield
    os.environ.clear()
    os.environ.update(saved)


def fake_text(self, system, user, effort="medium"):
    return "Hola. Lo siento por el retraso. ¿Te ayudo en algo más?"


def fake_json(self, system, user, schema, effort="high"):
    if "new_system_prompt" in schema["properties"]:
        return {"new_system_prompt": "Nuevo.", "changes": [], "summary": "Hecho."}
    return {
        "segments": [
            {"id": "R1", "sources": [{"id": "S2", "confidence": "alta"}], "explanation": "Idioma."},
            {"id": "R2", "sources": [], "explanation": ""},
            {"id": "R3", "sources": [{"id": "S4", "confidence": "baja"}], "explanation": "Ayuda."},
        ]
    }


@pytest.fixture
def fake_llm(monkeypatch):
    monkeypatch.setattr(LLM, "text", fake_text)
    monkeypatch.setattr(LLM, "json", fake_json)


# --- .env y ajustes -----------------------------------------------------------------


def test_load_env_fills_missing_variables_without_overriding(monkeypatch, tmp_path):
    (tmp_path / ".env").write_text(
        "PROMPTBLAME_JUDGE_PROVIDER=openai\nPROMPTBLAME_JUDGE_MODEL=gpt-x\nPROMPTBLAME_SERVICE_EFFORT=low\n"
        "PROMPTBLAME_ABLATION=true\nPROMPTBLAME_MAX_ABLATION=99\nANTHROPIC_API_KEY=from-file\n"
    )
    assert load_env() == str(tmp_path / ".env")
    assert os.environ["ANTHROPIC_API_KEY"] == "test"  # el entorno manda sobre el fichero
    cfg = settings()
    assert (cfg.judge.provider, cfg.judge.model, cfg.judge.effort) == ("openai", "gpt-x", "high")
    assert (cfg.service.provider, cfg.service.model, cfg.service.effort) == ("anthropic", "claude-opus-5-5", "low")
    assert cfg.ablation is True
    assert cfg.max_ablation == 30  # recortado al máximo


def test_invalid_settings_fall_back_to_defaults(monkeypatch):
    monkeypatch.setenv("PROMPTBLAME_SERVICE_PROVIDER", "nope")
    monkeypatch.setenv("PROMPTBLAME_JUDGE_EFFORT", "extreme")
    monkeypatch.setenv("PROMPTBLAME_LANGUAGE", "fr")
    cfg = settings()
    assert cfg.service.provider == "anthropic"
    assert cfg.judge.effort == "high"
    assert cfg.language is None
    assert load_env() is None  # no hay .env en el directorio temporal


def test_env_example_lists_every_setting():
    example = (Path(__file__).parent.parent / ".env.example").read_text()
    for name in [*ENV_VARS, "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY"]:
        assert f"{name}=" in example


def test_app_uses_env_defaults(monkeypatch, tmp_path, fake_llm):
    (tmp_path / ".env").write_text(
        "PROMPTBLAME_SERVICE_PROVIDER=openai\nPROMPTBLAME_SERVICE_MODEL=my-finetune\n"
        "PROMPTBLAME_JUDGE_EFFORT=max\nPROMPTBLAME_LANGUAGE=es\nOPENAI_API_KEY=sk-from-env-file\n"
    )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    assert at.selectbox(key="gen_provider").value == "openai"
    assert at.selectbox(key="gen_model_openai").value == "my-finetune"
    assert at.select_slider(key="judge_effort").value == "max"
    assert at.tabs[0].label.startswith("1 · Respuesta")
    key_box = at.text_input(key="api_key_openai")
    assert key_box.value == ""  # la key nunca se envía al navegador…
    assert "servidor" in key_box.placeholder  # …pero se indica que está configurada


# --- Confianza por bloque y puntuación causal ------------------------------------------


def _block(*links):
    return Block("B1", 0, 5, "Hola.", ["R1"], list(links), "")


def test_block_confidence_combines_judge_and_ablation():
    unit = segment("Saluda.", "system", "S")[0]
    assert _block().confidence is None
    assert _block().unsourced
    assert _block(SourceLink(unit, "alta")).confidence == "alta"
    assert _block(SourceLink(unit, "baja")).confidence == "baja"
    refuted = _block(SourceLink(unit, "alta", ablation_effect=0.0, causal_score=0.0))
    assert refuted.confidence_score == 0.45
    assert refuted.confidence == "media"
    confirmed = _block(SourceLink(unit, "media", ablation_effect=0.6, causal_score=0.9))
    assert confirmed.confidence == "alta"


def test_ablation_sets_causal_score():
    class Gen:
        def text(self, system, user, effort="medium"):
            return "Adiós." if "Saluda" not in system else "Hola."

    judge = type("J", (), {"json": lambda self, *a, **k: fake_judge_one()})()
    attr = attribute(judge, "Saluda.", "hola", "Hola.")
    verify_by_ablation(Gen(), attr)
    link = attr.blocks[0].sources[0]
    assert link.verified is True
    assert link.causal_score is not None
    assert 0.5 < link.causal_score <= 1.0
    assert attr.to_dict()["blocks"][0]["sources"][0]["causal_score"] == link.causal_score


def fake_judge_one():
    return {"segments": [{"id": "R1", "sources": [{"id": "S1", "confidence": "alta"}], "explanation": ""}]}


def test_unsourced_warning_and_confidence_in_html(fake_llm):
    attr = attribute(LLM(), SYSTEM, "hola", fake_text(None, "", ""))
    assert [b.id for b in attr.unsourced_blocks] == ["B2"]
    assert 0 < attr.unsourced_share < 1
    html = attribution_html(attr, language="en")
    assert 'class="warning"' in html
    assert "possible hallucination" in html
    assert 'class="blk nosrc"' in html
    assert 'class="blk low"' in html  # B3 tiene confianza baja
    assert "Block confidence" in html
    assert "posible alucinación" in attribution_html(attr, language="es")


# --- Instrucciones muertas -------------------------------------------------------------


def test_trim_system_prompt_removes_lines_and_sentences():
    text = "Eres un asistente.\n- Responde en español. Sé breve.\n\nNunca hables de política.\n\nFin."
    units = segment(text, "system", "S")
    assert trim_system_prompt(text, [units[2], units[3]]) == "Eres un asistente.\n- Responde en español.\n\nFin."
    assert trim_system_prompt(text, []) == text


def test_dead_instructions_aggregates_runs(fake_llm):
    attrs = [attribute(LLM(), SYSTEM, f"pregunta {i}", fake_text(None, "", "")) for i in range(3)]
    report = dead_instructions(attrs)
    assert report.runs == 3
    assert [u.unit.id for u in report.dead] == ["S1", "S3"]
    assert report.trimmed_system_prompt == "Responde en español.\nTermina ofreciendo ayuda."
    assert report.tokens_saved > 0
    assert report.tokens_before == estimate_tokens(SYSTEM)
    data = report.to_dict()
    assert data["dead"] == ["S1", "S3"]
    assert data["usage"][1]["cited_runs"] == 3
    with pytest.raises(ValueError, match="same system prompt"):
        dead_instructions([attrs[0], attribute(LLM(), "Otro.", "x", "Hola.")])


def test_dead_threshold_catches_rarely_cited():
    unit = segment(SYSTEM, "system", "S")
    attrs = []
    for i in range(4):
        links = [SourceLink(unit[1], "alta")] + ([SourceLink(unit[0], "baja")] if i == 0 else [])
        attrs.append(Attribution(SYSTEM, "u", "Hola.", unit, [], [Block("B1", 0, 5, "Hola.", ["R1"], links, "")]))
    assert [u.unit.id for u in dead_instructions(attrs).dead] == ["S3", "S4"]
    assert [u.unit.id for u in dead_instructions(attrs, threshold=0.25).dead] == ["S1", "S3", "S4"]


def test_scan_dead_instructions_skips_failed_runs(monkeypatch, fake_llm):
    calls = []

    def flaky(self, system, user, effort="medium"):
        calls.append(user)
        if user == "falla":
            raise LLMError("boom")
        return fake_text(self, system, user)

    monkeypatch.setattr(LLM, "text", flaky)
    report = scan_dead_instructions(LLM(), LLM(), SYSTEM, ["a", "falla", " "], runs_per_prompt=2)
    assert report.runs == 2  # las ejecuciones fallidas no cuentan
    assert report.errors == ["boom", "boom"]
    assert len(calls) == 4
    with pytest.raises(LLMError):
        scan_dead_instructions(LLM(), LLM(), SYSTEM, ["falla"])


def test_split_user_prompts():
    assert split_user_prompts("uno\n---\ndos\nlíneas\n---\n\n") == ["uno", "dos\nlíneas"]


def test_app_dead_instructions_tab(fake_llm):
    at = AppTest.from_file(APP, default_timeout=30).run()
    tab = at.tabs[2]
    assert tab.label.startswith("3 · Dead")
    at.text_area(key="dead_prompts").input("Where is my order?\n---\nCan I return it?").run()
    next(b for b in at.button if b.label == "Find dead instructions").click().run()
    assert not at.exception
    report = at.session_state.dead_report
    assert report.runs == 6  # 2 prompts × 3 ejecuciones
    assert report.dead
    next(b for b in at.button if b.key == "adopt_trimmed").click().run()
    assert at.text_area(key="system_prompt").value == report.trimmed_system_prompt
    assert at.session_state.versions


# El botón «Verify these links by ablation» vive dentro de st.dialog, que AppTest no
# vuelve a ejecutar como fragmento; se ha comprobado en el navegador con Playwright.


# --- CLI ----------------------------------------------------------------------------


def _files(tmp_path):
    (tmp_path / "system.txt").write_text(SYSTEM)
    (tmp_path / "user.txt").write_text("hola")
    (tmp_path / "prompts.jsonl").write_text('"uno"\n{"user_prompt": "dos"}\n')
    return tmp_path


def test_cli_attribute_json_and_checks(tmp_path, capsys, fake_llm):
    _files(tmp_path)
    code = cli.main(["attribute", "-s", "system.txt", "-u", "user.txt", "--json", "-o", "out.json"])
    assert code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["unsourced_blocks"] == ["B2"]
    assert json.loads((tmp_path / "out.json").read_text()) == data
    assert cli.main(["attribute", "-s", "system.txt", "-u", "user.txt", "--fail-on-unsourced", "0.1"]) == 3
    assert cli.main(["attribute", "-s", "system.txt", "-u", "user.txt", "--min-confidence", "0.5"]) == 3
    out = capsys.readouterr().out
    assert "no source" in out


def test_cli_dead_writes_trimmed_prompt(tmp_path, capsys, fake_llm):
    _files(tmp_path)
    args = ["dead", "-s", "system.txt", "-u", "prompts.jsonl", "--runs", "2", "--write-trimmed", "trim.txt"]
    assert cli.main(args) == 0
    assert "4 runs" in capsys.readouterr().out
    assert (tmp_path / "trim.txt").read_text() == "Responde en español.\nTermina ofreciendo ayuda.\n"
    assert cli.main([*args, "--fail-on-dead"]) == 3


def test_cli_rewrite_and_errors(tmp_path, capsys, fake_llm):
    _files(tmp_path)
    assert cli.main(["rewrite", "-s", "system.txt", "-u", "user.txt", "-i", "Más breve", "-o", "new.txt"]) == 0
    assert (tmp_path / "new.txt").read_text() == "Nuevo."
    assert cli.main(["attribute", "-s", "missing.txt", "-u", "user.txt"]) == 1
    assert "Error" in capsys.readouterr().err


def test_cli_without_subcommand_opens_ui(monkeypatch):
    seen = []
    monkeypatch.setattr(cli, "run_ui", lambda args: seen.append(args) or 0)
    assert cli.main([]) == 0
    assert cli.main(["--server.port", "8600"]) == 0
    assert cli.main(["ui", "--server.port", "1"]) == 0
    assert seen == [[], ["--server.port", "8600"], ["--server.port", "1"]]


# --- API REST -------------------------------------------------------------------------


def test_api_endpoints(fake_llm):
    client = TestClient(create_app())
    assert client.get("/health").json()["status"] == "ok"
    pair = {"system_prompt": SYSTEM, "user_prompt": "hola"}
    assert client.post("/generate", json=pair).json()["response"].startswith("Hola")
    attr = client.post("/attribute", json={**pair, "language": "es"}).json()
    assert attr["language"] == "es"
    assert attr["unsourced_blocks"] == ["B2"]
    assert attr["blocks"][0]["confidence"] == "alta"
    rewrite = client.post("/rewrite", json={**pair, "improvement": "Más breve"}).json()
    assert rewrite["new_system_prompt"] == "Nuevo."
    assert rewrite["diff"]
    dead = client.post("/dead-instructions", json={"system_prompt": SYSTEM, "user_prompts": ["a", "b"]}).json()
    assert dead["dead"] == ["S1", "S3"]
    assert client.post("/attribute", json={**pair, "judge": {"provider": "nope"}}).status_code == 422


def test_api_token_and_provider_errors(monkeypatch, fake_llm):
    monkeypatch.setenv("PROMPTBLAME_API_TOKEN", "s3cret")
    client = TestClient(create_app())
    pair = {"system_prompt": "a", "user_prompt": "b"}
    assert client.get("/health").status_code == 200
    assert client.post("/generate", json=pair).status_code == 401
    assert client.post("/generate", json=pair, headers={"Authorization": "Bearer nope"}).status_code == 401
    ok = client.post("/generate", json=pair, headers={"Authorization": "Bearer s3cret"})
    assert ok.status_code == 200

    def broken(self, system, user, effort="medium"):
        raise LLMError("Missing OpenAI API key.")

    monkeypatch.setattr(LLM, "text", broken)
    failed = client.post("/generate", json=pair, headers={"Authorization": "Bearer s3cret"})
    assert failed.status_code == 502
    assert failed.json()["detail"] == "Missing OpenAI API key."


def test_api_never_takes_base_url_from_request(monkeypatch, fake_llm):
    seen = []
    original = LLM.__init__

    def spy(self, *args, **kwargs):
        kwargs.setdefault("client", object())
        original(self, *args, **kwargs)
        seen.append(self.base_url)

    monkeypatch.setattr(LLM, "__init__", spy)
    monkeypatch.setenv("OPENAI_COMPATIBLE_BASE_URL", "http://localhost:9999/v1")
    client = TestClient(create_app())
    body = {
        "system_prompt": "a",
        "user_prompt": "b",
        "service": {"provider": "compatible", "base_url": "http://169.254.169.254/"},
    }
    assert client.post("/generate", json=body).status_code == 200
    assert seen == ["http://localhost:9999/v1"]
