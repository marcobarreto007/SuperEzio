import pytest

from src.core.pipeline.nodes.orchestrator import node_orchestrator
from src.core.pipeline.nodes.agent import node_agent
from src.core.pipeline.nodes.tool_executor import node_tool_executor


@pytest.mark.asyncio
async def test_orchestrator_sovereign_mode(monkeypatch):
    monkeypatch.setenv("SUPEREZIO_BOB_SOVEREIGN", "1")
    monkeypatch.setattr(
        "src.core.pipeline.nodes.orchestrator.get_stream_writer", lambda: lambda x: None
    )

    state = {
        "message": "cara, em vez de gastar 40 CAD na Lotto Quebec, acha uma penny stock que me dê adrenalina sem perder tudo",
        "ticker": "AAPL",  # should be ignored
        "trade_order_context": {"time_horizon": "14 days"},
    }

    plan = await node_orchestrator(state, gateway=None, config=None)

    assert plan["route"] == "general"
    assert plan["ticker"] == ""
    assert plan["risk_tolerance"] == "especulativa"
    assert plan["bob_intent"] == "buscar_oportunidade"
    assert "market_scan" in plan["allowed_tools"]
    assert plan["scanner_allowed"] is True
    assert plan["ticker_allowed"] is True
    assert plan["cognitive_mode"] == "SOVEREIGN"


@pytest.mark.asyncio
async def test_orchestrator_sovereign_mode_blocks_unscoped_ticket_reference(monkeypatch):
    monkeypatch.setenv("SUPEREZIO_BOB_SOVEREIGN", "1")
    monkeypatch.setattr(
        "src.core.pipeline.nodes.orchestrator.get_stream_writer", lambda: lambda x: None
    )

    plan = await node_orchestrator(
        {"message": "cara vc esta travado neste ticket ?", "ticker": ""},
        gateway=None,
        config=None,
    )

    assert plan["route"] == "needs_scope"
    assert plan["action"] == "ask_for_ticker"
    assert plan["required_slots"] == ["ticker"]
    assert plan["bob_intent"] == "missing_scope"
    assert plan["scanner_allowed"] is False
    assert plan["ticker_allowed"] is False
    assert plan["allowed_tools"] == ["final_answer"]
    assert plan["cognitive_mode"] == "SOVEREIGN"


@pytest.mark.asyncio
async def test_agent_sovereign_mode_captures_thesis_and_trace(monkeypatch):
    monkeypatch.setenv("SUPEREZIO_BOB_SOVEREIGN", "1")
    monkeypatch.setattr("src.core.pipeline.nodes.agent.get_stream_writer", lambda: lambda x: None)

    class MockGateway:
        async def chat_completion(self, **kwargs):
            return '<think>Vou analisar penny stocks de alta adrenalina.</think> {"tool": "market_scan", "args": {"query": "penny stocks"}}'

    state = {
        "message": "cara, em vez de gastar 40 CAD na Lotto Quebec, acha uma penny stock que me dê adrenalina sem perder tudo",
        "risk_tolerance": "especulativa",
        "bob_intent": "buscar_oportunidade",
        "agent_iterations": 0,
        "bob_reasoning_trace": [],
    }

    result = await node_agent(state, gateway=MockGateway(), config=None)

    assert "bob_thesis" in result
    assert result["bob_thesis"] == "Vou analisar penny stocks de alta adrenalina."
    assert "Vou analisar penny stocks de alta adrenalina." in result["bob_reasoning_trace"]
    assert result["current_datetime"] != ""
    assert result["agent_tool_call"]["tool"] == "market_scan"


@pytest.mark.asyncio
async def test_tool_executor_sovereign_mode_bypasses_permissions(monkeypatch):
    monkeypatch.setenv("SUPEREZIO_BOB_SOVEREIGN", "1")

    # Even if allowed_tools is restricted, sovereign mode bypasses it
    state = {
        "agent_tool_call": {"tool": "market_scan", "args": {"query": "penny stocks"}},
        "allowed_tools": ["final_answer"],  # Normally blocks market_scan
        "scanner_allowed": False,
        "executed_tools": [],
        "executed_tool_counts": {},
    }

    # Mock node_collector (which is called inside market_scan block)
    async def mock_node_collector(state, config=None):
        return {"scan": {"candidates": [], "rejected_count": 0}}

    import src.core.pipeline.nodes.tool_executor as tool_executor_module

    monkeypatch.setattr(tool_executor_module, "node_collector", mock_node_collector)

    result = await node_tool_executor(state, gateway=None, config=None)

    assert "tool_blocked" not in result
    assert result["executed_tools"] == ["market_scan"]
