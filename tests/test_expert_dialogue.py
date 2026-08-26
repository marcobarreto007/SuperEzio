from typing import ClassVar

import pytest

from core.pipeline.nodes.expert_dialogue import ExpertDialogue, extract_verdict_payload


class RecordingGateway:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def chat_completion(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


@pytest.mark.asyncio
async def test_expert_dialogue_ask_and_follow_up_include_history():
    gateway = RecordingGateway(
        [
            '{"verdict":"OVERVALUED","confidence":68,"bob_readable":"DCF below market."}',
            '{"verdict":"WAIT","confidence":78,"bob_readable":"Still below fair value."}',
        ]
    )
    dialogue = ExpertDialogue(gateway, max_rounds=3)

    first = await dialogue.ask(
        "fundamental_value",
        "deepseek",
        "system",
        "Initial DCF context",
    )
    second = await dialogue.follow_up(
        "fundamental_value",
        "deepseek",
        "But what if growth is 5 percent?",
    )
    verdict = dialogue.get_verdict()

    assert first["ok"] is True
    assert second["ok"] is True
    assert len(gateway.calls) == 2
    assert "Initial DCF context" in gateway.calls[1]["messages"][1]["content"]
    assert "But what if growth is 5 percent?" in gateway.calls[1]["messages"][1]["content"]
    assert verdict["verdict"] == "WAIT"
    assert verdict["confidence"] == 78.0
    assert verdict["rounds"] == 2


@pytest.mark.asyncio
async def test_expert_dialogue_respects_max_rounds():
    gateway = RecordingGateway(['{"verdict":"NEUTRAL","confidence":50}'])
    dialogue = ExpertDialogue(gateway, max_rounds=1)

    await dialogue.ask("sentiment", "gemini", "system", "context")
    skipped = await dialogue.follow_up("sentiment", "gemini", "Need refinement")

    assert skipped["skipped"] is True
    assert skipped["error"] == "max_rounds_reached"
    assert len(gateway.calls) == 1
    assert dialogue.get_verdict()["verdict"] == "NEUTRAL"


def test_extract_verdict_payload_supports_text_fallback():
    payload = extract_verdict_payload("This looks suspicious. Confidence: 72.")

    assert payload["verdict"] == "SUSPICIOUS"
    assert payload["confidence"] == 72.0


@pytest.mark.asyncio
async def test_expert_dialogue_respects_external_limits_and_disables_fallback(monkeypatch):
    monkeypatch.delenv("SUPEREZIO_DEEPSEEK_MAX_TOKENS", raising=False)
    monkeypatch.delenv("SUPEREZIO_DEEPSEEK_TIMEOUT_SEC", raising=False)
    monkeypatch.setenv("SUPEREZIO_EXPERT_MAX_TOKENS", "2000")
    monkeypatch.setenv("SUPEREZIO_EXPERT_TIMEOUT", "240")
    gateway = RecordingGateway(['{"verdict":"NEUTRAL","confidence":50}'])

    dialogue = ExpertDialogue(gateway, max_rounds=1)
    result = await dialogue.ask("sentiment", "deepseek", "system", "context")

    assert result["ok"] is True
    assert dialogue._timeout == 240
    assert gateway.calls[0]["max_tokens"] == 2000
    assert gateway.calls[0]["allow_fallback"] is False


@pytest.mark.asyncio
async def test_expert_dialogue_missing_provider_fails_without_calling_gateway():
    class MissingProviderGateway:
        providers: ClassVar[list] = []

        async def chat_completion(self, **kwargs):
            raise AssertionError("missing provider must not fall through")

    dialogue = ExpertDialogue(MissingProviderGateway(), max_rounds=1)
    result = await dialogue.ask("sentiment", "deepseek", "system", "context")

    assert result["ok"] is False
    assert result["error"] == "provider_not_configured"


@pytest.mark.asyncio
async def test_expert_dialogue_rejects_provider_provenance_mismatch():
    gateway = RecordingGateway(['{"verdict":"NEUTRAL","confidence":50}'])
    gateway.last_provider_used = "local_orchestrator"

    dialogue = ExpertDialogue(gateway, max_rounds=1)
    result = await dialogue.ask("sentiment", "deepseek", "system", "context")

    assert result["ok"] is False
    assert result["error"] == "provider_provenance_mismatch"
    assert gateway.calls[0]["allow_fallback"] is False
