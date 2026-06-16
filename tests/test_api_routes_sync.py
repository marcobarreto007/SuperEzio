"""Individual tests for each FastAPI endpoint to verify the frontend-to-backend sync.

Verifies the fluid communication flow:
A (Frontend UI) -> B (Backend Server) -> C (Pipeline/Bob/LLM) -> B -> A.
"""

from __future__ import annotations

import json
import unittest.mock
from types import SimpleNamespace

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from agent_server.main import app
from agent_server.endpoints import _session_history
from core.observability import log_queue


# ---------------------------------------------------------------------------
# Mock Pipeline & Fixture
# ---------------------------------------------------------------------------
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
def client_with_mock_pipeline(monkeypatch):
    mock_p = MockPipeline()
    original_pipeline = getattr(app.state, "pipeline", None)
    app.state.pipeline = mock_p
    import agent_server.endpoints as endpoints

    monkeypatch.setenv("SUPEREZIO_COCKPIT_READ_IBKR_ORDERS", "0")
    monkeypatch.setattr(endpoints.reward_gate, "score", lambda _text: 0.50)
    monkeypatch.setattr(
        endpoints.sanity_check,
        "verify",
        lambda *_args, **_kwargs: SimpleNamespace(passed=True, warnings=[], blocks=[]),
    )
    yield mock_p, TestClient(app)
    # restore
    if original_pipeline:
        app.state.pipeline = original_pipeline
    else:
        delattr(app.state, "pipeline")


# ---------------------------------------------------------------------------
# Endpoints: GET / and Static Files
# ---------------------------------------------------------------------------
def test_root(client_with_mock_pipeline):
    """1. GET / - Serves frontend index.html"""
    _, client = client_with_mock_pipeline
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "SuperEzio" in response.text or "<html" in response.text


def test_favicon(client_with_mock_pipeline):
    """2. GET /favicon.ico - Serves the SVG icon"""
    _, client = client_with_mock_pipeline
    response = client.get("/favicon.ico")
    assert response.status_code == 200
    assert "image/svg+xml" in response.headers["content-type"]
    assert "svg" in response.text
    assert "SE" in response.text


# ---------------------------------------------------------------------------
# Endpoints: Diagnostics, Metrics & Metadata
# ---------------------------------------------------------------------------
def test_health(client_with_mock_pipeline):
    """3. GET /health - Minimal public status check"""
    _, client = client_with_mock_pipeline
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "agent" in data
    assert "version" in data


def test_health_details(client_with_mock_pipeline):
    """4. GET /health/details - Deep status checks (GPU, models, redis, cost guard)"""
    _, client = client_with_mock_pipeline
    response = client.get("/health/details")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "checks" in data
    assert "gpu" in data["checks"]
    assert "local_models" in data["checks"]
    assert "redis" in data["checks"]
    assert "providers_summary" in data["checks"]
    assert "cost_guard" in data["checks"]
    assert data["mission"]["status"] == "loaded"
    assert data["mission"]["broker"]["ibkr"]["connection"] == "connected_paper"
    assert data["mission"]["broker"]["ibkr"]["mode"] == "paper_order_enabled"
    assert data["mission"]["broker"]["ibkr"]["can_submit_orders"] is True


def test_metrics(client_with_mock_pipeline):
    """5. GET /metrics - Telemetry indicators"""
    _, client = client_with_mock_pipeline
    response = client.get("/metrics")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "superezio"
    assert "version" in data


def test_capabilities(client_with_mock_pipeline):
    """6. GET /capabilities - Supported task list"""
    _, client = client_with_mock_pipeline
    response = client.get("/capabilities")
    assert response.status_code == 200
    data = response.json()
    assert data["agent"] == "f51_universal"
    assert "supported_tasks" in data
    assert "brain" in data


def test_product_manifest(client_with_mock_pipeline):
    """7. GET /product/manifest - Manifest config contract"""
    _, client = client_with_mock_pipeline
    response = client.get("/product/manifest")
    assert response.status_code == 200
    data = response.json()
    assert "product_name" in data
    assert "positioning" in data
    assert "runtime" in data


def test_cockpit_portfolio(client_with_mock_pipeline):
    """GET /cockpit/portfolio - cockpit portfolio contract."""
    _, client = client_with_mock_pipeline
    response = client.get("/cockpit/portfolio")
    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "IBKR"
    assert "connected" in data
    assert "equity" in data
    assert "positions_count" in data
    assert isinstance(data["positions"], list)
    assert "orders_count" in data
    assert isinstance(data["orders"], list)
    assert data["active_orders"] == data["orders"]
    assert "broker_orders_count" in data
    assert isinstance(data["broker_orders"], list)
    assert "local_tickets_count" in data
    assert isinstance(data["local_tickets"], list)
    assert "trade_history_count" in data
    assert isinstance(data["trade_history"], list)
    assert "trade_stats" in data
    assert "selected_ticker" in data


def test_cockpit_portfolio_separates_broker_local_and_history(
    client_with_mock_pipeline, monkeypatch
):
    """GET /cockpit/portfolio separates real broker orders from local audit rows."""
    import agent_server.endpoints as endpoints

    monkeypatch.setattr(
        endpoints,
        "_cockpit_ibkr_open_orders",
        lambda: [
            {
                "order_id": "ibkr-1",
                "ticker": "AAPL",
                "symbol": "AAPL",
                "action": "BUY",
                "qty": 3,
                "status": "Submitted",
                "source": "ibkr",
            }
        ],
    )
    monkeypatch.setattr(
        endpoints,
        "_cockpit_local_order_tickets",
        lambda: [
            {
                "order_id": "local-1",
                "ticker": "SNDL",
                "symbol": "SNDL",
                "action": "BUY",
                "qty": 10,
                "status": "pending_validation",
                "source": "local_pending",
            }
        ],
    )
    monkeypatch.setattr(
        endpoints,
        "_cockpit_trade_history",
        lambda limit=50: {
            "source": "paper_journal",
            "count": 1,
            "stats": {"total_trades": 1},
            "trades": [
                {
                    "trade_id": "paper-1",
                    "ticker": "PLUG",
                    "status": "open",
                    "source": "paper_journal",
                }
            ],
        },
    )
    _, client = client_with_mock_pipeline

    response = client.get("/cockpit/portfolio")
    assert response.status_code == 200
    data = response.json()
    assert data["orders_source"] == "ibkr"
    assert data["broker_orders_count"] == 1
    assert data["local_tickets_count"] == 1
    assert data["orders_count"] == 2
    assert data["orders"][0]["source"] == "ibkr"
    assert data["orders"][1]["source"] == "local_pending"
    assert data["trade_history_count"] == 1
    assert data["trade_history"][0]["trade_id"] == "paper-1"


def test_trade_history_endpoint(client_with_mock_pipeline, monkeypatch):
    """GET /trades/history exposes PaperJournal history to the cockpit."""
    import agent_server.endpoints as endpoints

    monkeypatch.setattr(
        endpoints,
        "_cockpit_trade_history",
        lambda limit=50: {
            "source": "paper_journal",
            "count": 1,
            "stats": {"total_trades": 1, "open_trades": 1},
            "trades": [{"trade_id": "paper-1", "ticker": "PLUG", "status": "open"}],
        },
    )
    _, client = client_with_mock_pipeline

    response = client.get("/trades/history?limit=7")
    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "paper_journal"
    assert data["stats"]["total_trades"] == 1
    assert data["trades"][0]["ticker"] == "PLUG"


def test_cockpit_summary(client_with_mock_pipeline):
    """GET /cockpit/summary - aggregate frontpage contract."""
    _, client = client_with_mock_pipeline
    response = client.get("/cockpit/summary")
    assert response.status_code == 200
    data = response.json()
    assert "generated_at" in data
    assert data["pipeline"]["status"] == "ok"
    assert "sentiment" in data
    assert "portfolio" in data
    assert data["portfolio"]["provider"] == "IBKR"
    assert set(["genie", "deep", "bob", "status"]).issubset(data)
    assert set(["pulses", "alerts"]).issubset(data["genie"])
    assert set(["last_math", "last_experts", "last_trinity"]).issubset(data["deep"])
    assert set(["last_decision", "portfolio", "guardrails"]).issubset(data["bob"])
    assert "approvals" in data["bob"]
    assert data["bob"]["portfolio"]["provider"] == "IBKR"
    assert data["status"]["ibkr"]["status"] == "online"
    assert "orders_count" in data["status"]["ibkr"]
    assert data["status"]["guardrails"]["total"] == 30


def test_trade_execute_creates_pending_ticket_without_broker_submit(
    client_with_mock_pipeline, monkeypatch
):
    """POST /trade/execute must not bypass Bob/committee validation."""
    import core.pipeline.nodes.tool_executor as tool_executor

    async def fail_if_called(*_args, **_kwargs):
        raise AssertionError("_submit_paper_order must not run from /trade/execute")

    monkeypatch.setattr(tool_executor, "_submit_paper_order", fail_if_called)
    _, client = client_with_mock_pipeline

    response = client.post(
        "/trade/execute",
        json={
            "ticker": "AAPL",
            "action": "buy",
            "qty": 1,
            "limit_price": 100,
            "message": "test guarded ticket",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is False
    assert data["submitted_to_broker"] is False
    assert data["phase"] == "pending_validation"
    assert data["reason"] == "committee_required_before_submit"
    assert "committee" in data["next_step"]

    status = client.get(f"/trade/status/{data['order_id']}")
    assert status.status_code == 200
    assert status.json()["phase"] == "pending_validation"


def test_paper_approval_endpoints(client_with_mock_pipeline):
    """POST /paper/approve and /paper/reject resolve pending requests."""
    from core.trading.approval_gate import get_approval_gate, reset_approval_gate_for_test

    _, client = client_with_mock_pipeline
    gate = reset_approval_gate_for_test()
    req = gate.submit("PLUG", "buy", 100, 100.0, 95.0, 501.0, "pytest")

    response = client.post(f"/paper/approve/{req.id}")
    assert response.status_code == 200
    assert response.json()["request"]["status"] == "approved"

    req2 = get_approval_gate().submit("TSLA", "buy", 100, 100.0, 95.0, 501.0, "pytest")
    response = client.post(f"/paper/reject/{req2.id}")
    assert response.status_code == 200
    assert response.json()["request"]["status"] == "rejected"

    response = client.post("/paper/approve/no-such-id")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Endpoints: Market Data & Real-Time SSE
# ---------------------------------------------------------------------------
def test_chart_data(client_with_mock_pipeline, monkeypatch):
    """8. GET /api/chart-data/{ticker} - Candles and indicators"""
    _, client = client_with_mock_pipeline

    from data.data_hub import hub

    # Mock data hub calls
    monkeypatch.setattr(
        hub,
        "get_candles",
        lambda *args, **kwargs: {
            "candles": [
                {
                    "time": 1700000000,
                    "open": 100.0,
                    "high": 105.0,
                    "low": 95.0,
                    "close": 102.0,
                    "volume": 1000,
                },
                {
                    "time": 1700000060,
                    "open": 102.0,
                    "high": 108.0,
                    "low": 101.0,
                    "close": 107.0,
                    "volume": 1500,
                },
            ]
        },
    )
    monkeypatch.setattr(
        hub,
        "get_profile",
        lambda *args, **kwargs: {
            "name": "Apple Inc.",
            "sector": "Technology",
            "currency": "USD",
            "exchange": "NASDAQ",
            "market_cap": 2900000000000,
        },
    )

    response = client.get("/api/chart-data/AAPL?timeframe=6M")
    assert response.status_code == 200
    data = response.json()
    assert data["ticker"] == "AAPL"
    assert "ohlcv" in data
    assert len(data["ohlcv"]) == 2
    assert "price" in data
    assert data["price"]["current"] == 107.0
    assert "indicators" in data
    assert "sma20" in data["indicators"]


def test_chart_sse(client_with_mock_pipeline, monkeypatch):
    """9. GET /api/chart-sse/{ticker} - Streaming candle data via SSE"""
    _, client = client_with_mock_pipeline

    from data.data_hub import hub

    monkeypatch.setattr(
        hub,
        "get_candles",
        lambda *args, **kwargs: {
            "candles": [
                {
                    "time": 1700000000,
                    "open": 100.0,
                    "high": 105.0,
                    "low": 95.0,
                    "close": 102.0,
                    "volume": 1000,
                }
            ]
        },
    )

    # Mock Request.is_disconnected to exit the loop after the first check
    calls = 0

    async def mock_is_disconnected(self):
        nonlocal calls
        calls += 1
        return calls > 1

    with unittest.mock.patch.object(Request, "is_disconnected", mock_is_disconnected):
        response = client.get("/api/chart-sse/AAPL?timeframe=1D&refresh_s=1")
        assert response.status_code == 200
        assert "AAPL" in response.text
        assert "event: candle_snapshot" in response.text or "data: " in response.text


# ---------------------------------------------------------------------------
# Endpoints: Observability Logs Stream
# ---------------------------------------------------------------------------
def test_neural_logs(client_with_mock_pipeline):
    """10. GET /neural/logs - Streaming runtime logs via SSE"""
    _, client = client_with_mock_pipeline
    # Clear any leftover logs from other tests
    while not log_queue.empty():
        try:
            log_queue.get_nowait()
        except Exception:
            break
    log_queue.put("Test Log Entry: Agent initialized.")

    # Mock Request.is_disconnected to exit after one item is processed
    calls = 0

    async def mock_is_disconnected(self):
        nonlocal calls
        calls += 1
        return calls > 1

    with unittest.mock.patch.object(Request, "is_disconnected", mock_is_disconnected):
        response = client.get("/neural/logs")
        assert response.status_code == 200
        assert "Test Log Entry" in response.text


# ---------------------------------------------------------------------------
# Endpoints: Experts & Firewall Evaluations
# ---------------------------------------------------------------------------
def test_sdca_evaluate(client_with_mock_pipeline):
    """11. POST /api/sdca/evaluate - Bounded SDCA candidate checks"""
    _, client = client_with_mock_pipeline
    payload = {
        "id": "test-sdca-eval-001",
        "source": "pytest",
        "asset": "BTC-CAD",
        "action": "buy_leveraged",
        "thesis": "BTC breakout, leverage up",
        "amount_cad": 1000.0,
        "risk_context": {"leverage": True, "fomo": True},
        "raw_signals": {"price_change_2h": 9.5, "social_hype": "high"},
    }
    response = client.post("/api/sdca/evaluate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "decision" in data
    assert data["decision"] in {"BLOCK", "REVIEW"}
    assert "ghost_tokens" in data


def test_neural_predict(client_with_mock_pipeline):
    """12. POST /experts/neural-decision/predict - Signal expert prediction"""
    _, client = client_with_mock_pipeline
    payload = {
        "symbol": "BTCUSDT",
        "timeframe": "1h",
        "features": {
            "return_1": 0.002,
            "return_5": -0.01,
            "rsi_14": 42.5,
            "atr_pct": 0.018,
            "volume_zscore": 2.4,
            "price_vs_ema_21": -0.006,
            "trend_slope": -0.12,
            "volatility_regime": "high",
            "liquidity_sweep": True,
        },
        "context": {
            "macro_risk": "neutral",
            "news_sentiment": "neutral",
            "fraud_risk": 0.12,
            "veracity_score": 0.77,
        },
    }
    response = client.post("/experts/neural-decision/predict", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["expert"] == "NeuralDecisionExpert"
    assert "direction_prob" in data
    assert "uncertainty" in data
    assert "recommendation" in data


# ---------------------------------------------------------------------------
# Endpoints: Task Submit Complete E2E Flow (A -> B -> C -> B -> A)
# ---------------------------------------------------------------------------
def test_task_submit_casual_flow(client_with_mock_pipeline):
    """13a. POST /task/submit - E2E flow for casual query"""
    mock_p, client = client_with_mock_pipeline

    mock_p.events_to_yield = [
        {"type": "STREAM_START", "msg_id": "test-msg-001"},
        {"type": "INTENT_CLASSIFIED", "intent": "general_question", "route": "general"},
        {"type": "CHUNK", "content": "Hello! I am Bob, your financial orchestrator."},
        {"type": "PIPELINE_STEP", "step": "agent_primary", "status": "completed"},
    ]

    payload = {
        "version": "a2a/1.0",
        "from": "user",
        "to": "superezio",
        "type": "TASK.SUBMIT",
        "payload": {
            "message": "Hi Bob!",
            "session_id": "session-test-01",
        },
    }

    response = client.post("/task/submit", json=payload)
    assert response.status_code == 200

    # Parse NDJSON
    lines = [line.strip() for line in response.text.strip().split("\n") if line.strip()]
    events = [json.loads(line) for line in lines]

    # Validate streamed event types
    event_types = [ev["type"] for ev in events]
    assert "STREAM_START" in event_types
    assert "INTENT_CLASSIFIED" in event_types
    assert "CHUNK" in event_types
    assert "STREAM_END" in event_types

    chunks = [ev for ev in events if ev["type"] == "CHUNK"]
    assert chunks[0]["content"] == "Hello! I am Bob, your financial orchestrator."

    # Validate STREAM_END contains trace metadata
    stream_end = events[-1]
    assert stream_end["type"] == "STREAM_END"
    trace = stream_end["trace"]
    assert trace["user_query"] == "Hi Bob!"
    assert trace["detected_intent"] == "general_question"
    assert trace["route_used"] == "general"
    assert trace["fallback_used"] is False


def test_task_submit_broker_status_ignores_ibkr_ui_ticker(client_with_mock_pipeline):
    """Broker status questions about IBKR must not become ticker analysis."""
    mock_p, client = client_with_mock_pipeline

    mock_p.events_to_yield = [
        {"type": "STREAM_START", "msg_id": "test-msg-broker-status"},
        {"type": "INTENT_CLASSIFIED", "intent": "general_question", "route": "general"},
        {
            "type": "CHUNK",
            "content": "IBKR is connected in read-only paper mode; I cannot submit orders.",
        },
    ]

    payload = {
        "version": "a2a/1.0",
        "from": "user",
        "to": "superezio",
        "type": "TASK.SUBMIT",
        "payload": {
            "message": "Bob, voce esta em modo paper/read-only no IBKR?",
            "ticker": "IBKR",
            "session_id": "session-test-broker-status",
        },
    }

    response = client.post("/task/submit", json=payload)
    assert response.status_code == 200
    assert mock_p.last_stream_kwargs["ticker"] == ""
    assert mock_p.last_stream_kwargs["context"] == ""


def test_task_submit_quality_gate_flags_low_score(client_with_mock_pipeline, monkeypatch):
    """13a.1 POST /task/submit - Quality gate adds trace metadata without fallback."""
    mock_p, client = client_with_mock_pipeline

    import agent_server.endpoints as endpoints

    monkeypatch.setattr(endpoints.reward_gate, "score", lambda _text: 0.12)
    mock_p.events_to_yield = [
        {"type": "STREAM_START", "msg_id": "test-msg-quality"},
        {"type": "INTENT_CLASSIFIED", "intent": "general_question", "route": "general"},
        {"type": "PIPELINE_STEP", "step": "agent_primary", "status": "started"},
        {
            "type": "CHUNK",
            "content": "This answer is long enough to be scored by the quality gate.",
        },
        {"type": "PIPELINE_STEP", "step": "agent_primary", "status": "completed"},
    ]

    payload = {
        "version": "a2a/1.0",
        "from": "user",
        "to": "superezio",
        "type": "TASK.SUBMIT",
        "payload": {
            "message": "Hi Bob!",
            "session_id": "session-test-quality",
        },
    }

    response = client.post("/task/submit", json=payload)
    assert response.status_code == 200
    events = [json.loads(line) for line in response.text.strip().split("\n") if line.strip()]
    trace = events[-1]["trace"]

    assert trace["quality_score"] == 0.12
    assert trace["quality_flagged"] is True
    assert trace["quality_warnings"] == ["reward_score=0.120 < 0.3"]
    assert trace["fallback_used"] is False


def test_task_submit_empty_fallback(client_with_mock_pipeline):
    """13b. POST /task/submit - Empty response triggers the fallback chunk mechanism"""
    mock_p, client = client_with_mock_pipeline

    # Simulate an empty response where no chunks were yielded
    mock_p.events_to_yield = [
        {"type": "STREAM_START", "msg_id": "test-msg-002"},
    ]

    payload = {
        "version": "a2a/1.0",
        "from": "user",
        "to": "superezio",
        "type": "TASK.SUBMIT",
        "payload": {
            "message": "Analyze AAPL",
            "session_id": "session-test-02",
        },
    }

    response = client.post("/task/submit", json=payload)
    assert response.status_code == 200

    lines = [line.strip() for line in response.text.strip().split("\n") if line.strip()]
    events = [json.loads(line) for line in lines]

    # Find the fallback chunk
    chunks = [ev for ev in events if ev["type"] == "CHUNK"]
    assert len(chunks) == 1
    content = chunks[0]["content"]
    assert isinstance(content, str) and content.strip()
    assert "route:" in content
    assert "Final verdict:" in content

    stream_end = events[-1]
    assert stream_end["trace"]["fallback_used"] is True
    assert stream_end["trace"]["final_content_length"] > 0


def test_task_submit_what_happened_intercept(client_with_mock_pipeline):
    """13c. POST /task/submit - Intercepts "o que houve" immediately after a failure"""
    mock_p, client = client_with_mock_pipeline
    session_id = "session-failure-test"

    # Pre-populate session history with a failure record
    _session_history[session_id] = {
        "detected_intent": "MACRO_THESIS",
        "failed": True,
    }

    payload = {
        "version": "a2a/1.0",
        "from": "user",
        "to": "superezio",
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

    # And stream end trace is correct
    stream_end_events = [ev for ev in events if ev.get("type") == "STREAM_END"]
    assert len(stream_end_events) == 1
    trace = stream_end_events[0]["trace"]
    assert trace["detected_intent"] == "WHAT_HAPPENED_INTERCEPT"
    assert trace["scanner_invoked"] is False


def test_feedback_endpoint_round_trip(client_with_mock_pipeline, monkeypatch, tmp_path):
    """13d. POST /feedback and GET /feedback/stats - Local feedback capture."""
    _, client = client_with_mock_pipeline

    import core.ml.feedback as feedback

    monkeypatch.setattr(feedback, "_FEEDBACK_DIR", tmp_path)

    response = client.post(
        "/feedback",
        json={"msg_id": "test-msg-feedback", "rating": 1, "comment": "useful"},
    )
    assert response.status_code == 200
    assert response.json() == {"ok": True}

    stats = client.get("/feedback/stats?days=1")
    assert stats.status_code == 200
    assert stats.json()["total"] == 1


def test_feedback_endpoint_rejects_bad_rating(client_with_mock_pipeline):
    """13e. POST /feedback - Invalid ratings are bounded and return HTTP 400."""
    _, client = client_with_mock_pipeline

    response = client.post("/feedback", json={"msg_id": "test-msg-feedback", "rating": "bad"})

    assert response.status_code == 400
    assert response.json()["detail"] == "rating must be 0-5"


def test_frontend_ops_console_integration():
    """14. Verifies the new Operations Console UI integration files exist and contain appropriate wiring."""
    from pathlib import Path

    html = Path("frontend/index.html").read_text(encoding="utf-8")
    init_js = Path("frontend/js/init.js").read_text(encoding="utf-8")
    ops_js = Path("frontend/js/ops-console.js").read_text(encoding="utf-8")
    ops_css = Path("frontend/css/ops-console.css").read_text(encoding="utf-8")

    assert len(ops_css) > 0
    assert 'href="css/ops-console.css"' in html
    assert 'id="ops-console-btn"' in html
    assert 'id="broker-status-btn"' in html
    assert 'id="broker-status-label"' in html
    assert 'id="ops-console"' in html
    assert 'id="ops-card-broker"' in html
    assert 'id="ops-broker-status"' in html
    assert 'src="js/ops-console.js"' in html

    assert "window.SZ.opsConsole =" in ops_js
    assert "loadDiagnostics" in ops_js
    assert "renderBrokerDiagnostics" in ops_js

    assert "refreshBrokerStatus" in init_js
    assert "updateBrokerStatus" in init_js
    assert "broker-status-btn" in init_js
    assert "ops-console-btn" in init_js
    assert "ops-console-close" in init_js
    assert "SZ.opsConsole.toggle" in init_js


def test_frontend_ibkr_order_mirror_integration():
    """15. Frontpage exposes active IBKR orders and clicking one drives the chart ticker."""
    from pathlib import Path

    html = Path("frontend/index.html").read_text(encoding="utf-8")
    init_js = Path("frontend/js/init.js").read_text(encoding="utf-8")
    cockpit_js = Path("frontend/js/cockpit.js").read_text(encoding="utf-8")
    charts_css = Path("frontend/css/charts.css").read_text(encoding="utf-8")

    assert 'id="orders-mirror"' in html
    assert 'id="orders-list"' in html
    assert 'id="orders-count"' in html
    assert "function renderPortfolioMirror" in init_js
    assert "function selectTicker" in init_js
    assert "ibkr_mirror_click" in init_js
    assert "refreshCockpitPortfolio().then" in init_js
    assert "window.SZ.renderPortfolioMirror" in cockpit_js
    assert ".order-row.is-selected" in charts_css
