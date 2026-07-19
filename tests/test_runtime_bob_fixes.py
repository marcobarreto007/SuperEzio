import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from agent_server.main import app
from agent_server.endpoints import _session_history
from core.bob_consciousness.body import BobsBody


# Mock Pipeline for controlling runtime responses
class MockPipeline:
    def __init__(self):
        self.events_to_yield = []
        self.last_stream_kwargs = {}

    async def stream_events(self, prompt, **kwargs):
        self.last_stream_kwargs = {"prompt": prompt, **kwargs}
        for ev in self.events_to_yield:
            yield ev

    def get_status(self):
        return {"status": "ok", "nodes": []}

    def shutdown(self):
        pass


@pytest.fixture
def client_with_mock_pipeline():
    mock_p = MockPipeline()
    original_pipeline = getattr(app.state, "pipeline", None)
    app.state.pipeline = mock_p
    yield mock_p, TestClient(app)
    # restore
    if original_pipeline:
        app.state.pipeline = original_pipeline
    else:
        delattr(app.state, "pipeline")


def test_man_at_work_notification_applies_timeout_to_urlopen(monkeypatch):
    """urllib Request has no timeout argument; the network operation owns it."""
    monkeypatch.setenv("SUPEREZIO_DEEPSEEK_API_KEY", "test-key-not-a-secret")
    response = MagicMock()
    response.__enter__.return_value.read.return_value = b'{"choices": []}'

    with patch("urllib.request.urlopen", return_value=response) as urlopen:
        BobsBody()._try_deepseek_notification("test containment")

    request = urlopen.call_args.args[0]
    assert request.full_url == "https://api.deepseek.com/v1/chat/completions"
    assert urlopen.call_args.kwargs == {"timeout": 10}


# Test A — Macro thesis does not attach AAPL
def test_macro_thesis_does_not_attach_aapl(client_with_mock_pipeline):
    mock_p, client = client_with_mock_pipeline

    # We yield a standard pipeline execution flow
    mock_p.events_to_yield = [
        {"type": "STREAM_START", "msg_id": "test-msg-id"},
        {"type": "INTENT_CLASSIFIED", "intent": "general_question", "route": "general"},
        {"type": "PIPELINE_STEP", "step": "agent_primary", "status": "started"},
        {"type": "CHUNK", "content": "Question Classification — MACRO_THESIS\n" + "A" * 600},
        {"type": "PIPELINE_STEP", "step": "agent_primary", "status": "completed"},
    ]

    payload = {
        "from": "test-runner",
        "to": "bob",
        "type": "TASK.SUBMIT",
        "payload": {
            "message": (
                "An investor believes AI will dominate the next decade and wants heavy exposure "
                "to AI infrastructure, semiconductors, cloud, energy, and automation. Build a thesis "
                "that separates real secular opportunity from hype, overvaluation, and concentration risk."
            ),
            "ticker": "AAPL",
            "chart_context": "OHLCV AAPL data",
            "session_id": "session-aapl-leak-test",
        },
    }

    response = client.post("/task/submit", json=payload)
    assert response.status_code == 200

    # Parse NDJSON response lines
    lines = [line.strip() for line in response.text.strip().split("\n") if line.strip()]
    events = [json.loads(line) for line in lines]

    # Check that stream ended and trace is correct
    stream_end_events = [ev for ev in events if ev.get("type") == "STREAM_END"]
    assert len(stream_end_events) == 1
    trace = stream_end_events[0]["trace"]

    assert trace["user_query"] == payload["payload"]["message"]
    assert trace["detected_intent"] == "MACRO_THESIS"
    assert trace["selected_ui_ticker"] == "AAPL"
    assert trace["chart_context_attached"] is False
    assert trace["scanner_invoked"] is False
    assert trace["fallback_used"] is False
    assert trace["final_content_length"] > 500

    # Verify context leak block: mock_p should have received empty/unset ticker and context
    assert mock_p.last_stream_kwargs.get("ticker") == ""
    assert mock_p.last_stream_kwargs.get("context") == ""


# Test B — Empty response blocked
def test_empty_response_blocked(client_with_mock_pipeline):
    mock_p, client = client_with_mock_pipeline

    # Simulating empty response from backend (no chunks yielded)
    mock_p.events_to_yield = [
        {"type": "STREAM_START", "msg_id": "test-msg-id"},
    ]

    payload = {
        "from": "test-runner",
        "to": "bob",
        "type": "TASK.SUBMIT",
        "payload": {
            "message": "Verify empty response handling",
            "session_id": "session-empty-test",
        },
    }

    response = client.post("/task/submit", json=payload)
    assert response.status_code == 200

    lines = [line.strip() for line in response.text.strip().split("\n") if line.strip()]
    events = [json.loads(line) for line in lines]

    stream_end_events = [ev for ev in events if ev.get("type") == "STREAM_END"]
    assert len(stream_end_events) == 1
    trace = stream_end_events[0]["trace"]

    # Under OPUS §7 (No Empty Response Rule), when the pipeline yields zero
    # content the backend synthesizes a structured fallback CHUNK before
    # STREAM_END. So `final_content_length` is the size of that fallback,
    # NOT zero. `fallback_used` is the canonical signal that the empty path
    # was hit.
    assert trace["fallback_used"] is True
    assert trace["final_content_length"] > 0


# Test C — "o que houve" after failed answer explains failure
def test_what_happened_after_failed_answer(client_with_mock_pipeline):
    mock_p, client = client_with_mock_pipeline
    session_id = "session-what-happened-test"

    # Pre-populate session history with a failure for MACRO_THESIS
    _session_history[session_id] = {
        "detected_intent": "MACRO_THESIS",
        "failed": True,
    }

    payload = {
        "from": "test-runner",
        "to": "bob",
        "type": "TASK.SUBMIT",
        "payload": {
            "message": "o que houve",
            "session_id": session_id,
        },
    }

    response = client.post("/task/submit", json=payload)
    assert response.status_code == 200

    lines = [line.strip() for line in response.text.strip().split("\n") if line.strip()]
    events = [json.loads(line) for line in lines]

    # Intercept query should have yielded CHUNK explaining previous failure
    chunk_events = [ev for ev in events if ev.get("type") == "CHUNK"]
    assert len(chunk_events) == 1
    content = chunk_events[0]["content"]
    assert "The previous request failed to produce valid content." in content
    assert "MACRO_THESIS" in content
    assert "No market scanner should have been used." in content

    # And stream end trace is correct
    stream_end_events = [ev for ev in events if ev.get("type") == "STREAM_END"]
    assert len(stream_end_events) == 1
    trace = stream_end_events[0]["trace"]
    assert trace["detected_intent"] == "WHAT_HAPPENED_INTERCEPT"
    assert trace["scanner_invoked"] is False
    assert trace["chart_context_attached"] is False


# Test D — Explicit AAPL chart question still works
def test_explicit_aapl_chart_question_works(client_with_mock_pipeline):
    mock_p, client = client_with_mock_pipeline

    mock_p.events_to_yield = [
        {"type": "STREAM_START", "msg_id": "test-msg-id"},
        {"type": "INTENT_CLASSIFIED", "intent": "MARKET_CONTEXT", "route": "ticker_analysis"},
        {"type": "CHUNK", "content": "AAPL looks bullish on current chart..."},
    ]

    payload = {
        "from": "test-runner",
        "to": "bob",
        "type": "TASK.SUBMIT",
        "payload": {
            "message": "What happened to AAPL on the current chart?",
            "ticker": "AAPL",
            "chart_context": "AAPL chart context data",
            "session_id": "session-explicit-test",
        },
    }

    response = client.post("/task/submit", json=payload)
    assert response.status_code == 200

    lines = [line.strip() for line in response.text.strip().split("\n") if line.strip()]
    events = [json.loads(line) for line in lines]

    stream_end_events = [ev for ev in events if ev.get("type") == "STREAM_END"]
    assert len(stream_end_events) == 1
    trace = stream_end_events[0]["trace"]

    assert trace["detected_intent"] == "MARKET_CONTEXT"
    assert trace["chart_context_attached"] is True
    assert trace["selected_ui_ticker"] == "AAPL"

    # Check that context block was actually passed down
    assert "AAPL chart context data" in mock_p.last_stream_kwargs.get("context", "")
    assert mock_p.last_stream_kwargs.get("ticker") == "AAPL"


def test_attached_chart_context_blocks_false_no_data_answer(client_with_mock_pipeline):
    mock_p, client = client_with_mock_pipeline

    mock_p.events_to_yield = [
        {"type": "STREAM_START", "msg_id": "test-msg-id"},
        {"type": "INTENT_CLASSIFIED", "intent": "ticker_analysis", "route": "ticker_analysis"},
        {"type": "PIPELINE_STEP", "step": "agent_primary", "status": "started"},
        {
            "type": "CHUNK",
            "content": (
                "Nao ha preco, nem grafico, nem metricas para sustentar uma tese operacional."
            ),
        },
    ]

    prompt = (
        "TICKER DIBS: sincronize grafico + Sentimento Vivo. "
        "Bob, analise tese, risco, invalidacao e alvo/stop. "
        "Sentimento=NEUTRAL flat, score=0.03, Reddit=0 mencoes."
    )
    chart_context = (
        "=== CHART CONTEXT ===\n"
        "Ticker: DIBS\n"
        "Current price: 4.09\n"
        "Last close: 4.09\n"
        "Last volume: 484\n"
        "Data points: 130\n"
        "RSI: 42.10\n"
        "=== END CHART CONTEXT ==="
    )
    payload = {
        "from": "test-runner",
        "to": "bob",
        "type": "TASK.SUBMIT",
        "payload": {
            "message": prompt,
            "ticker": "DIBS",
            "chart_context": chart_context,
            "session_id": "session-dibs-chart-repair",
        },
    }

    response = client.post("/task/submit", json=payload)
    assert response.status_code == 200

    lines = [line.strip() for line in response.text.strip().split("\n") if line.strip()]
    events = [json.loads(line) for line in lines]
    content = "".join(ev.get("content", "") for ev in events if ev.get("type") == "CHUNK")
    stream_end = [ev for ev in events if ev.get("type") == "STREAM_END"][0]
    trace = stream_end["trace"]

    assert "Nao ha preco" not in content
    assert "nao vou tratar como falta de dados" in content
    assert "preco atual 4.09" in content
    assert "130 candles" in content
    assert trace["chart_context_attached"] is True
    assert trace["answer_repaired"] is True
    assert trace["repair_reason"] == "model_denied_attached_chart_context"
    assert mock_p.last_stream_kwargs.get("ticker") == "DIBS"
    assert "DIBS" in mock_p.last_stream_kwargs.get("context", "")
