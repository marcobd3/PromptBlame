"""Pruebas de los proveedores OpenAI, Gemini y compatibles con clientes simulados."""

import json
from types import SimpleNamespace

import openai
import pytest

try:  # los SDK recientes usan httpx2
    import httpx2 as httpx
except ImportError:  # pragma: no cover
    import httpx

from promptblame.attribution import ATTRIBUTION_SCHEMA, attribute
from promptblame.llm import LLM, PROVIDERS, LLMError, extract_json


def _openai_response(content, finish="stop", refusal=None):
    message = SimpleNamespace(content=content, refusal=refusal)
    return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason=finish)])


def _bad_request(msg="response_format no soportado"):
    request = httpx.Request("POST", "http://x/v1/chat/completions")
    return openai.BadRequestError(msg, response=httpx.Response(400, request=request), body=None)


class FakeChat:
    def __init__(self, handler):
        self.handler = handler
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.handler(kwargs)


def fake_openai(handler, model="gpt-6.1-sol", provider="openai"):
    chat = FakeChat(handler)
    client = SimpleNamespace(chat=SimpleNamespace(completions=chat))
    base_url = "http://localhost:11434/v1" if provider == "compatible" else None
    return LLM(model=model, provider=provider, client=client, base_url=base_url), chat


class FakeGeminiModels:
    def __init__(self, handler):
        self.handler = handler
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return self.handler(kwargs)


def fake_gemini(handler, model="gemini-4-argon"):
    models = FakeGeminiModels(handler)
    return LLM(model=model, provider="gemini", client=SimpleNamespace(models=models)), models


def _gemini_response(text, finish="STOP"):
    return SimpleNamespace(
        text=text,
        prompt_feedback=None,
        candidates=[SimpleNamespace(finish_reason=finish)],
    )


JUDGED = {"segments": [{"id": "R1", "sources": [{"id": "S1", "confidence": "alta"}], "explanation": "Saludo."}]}


# --- Registro de proveedores -----------------------------------------------------


def test_providers_registry():
    assert list(PROVIDERS) == ["anthropic", "openai", "gemini", "compatible"]
    assert PROVIDERS["anthropic"].models[0] == "claude-opus-5-5"
    assert PROVIDERS["compatible"].needs_base_url
    assert not PROVIDERS["compatible"].key_required


def test_unknown_provider_and_missing_base_url():
    with pytest.raises(LLMError, match="desconocido"):
        LLM(model="x", provider="nope", client=object())
    with pytest.raises(LLMError, match="URL base"):
        LLM(model="llama3.3", provider="compatible")


def test_extract_json_tolerates_fences_and_text():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Aquí tienes: {"a": {"b": 2}} ¡listo!') == {"a": {"b": 2}}
    with pytest.raises(LLMError, match="JSON"):
        extract_json("nada")


# --- OpenAI ---------------------------------------------------------------------


def test_openai_text_sends_system_and_effort():
    llm, chat = fake_openai(lambda kw: _openai_response("hola"))
    assert llm.text("Eres breve.", "Hola", effort="xhigh") == "hola"
    call = chat.calls[0]
    assert call["messages"][0] == {"role": "system", "content": "Eres breve."}
    assert call["reasoning_effort"] == "xhigh"
    assert "response_format" not in call


def test_openai_no_effort_for_non_reasoning_model():
    llm, chat = fake_openai(lambda kw: _openai_response("hola"), model="gpt-4.1")
    llm.text("", "Hola")
    assert "reasoning_effort" not in chat.calls[0]
    assert chat.calls[0]["messages"] == [{"role": "user", "content": "Hola"}]


def test_openai_json_uses_strict_schema_for_attribution():
    llm, chat = fake_openai(lambda kw: _openai_response(json.dumps(JUDGED)))
    attr = attribute(llm, "Saluda.", "Hola", "¡Hola!")
    fmt = chat.calls[0]["response_format"]
    assert fmt["type"] == "json_schema"
    assert fmt["json_schema"]["strict"] is True
    assert fmt["json_schema"]["schema"] == ATTRIBUTION_SCHEMA
    assert attr.blocks[0].sources[0].unit.id == "S1"


def test_openai_refusal_and_length():
    llm, _ = fake_openai(lambda kw: _openai_response(None, refusal="No."))
    with pytest.raises(LLMError, match="rechazó"):
        llm.text("", "u")
    llm, _ = fake_openai(lambda kw: _openai_response("cort", finish="length"))
    with pytest.raises(LLMError, match="cortó"):
        llm.text("", "u")


# --- Compatible con OpenAI -----------------------------------------------------------


def test_compatible_falls_back_when_json_schema_unsupported():
    def handler(kw):
        fmt = kw.get("response_format", {}).get("type")
        if fmt in ("json_schema", "json_object"):
            raise _bad_request()
        assert "JSON Schema" in kw["messages"][0]["content"]
        return _openai_response("```json\n" + json.dumps(JUDGED) + "\n```")

    llm, chat = fake_openai(handler, model="llama3.3", provider="compatible")
    assert llm.json("Juez.", "datos", ATTRIBUTION_SCHEMA, effort="max") == JUDGED
    assert [c.get("response_format", {}).get("type") for c in chat.calls] == ["json_schema", "json_object", None]
    assert all("reasoning_effort" not in c for c in chat.calls)


def test_compatible_reports_last_bad_request():
    def handler(kw):
        raise _bad_request("modelo roto")

    llm, _ = fake_openai(handler, model="llama3.3", provider="compatible")
    with pytest.raises(LLMError, match="modelo roto"):
        llm.json("s", "u", {"type": "object"})


# --- Gemini ---------------------------------------------------------------------


def test_gemini_json_and_thinking_level():
    llm, models = fake_gemini(lambda kw: _gemini_response(json.dumps(JUDGED)))
    assert llm.json("Juez.", "datos", ATTRIBUTION_SCHEMA, effort="max") == JUDGED
    call = models.calls[0]
    assert call["model"] == "gemini-4-argon"
    assert call["contents"] == "datos"
    config = call["config"]
    assert config["system_instruction"] == "Juez."
    assert config["response_mime_type"] == "application/json"
    assert config["response_json_schema"] == ATTRIBUTION_SCHEMA
    assert config["thinking_config"] == {"thinking_level": "HIGH"}


def test_gemini_text_without_system_or_thinking_for_old_models():
    llm, models = fake_gemini(lambda kw: _gemini_response("hola"), model="gemini-2.5-flash")
    assert llm.text("", "u", effort="low") == "hola"
    assert models.calls[0]["config"] == {}


def test_gemini_max_tokens_and_api_errors():
    llm, _ = fake_gemini(lambda kw: _gemini_response("cort", finish="FinishReason.MAX_TOKENS"))
    with pytest.raises(LLMError, match="cortó"):
        llm.text("", "u")

    from google.genai import errors

    def boom(kw):
        raise errors.ClientError(404, {"error": {"code": 404, "message": "no existe", "status": "NOT_FOUND"}})

    llm, _ = fake_gemini(boom, model="gemini-99")
    with pytest.raises(LLMError, match="no está disponible"):
        llm.text("", "u")
