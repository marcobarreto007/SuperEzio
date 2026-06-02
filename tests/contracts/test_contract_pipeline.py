"""Contract tests for PipelineState + Pydantic node I/O models."""

from src.core.pipeline.contracts import (
    PipelineState,
    AgentToolCall,
    IntentResult,
    AgentRequest,
    ExpertCall,
    _expert_results_reducer,
)


# ---------------------------------------------------------------------------
# PipelineState TypedDict
# ---------------------------------------------------------------------------


def test_pipeline_state_empty():
    state: PipelineState = {}
    assert state.get("route") is None
    assert state.get("ticker") is None


def test_pipeline_state_typical():
    state: PipelineState = {
        "run_id": "abc123",
        "message": "analise AAPL 14 dias",
        "route": "ticker_analysis",
        "intent": "ticker_analysis",
        "ticker": "AAPL",
        "time_horizon": "14 days",
        "expert_results": [],
        "executed_tools": ["collect_data"],
        "f51_verdict": {
            "confidence": 0.965,
            "passed": True,
            "factors": {},
            "hub_risk_score": 0.2,
        },
    }
    assert state["route"] == "ticker_analysis"
    assert state["ticker"] == "AAPL"
    assert state["executed_tools"] == ["collect_data"]


def test_pipeline_state_expert_results_default():
    state: PipelineState = {}
    assert state.get("expert_results") in (None, [])


# ---------------------------------------------------------------------------
# IntentResult
# ---------------------------------------------------------------------------


def test_intent_result_defaults():
    r = IntentResult()
    assert r.route == "general"
    assert r.intent == "general_question"
    assert r.action == "answer"
    assert r.ticker == ""
    assert r.confidence == 0.0
    assert r.required_slots == []
    assert r.reasons == []
    assert r.source == "deterministic"


def test_intent_result_ticker_analysis():
    r = IntentResult(
        route="ticker_analysis",
        intent="ticker_analysis",
        action="collect_data",
        ticker="AAPL",
        confidence=0.86,
        reasons=["explicit_ticker_detected"],
    )
    assert r.ticker == "AAPL"
    assert r.action == "collect_data"


# ---------------------------------------------------------------------------
# AgentRequest
# ---------------------------------------------------------------------------


def test_agent_request_defaults():
    r = AgentRequest(task="analyze AAPL")
    assert r.task == "analyze AAPL"
    assert r.ticker == ""
    assert r.model_family == "local"


def test_agent_request_full():
    r = AgentRequest(
        task="analyze AAPL 14 days",
        ticker="AAPL",
        intent="ticker_analysis",
        route="ticker_analysis",
        data_context="price=300.22, rsi=87.9",
        f51_verdict={"confidence": 0.965, "passed": True},
    )
    assert r.ticker == "AAPL"
    assert r.route == "ticker_analysis"
    assert r.f51_verdict["confidence"] == 0.965


# ---------------------------------------------------------------------------
# ExpertCall
# ---------------------------------------------------------------------------


def test_expert_call():
    call = ExpertCall(role="fundamental", ticker="AAPL", context="price=300")
    assert call.role == "fundamental"
    assert call.ticker == "AAPL"
    assert call.provider_name == ""
    assert call.timeout == 60.0


def test_expert_call_custom():
    call = ExpertCall(role="technical", ticker="TSLA", provider_name="deepseek", timeout=30.0)
    assert call.provider_name == "deepseek"
    assert call.timeout == 30.0


# ---------------------------------------------------------------------------
# AgentToolCall
# ---------------------------------------------------------------------------


def test_agent_tool_call_accepts_known_tool():
    call = AgentToolCall.model_validate({"tool": "neural_decision", "args": {"ticker": "AAPL"}})
    assert call.tool == "neural_decision"
    assert call.args == {"ticker": "AAPL"}


def test_agent_tool_call_rejects_unknown_tool():
    try:
        AgentToolCall.model_validate({"tool": "legacy_magic_tool", "args": {}})
    except Exception as exc:
        assert "legacy_magic_tool" in str(exc)
    else:
        raise AssertionError("unknown agent tools must be rejected")


# ---------------------------------------------------------------------------
# Reducer
# ---------------------------------------------------------------------------


def test_expert_results_reducer_empty():
    result = _expert_results_reducer(None, None)
    assert result == []


def test_expert_results_reducer_left_only():
    result = _expert_results_reducer([{"role": "a"}], None)
    assert result == [{"role": "a"}]


def test_expert_results_reducer_both():
    result = _expert_results_reducer([{"role": "a"}], [{"role": "b"}])
    assert result == [{"role": "a"}, {"role": "b"}]


def test_expert_results_reducer_appends():
    result = _expert_results_reducer([{"role": "a"}, {"role": "b"}], [{"role": "c"}])
    assert len(result) == 3
