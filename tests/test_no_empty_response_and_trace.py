"""Tests K-strengthened and §8 — No empty response + runtime trace enrichment.

Pins down two contracts at the /task/submit boundary:

1. **No Empty Response Rule (OPUS §7).** When the pipeline yields zero
   CHUNK events, the backend MUST synthesize a structured fallback CHUNK
   before STREAM_END so the frontend never has to render a blank bubble.
   The fallback content must include route, intent, and a concrete
   suggestion for the user.

2. **Runtime Trace (OPUS §8).** Every /task/submit STREAM_END trace must
   carry the scan telemetry fields:
       - candidate_count
       - rejected_count
       - top_rejection_reasons
       - provider_sources_used
       - provider_error
   These come from the DATA_COLLECTED event emitted by the collector node.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from agent_server.main import app


class _MockPipeline:
    def __init__(self) -> None:
        self.events_to_yield: list[dict] = []
        self.last_stream_kwargs: dict = {}

    async def stream_events(self, prompt: str, **kwargs):
        self.last_stream_kwargs = {"prompt": prompt, **kwargs}
        for ev in self.events_to_yield:
            yield ev

    def get_status(self) -> dict:
        return {"status": "ok", "nodes": []}

    def shutdown(self) -> None:
        pass


@pytest.fixture
def client_with_mock_pipeline():
    mock_p = _MockPipeline()
    original = getattr(app.state, "pipeline", None)
    app.state.pipeline = mock_p
    yield mock_p, TestClient(app)
    if original is not None:
        app.state.pipeline = original
    else:
        try:
            delattr(app.state, "pipeline")
        except AttributeError:
            pass


def _ndjson_events(response) -> list[dict]:
    return [json.loads(line) for line in response.text.strip().split("\n") if line.strip()]


# ---------------------------------------------------------------------------
# Test K (strengthened) — Empty pipeline output → structured fallback CHUNK
# ---------------------------------------------------------------------------


def test_empty_pipeline_emits_structured_fallback_chunk(client_with_mock_pipeline):
    """When the pipeline produces zero CHUNKs, the backend must synthesize
    one structured fallback CHUNK before STREAM_END, never let the
    frontend render an empty bubble."""
    mock_p, client = client_with_mock_pipeline

    mock_p.events_to_yield = [
        {"type": "STREAM_START", "msg_id": "k-strengthened-1"},
        {"type": "INTENT_CLASSIFIED", "intent": "MARKET_SCAN", "route": "market_scan"},
        # Note: NO CHUNK events here on purpose.
    ]

    payload = {
        "from": "test-runner",
        "to": "bob",
        "type": "TASK.SUBMIT",
        "payload": {
            "message": "What stock would you recommend if I want to profit within the next 2 weeks?",
            "session_id": "session-k-empty",
        },
    }

    response = client.post("/task/submit", json=payload)
    assert response.status_code == 200

    events = _ndjson_events(response)
    chunks = [ev for ev in events if ev.get("type") == "CHUNK"]
    stream_ends = [ev for ev in events if ev.get("type") == "STREAM_END"]

    # Exactly one fallback CHUNK was synthesized.
    assert len(chunks) == 1, (
        "Backend must emit exactly one fallback CHUNK when the pipeline "
        f"yields no content. Got {len(chunks)} CHUNKs."
    )
    content = chunks[0]["content"]
    assert isinstance(content, str) and content.strip(), "Fallback CHUNK must not itself be empty."
    # The structured fallback advertises route + intent + actionable suggestion.
    assert "route:" in content
    assert "detected_intent:" in content
    assert "Suggestion:" in content

    # And the trace reflects the fallback path with non-zero final length.
    assert len(stream_ends) == 1
    trace = stream_ends[0]["trace"]
    assert trace["fallback_used"] is True
    assert trace["final_content_length"] > 0, (
        "After the fallback CHUNK is emitted, final_content_length must be greater than zero."
    )


# ---------------------------------------------------------------------------
# Test §8 — Trace must surface scan telemetry from DATA_COLLECTED
# ---------------------------------------------------------------------------


def test_stream_end_trace_includes_scan_telemetry(client_with_mock_pipeline):
    """The collector emits DATA_COLLECTED with candidate/rejection metrics.
    The /task/submit trace must aggregate these so operators can diagnose
    'why did the scan return nothing' without grepping logs."""
    mock_p, client = client_with_mock_pipeline

    mock_p.events_to_yield = [
        {"type": "STREAM_START", "msg_id": "trace-1"},
        {"type": "INTENT_CLASSIFIED", "intent": "MARKET_SCAN", "route": "market_scan"},
        {"type": "PIPELINE_STEP", "step": "data", "status": "started"},
        {
            "type": "DATA_COLLECTED",
            "ticker": "",
            "quality": "partial",
            "candidates": 0,
            "rejected_count": 7,
            "rejection_summary": {
                "missing_short_term_thesis": 4,
                "missing_price": 2,
                "missing_liquidity": 1,
            },
            "providers": ["finnhub", "twelve_data"],
            "source_errors": ["finnhub: rate_limited"],
        },
        {"type": "PIPELINE_STEP", "step": "data", "status": "completed"},
        {"type": "CHUNK", "content": "Scan ran. No valid candidates."},
    ]

    payload = {
        "from": "test-runner",
        "to": "bob",
        "type": "TASK.SUBMIT",
        "payload": {
            "message": "Short-term opportunity?",
            "session_id": "session-trace-1",
        },
    }

    response = client.post("/task/submit", json=payload)
    assert response.status_code == 200

    events = _ndjson_events(response)
    stream_ends = [ev for ev in events if ev.get("type") == "STREAM_END"]
    assert len(stream_ends) == 1
    trace = stream_ends[0]["trace"]

    # Required §8 fields are present.
    for field in (
        "candidate_count",
        "rejected_count",
        "top_rejection_reasons",
        "provider_sources_used",
        "provider_error",
    ):
        assert field in trace, f"Trace is missing required §8 field: {field}"

    # And they reflect what the collector reported.
    assert trace["candidate_count"] == 0
    assert trace["rejected_count"] == 7
    # Ordered by frequency, top reason first.
    assert trace["top_rejection_reasons"][0].startswith("missing_short_term_thesis:")
    assert "finnhub" in trace["provider_sources_used"]
    assert "twelve_data" in trace["provider_sources_used"]
    # provider_error captured from source_errors[0].
    assert trace["provider_error"] is not None
    assert "rate_limited" in trace["provider_error"]
