"""Regressao: response_format=json_object exige a palavra "json" na mensagem.

DeepSeek oficial devolve 400 ("Prompt must contain the word 'json' ...")
quando o modo JSON e usado sem a palavra no request — incidente 2026-09-10:
chat sem ticker morreu com BadRequestError e serviu fallback enlatado.
"""

from types import SimpleNamespace

import core.model_serving.gateway as gateway_module
from core.model_serving.gateway import ModelGateway, _ensure_json_word
from core.model_serving.providers import GatewayConfig, ModelProvider


class _FakeStream:
    def __init__(self, text):
        self._text = text

    def __aiter__(self):
        async def gen():
            yield SimpleNamespace(
                choices=[
                    SimpleNamespace(delta=SimpleNamespace(content=self._text, reasoning_content=""))
                ]
            )

        return gen()


class _FakeCompletions:
    def __init__(self, sink):
        self._sink = sink

    async def create(self, **kwargs):
        self._sink.append(kwargs)
        if kwargs.get("stream"):
            return _FakeStream("ok")
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok", reasoning_content=""))]
        )


class _FakeClient:
    def __init__(self, sink):
        self.chat = SimpleNamespace(completions=_FakeCompletions(sink))

    async def close(self):
        return None


def _provider():
    return ModelProvider(
        name="agent",
        base_url="https://api.deepseek.com",
        api_key="test-key",
        model="deepseek-v4-pro",
    )


def _gateway(monkeypatch):
    calls = []
    monkeypatch.setattr(gateway_module, "AsyncOpenAI", lambda **kwargs: _FakeClient(calls))
    gw = ModelGateway(
        providers=[_provider()],
        config=GatewayConfig(max_fallbacks=1, retry_attempts=1, retry_delay_s=0),
    )
    return gw, calls


def _messages_text(kwargs):
    return "\n".join(str(m.get("content")) for m in kwargs["messages"])


async def test_generate_api_injects_json_word(monkeypatch):
    gw, calls = _gateway(monkeypatch)
    await gw.generate_api(gw.providers[0], prompt="responda apenas: ok", json_mode=True)
    assert calls[0]["response_format"] == {"type": "json_object"}
    assert "json" in _messages_text(calls[0]).lower()


async def test_generate_api_keeps_existing_json_prompt(monkeypatch):
    gw, calls = _gateway(monkeypatch)
    await gw.generate_api(
        gw.providers[0], system_prompt="Responda em JSON.", prompt="ok", json_mode=True
    )
    assert calls[0]["messages"][0]["content"] == "Responda em JSON."


async def test_generate_api_without_json_mode_does_not_inject(monkeypatch):
    gw, calls = _gateway(monkeypatch)
    await gw.generate_api(gw.providers[0], prompt="responda apenas: ok", json_mode=False)
    assert "response_format" not in calls[0]
    assert "json" not in _messages_text(calls[0]).lower()


async def test_stream_api_injects_json_word(monkeypatch):
    gw, calls = _gateway(monkeypatch)
    chunks = [
        chunk
        async for chunk in gw.stream_generate_api(
            gw.providers[0], prompt="responda apenas: ok", json_mode=True
        )
    ]
    assert "".join(chunks) == "ok"
    assert calls[0]["response_format"] == {"type": "json_object"}
    assert "json" in _messages_text(calls[0]).lower()


def test_ensure_json_word_is_idempotent():
    messages = [
        {"role": "system", "content": "Voce e um assistente."},
        {"role": "user", "content": "resuma"},
    ]
    _ensure_json_word(messages)
    snapshot = [dict(m) for m in messages]
    assert "json" in messages[0]["content"].lower()
    _ensure_json_word(messages)
    assert messages == snapshot


def test_ensure_json_word_uses_last_user_message_without_system():
    messages = [{"role": "user", "content": "resuma"}]
    _ensure_json_word(messages)
    assert "json" in messages[0]["content"].lower()
