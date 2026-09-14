import pytest

from src.core.pipeline.nodes.agent import (
    LOCAL_AGENT_INPUT_CHAR_BUDGET,
    _fit_messages_to_local_context,
    _parse_tool_calls,
    node_agent,
)
from src.core.pipeline.nodes.orchestrator import node_orchestrator
from src.core.pipeline.nodes.tool_executor import node_tool_executor


def test_local_prompt_budget_trims_reports_before_binding_contracts():
    # Anexos dimensionados a partir do orcamento real: assim o teste continua
    # provando TRUNCAMENTO quando a janela local mudar, em vez de virar um
    # numero magico que so vale para uma janela. (24_000 fixo quebrava quando
    # o orcamento subiu para 288_000 em 11/09/2026.)
    orcamento = LOCAL_AGENT_INPUT_CHAR_BUDGET
    messages = [
        {"role": "system", "content": "binding-system" * 300},
        {"role": "system", "content": "binding-verdict" * 300},
        {"role": "user", "content": "Pipeline Report:\n" + "P" * orcamento},
        {"role": "user", "content": "Observations so far:\n" + "O" * (orcamento // 2)},
        {"role": "user", "content": "final instruction"},
    ]

    fitted = _fit_messages_to_local_context(messages)

    assert sum(len(message["content"]) for message in fitted) <= orcamento
    assert fitted[0]["content"] == messages[0]["content"]
    assert fitted[1]["content"] == messages[1]["content"]
    assert fitted[-1]["content"] == "final instruction"
    assert any("TRUNCATED TO FIT LOCAL CONTEXT" in message["content"] for message in fitted)


@pytest.mark.asyncio
async def test_orchestrator_sovereign_mode(monkeypatch):
    monkeypatch.setenv("SUPEREZIO_BOB_SOVEREIGN", "1")
    monkeypatch.setattr(
        "src.core.pipeline.nodes.orchestrator.get_stream_writer", lambda: lambda x: None
    )

    state = {
        "message": "cara, em vez de gastar 40 CAD na Lotto Quebec, acha uma penny stock que me dê adrenalina sem perder tudo",
        "trade_order_context": {"time_horizon": "14 days"},
    }

    plan = await node_orchestrator(state, gateway=None, config=None)

    assert plan["route"] == "agent"
    assert plan["intent"] == "bob_decides"
    assert plan["ticker"] == ""
    assert plan["risk_tolerance"] == "moderada"
    assert plan["bob_intent"] == "market_scan"
    assert "market_scan" in plan["allowed_tools"]
    assert "collect_data" in plan["allowed_tools"]
    assert plan["scanner_allowed"] is True
    assert plan["ticker_allowed"] is True
    assert plan["ticket_allowed"] is False
    assert plan["cognitive_mode"] == "MARKET_DISCOVERY"
    assert "submit_paper_order" not in plan["allowed_tools"]


@pytest.mark.asyncio
async def test_orchestrator_preserves_selected_ui_ticker(monkeypatch):
    monkeypatch.setenv("SUPEREZIO_BOB_SOVEREIGN", "1")
    monkeypatch.setattr(
        "src.core.pipeline.nodes.orchestrator.get_stream_writer", lambda: lambda x: None
    )

    plan = await node_orchestrator(
        {"message": "TICKER DIBS: sincronize com o grafico atual", "ticker": "dibs"},
        gateway=None,
        config=None,
    )

    assert plan["route"] == "agent"
    assert plan["intent"] == "bob_decides"
    assert plan["ticker"] == "DIBS"
    assert "sem dados" in plan["answer_contract"]


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

    assert plan["route"] == "agent"
    assert plan["action"] == "analyze_and_execute"
    assert plan["required_slots"] == []
    assert plan["bob_intent"] == "general_answer"
    assert plan["scanner_allowed"] is False
    assert plan["ticker_allowed"] is False
    assert "final_answer" in plan["allowed_tools"]


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


def test_parse_tool_calls_returns_multiple_valid_calls():
    calls = _parse_tool_calls(
        '[{"tool":"collect_data","args":{"ticker":"AAPL"}},'
        '{"tool":"sdca_firewall","args":{"decision":"review"}}]'
    )

    assert [call["tool"] for call in calls] == ["collect_data", "sdca_firewall"]
    assert calls[0]["args"]["ticker"] == "AAPL"


@pytest.mark.asyncio
async def test_agent_sovereign_mode_queues_extra_tool_calls(monkeypatch):
    monkeypatch.setenv("SUPEREZIO_BOB_SOVEREIGN", "1")
    monkeypatch.setattr("src.core.pipeline.nodes.agent.get_stream_writer", lambda: lambda x: None)

    class MockGateway:
        async def chat_completion(self, **kwargs):
            return (
                '[{"tool":"collect_data","args":{"ticker":"AAPL"}},'
                '{"tool":"sdca_firewall","args":{"decision":"review"}}]'
            )

    result = await node_agent(
        {
            "message": "run the full checks",
            "agent_iterations": 0,
            "bob_reasoning_trace": [],
        },
        gateway=MockGateway(),
        config=None,
    )

    assert result["agent_tool_call"]["tool"] == "collect_data"
    assert [call["tool"] for call in result["_pending_tool_calls"]] == ["sdca_firewall"]


@pytest.mark.asyncio
async def test_tool_executor_sovereign_mode_respects_permissions(monkeypatch):
    monkeypatch.setenv("SUPEREZIO_BOB_SOVEREIGN", "1")
    monkeypatch.setattr(
        "src.core.pipeline.nodes.tool_executor.get_stream_writer", lambda: lambda x: None
    )

    state = {
        "agent_tool_call": {"tool": "market_scan", "args": {"query": "penny stocks"}},
        "allowed_tools": ["final_answer"],
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

    assert result["tool_blocked"]["tool"] == "market_scan"
    assert "cognitive_contract" in result["tool_blocked"]["reason"]
    assert result["executed_tools"] == []
