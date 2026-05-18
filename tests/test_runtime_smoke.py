"""Smoke tests for the official runtime — no external servers required."""

import os
import sys
import pytest

# Ensure src is importable for direct imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
os.environ.setdefault("UNIVERSAL_SKIP_GATEWAY", "1")


# ---------------------------------------------------------------------------
# 1. FastAPI app health
# ---------------------------------------------------------------------------


def test_app_imports():
    """Canonical entrypoint imports without error."""
    from agent_server.main import app

    assert app is not None


def test_app_title():
    from agent_server.main import app

    assert "A2A" in app.title or "SuperEzio" in app.title


def test_app_has_health_route():
    from agent_server.main import app

    paths = set()
    for route in app.routes:
        if hasattr(route, "path"):
            paths.add(route.path)
    assert "/health" in paths


def test_app_has_task_submit_route():
    from agent_server.main import app

    paths = set()
    for route in app.routes:
        if hasattr(route, "path"):
            paths.add(route.path)
    assert any("submit" in p for p in paths)


# ---------------------------------------------------------------------------
# 2. A2A Protocol
# ---------------------------------------------------------------------------


def test_a2a_message_roundtrip():
    from core.ports.protocol import A2AMessage, MessageType

    msg = A2AMessage(
        from_agent="ui",
        to_agent="bob",
        type=MessageType.TASK_SUBMIT,
        payload={"ticker": "AAPL", "time_horizon": "14 days"},
    )
    assert msg.payload["ticker"] == "AAPL"
    assert msg.from_agent == "ui"

    resp = A2AMessage.create_response(
        msg, type=MessageType.TASK_RESULT, payload={"verdict": "HOLD"}, from_agent="bob"
    )
    assert resp.correlation_id == msg.correlation_id
    assert resp.trace_id == msg.trace_id


# ---------------------------------------------------------------------------
# 3. Pipeline graph
# ---------------------------------------------------------------------------


def test_graph_builds_and_has_nodes():
    from core.pipeline import build_graph

    p = build_graph()
    nodes = set(p.graph.nodes.keys())
    expected = {
        "__start__",
        "orchestrator_primary",
        "data",
        "f51_verdict",
        "ceo_primary",
    }
    assert expected.issubset(nodes)


def test_graph_status():
    from core.pipeline import build_graph

    p = build_graph()
    status = p.get_status()
    assert isinstance(status["nodes"], list)
    assert "gateway_available" in status


def test_graph_shutdown():
    from core.pipeline import build_graph

    p = build_graph()
    p.shutdown()


# ---------------------------------------------------------------------------
# 4. F51 Engine
# ---------------------------------------------------------------------------


def test_f51_unified_decision_smoke():
    from src.f51.formulas import DecisionFactors, unified_decision

    f = DecisionFactors(
        veracity=1.0,
        consensus=0.7,
        proxy_reward=0.5,
        robustness=0.8,
        uncertainty=0.2,
        danger=0.0,
    )
    result = unified_decision(f)
    assert 0.0 <= result <= 1.0


def test_f51_veracity_gate_smoke():
    from src.f51.gates import VeracityGate

    gate = VeracityGate()
    result = gate.verify(
        [("price", 100.0, "test"), ("volume", 1000.0, "test")],
        {"price": 100.0, "volume": 1000.0},
    )
    assert result.passed is True


def test_f51_combined_risk_smoke():
    from src.f51.formulas import combined_risk

    c = combined_risk(0.1, 0.3, 0.7)
    assert c >= 0.7


# ---------------------------------------------------------------------------
# 5. CEO prompt builder
# ---------------------------------------------------------------------------


def test_ceo_system_prompt():
    from core.pipeline.prompts.builder import ceo_system_prompt

    prompt = ceo_system_prompt()
    assert len(prompt) > 100
    assert "ENGLISH" in prompt


def test_build_ceo_prompt_ticker():
    from core.pipeline.prompts.builder import build_ceo_prompt

    state = {
        "message": "AAPL 14 dias analise",
        "ticker": "AAPL",
        "intent": "ticker_analysis",
        "route": "ticker_analysis",
        "time_horizon": "14 days",
    }
    prompt = build_ceo_prompt(state)
    assert "VERDICT" in prompt
    assert "AAPL" in prompt


def test_build_ceo_prompt_casual():
    from core.pipeline.prompts.builder import build_ceo_prompt

    state = {
        "message": "Hello who are you",
        "intent": "general_question",
        "route": "general",
    }
    prompt = build_ceo_prompt(state)
    assert "USER:" in prompt


# ---------------------------------------------------------------------------
# 6. NeuralDecisionExpert
# ---------------------------------------------------------------------------


def test_neural_decision_expert_imports():
    from experts.neural_decision.neural_decision_expert import NeuralDecisionExpert

    assert NeuralDecisionExpert is not None


def test_neural_decision_expert_smoke():
    from experts.neural_decision.neural_decision_expert import NeuralDecisionExpert

    expert = NeuralDecisionExpert()
    features = {
        "price": [100.0 + i * 0.5 for i in range(30)],
        "volume": [1000000.0 for _ in range(30)],
        "technicals": {"rsi": 55.0, "macd": 1.2, "sma_20": 105.0, "sma_50": 98.0},
    }
    context = {"sentiment_score": 0.2, "macro_context": "neutral"}
    result = expert.predict("AAPL", "14 days", features, context)
    assert result is not None
    assert "direction_prob" in result or "error" in result


# ---------------------------------------------------------------------------
# 7. DataHub
# ---------------------------------------------------------------------------


def test_data_hub_imports():
    from data.data_hub import DataHub

    assert DataHub is not None


def test_data_hub_instantiation():
    from data.data_hub import DataHub

    hub = DataHub()
    assert hasattr(hub, "get_price")
    assert hasattr(hub, "get_profile")
    assert hasattr(hub, "get_candles")
    assert hasattr(hub, "get_quote")


# ---------------------------------------------------------------------------
# 8. Protocol
# ---------------------------------------------------------------------------


def test_message_type_enum():
    from core.ports.protocol import MessageType

    assert MessageType.TASK_SUBMIT == "TASK.SUBMIT"
    assert MessageType.ERROR == "ERROR"


def test_a2a_message_validation():
    from core.ports.protocol import A2AMessage

    with pytest.raises(Exception):
        A2AMessage.model_validate({"from": "ui"})  # missing to and type
