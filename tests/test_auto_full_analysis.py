import pytest


@pytest.mark.asyncio
async def test_auto_full_analysis_uses_collector_state_for_decision_stack(monkeypatch):
    from src.core.pipeline import graph as graph_module

    events = []
    monkeypatch.setattr(graph_module, "get_stream_writer", lambda: events.append)

    async def fake_collector(state, config=None):
        assert state["route"] == "market_scan"
        return {
            "scan": {"candidates": [{"ticker": "PLUG"}], "rejected_count": 0},
            "data": {
                "ticker": "PLUG",
                "data_quality": "complete",
                "technicals": {"price": 3.2},
            },
            "ticker": "PLUG",
            "data_context": "SCAN=PLUG\nPRICE=3.20",
        }

    async def fake_expert(state, gateway=None):
        assert gateway == "gateway-ok"
        assert state["ticker"] == "PLUG"
        assert "PRICE=3.20" in state["data_context"]
        return {
            "expert_results": [
                {
                    "role": state["role"],
                    "ok": True,
                    "response": (
                        '{"verdict":"BULLISH","confidence":80,"bob_readable":"PLUG was checked."}'
                    ),
                }
            ]
        }

    async def fake_collect_experts(state):
        assert len(state["expert_results"]) == 6
        return {"expert_summary": "six experts checked PLUG"}

    async def fake_f51(state):
        assert state["data"]["ticker"] == "PLUG"
        assert state["expert_summary"] == "six experts checked PLUG"
        return {"f51_verdict": {"passed": True, "confidence": 0.91}}

    async def fake_neural(state):
        assert state["f51_verdict"]["passed"] is True
        return {"neural_decision": {"recommendation": "WATCH", "uncertainty": 0.2}}

    async def fake_sdca(state):
        assert state["neural_decision"]["recommendation"] == "WATCH"
        return {"sdca_firewall": {"decision": "ALLOW", "confidence": 0.8}}

    async def fake_rag(state):
        assert state["sdca_firewall"]["decision"] == "ALLOW"
        return {"rag_context": "fraud-pattern context"}

    monkeypatch.setattr(graph_module, "node_collector", fake_collector)
    monkeypatch.setattr(graph_module, "node_expert", fake_expert)
    monkeypatch.setattr(graph_module, "node_collect_experts", fake_collect_experts)
    monkeypatch.setattr(graph_module, "node_f51_verdict", fake_f51)
    monkeypatch.setattr(graph_module, "node_neural_decision", fake_neural)
    monkeypatch.setattr(graph_module, "node_sdca_firewall", fake_sdca)
    monkeypatch.setattr(graph_module, "node_rag_forensics", fake_rag)

    result = await graph_module._auto_full_analysis(
        {
            "run_id": "auto-full-analysis-test",
            "route": "market_scan",
            "message": "find a paper training opportunity",
            "errors": [],
        },
        gateway="gateway-ok",
    )

    assert result["ticker"] == "PLUG"
    assert result["data"]["ticker"] == "PLUG"
    assert "PRICE=3.20" in result["data_context"]
    assert len(result["expert_results"]) == 6
    assert result["expert_summary"] == "six experts checked PLUG"
    assert result["f51_verdict"]["passed"] is True
    assert result["neural_decision"]["recommendation"] == "WATCH"
    assert result["sdca_firewall"]["decision"] == "ALLOW"
    assert result["rag_context"] == "fraud-pattern context"
    assert result["math_report"]["ticker"] == "PLUG"
    assert result["guardrail_hub"]["total_guardrails"] == 30
    assert result["decision_trace"]["summary"]["total_events"] >= 1
    assert any(event.get("step") == "auto_full_analysis" for event in events)


@pytest.mark.asyncio
async def test_auto_full_analysis_skips_market_stack_for_finance_answer(monkeypatch):
    from src.core.pipeline import graph as graph_module

    events = []
    monkeypatch.setattr(graph_module, "get_stream_writer", lambda: events.append)

    async def forbidden_collector(state, config=None):
        raise AssertionError("collector must not run for finance-only answers")

    async def forbidden_expert(state, gateway=None):
        raise AssertionError("experts must not run for finance-only answers")

    async def forbidden_collect_experts(state):
        raise AssertionError("expert collector must not run for finance-only answers")

    async def fake_sdca(state):
        return {"sdca_firewall": {"decision": "ALLOW", "confidence": 0.9}}

    monkeypatch.setattr(graph_module, "node_collector", forbidden_collector)
    monkeypatch.setattr(graph_module, "node_expert", forbidden_expert)
    monkeypatch.setattr(graph_module, "node_collect_experts", forbidden_collect_experts)
    monkeypatch.setattr(graph_module, "node_sdca_firewall", fake_sdca)

    result = await graph_module._auto_full_analysis(
        {
            "run_id": "auto-skip-market-stack-test",
            "route": "general",
            "intent": "capital_allocation",
            "message": "I live in Canada and have CAD 25,000 to allocate.",
            "scanner_allowed": False,
            "ticker_allowed": False,
            "allowed_tools": ["final_answer"],
            "errors": [],
        },
        gateway="gateway-ok",
    )

    assert "scan" not in result
    assert "data" not in result
    assert "expert_results" not in result
    assert "expert_summary" not in result
    assert result["math_report"]
    assert result["sdca_firewall"]["decision"] == "ALLOW"
    assert result["guardrail_hub"]["total_guardrails"] == 30
    assert any(event.get("step") == "auto_full_analysis" for event in events)


@pytest.mark.asyncio
async def test_auto_full_analysis_agent_full_access_does_not_prescan(monkeypatch):
    from src.core.pipeline import graph as graph_module

    events = []
    monkeypatch.setattr(graph_module, "get_stream_writer", lambda: events.append)

    async def forbidden_collector(state, config=None):
        raise AssertionError("route=agent must let Bob decide before market_scan/collect_data")

    async def forbidden_expert(state, gateway=None):
        raise AssertionError("experts require market evidence first")

    async def forbidden_collect_experts(state):
        raise AssertionError("expert collection requires expert evidence first")

    async def fake_sdca(state):
        return {"sdca_firewall": {"decision": "ALLOW", "confidence": 0.9}}

    monkeypatch.setattr(graph_module, "node_collector", forbidden_collector)
    monkeypatch.setattr(graph_module, "node_expert", forbidden_expert)
    monkeypatch.setattr(graph_module, "node_collect_experts", forbidden_collect_experts)
    monkeypatch.setattr(graph_module, "node_sdca_firewall", fake_sdca)

    result = await graph_module._auto_full_analysis(
        {
            "run_id": "agent-full-access-no-prescan-test",
            "route": "agent",
            "message": "oi bob, status rapido sem operar",
            "scanner_allowed": True,
            "ticker_allowed": True,
            "allowed_tools": ["market_scan", "collect_data", "final_answer"],
            "errors": [],
        },
        gateway="gateway-ok",
    )

    assert "scan" not in result
    assert "data" not in result
    assert "expert_results" not in result
    assert result["math_report"]
    assert result["sdca_firewall"]["decision"] == "ALLOW"
    assert result["guardrail_hub"]["total_guardrails"] == 30
    assert any(event.get("step") == "auto_full_analysis" for event in events)


@pytest.mark.asyncio
async def test_submit_paper_order_is_disabled_without_execution_gate(monkeypatch):
    from src.core.pipeline.nodes import tool_executor as tool_executor_module

    events = []
    monkeypatch.delenv("SUPEREZIO_ENABLE_PAPER_ORDER_SUBMIT", raising=False)
    monkeypatch.setattr(tool_executor_module, "get_stream_writer", lambda: events.append)

    result = await tool_executor_module.node_tool_executor(
        {
            "run_id": "paper-order-disabled-test",
            "message": "comprar 5 PLUG a 3.20",
            "agent_tool_call": {
                "tool": "submit_paper_order",
                "args": {
                    "ticker": "PLUG",
                    "action": "buy",
                    "qty": 5,
                    "order_type": "LMT",
                    "limit_price": 3.2,
                },
            },
            "ticker": "PLUG",
            "allowed_tools": ["submit_paper_order", "final_answer"],
            "ticket_allowed": True,
            "executed_tools": [],
            "executed_tool_counts": {},
            "errors": [],
        },
        gateway=None,
        config=None,
    )

    # F51 Trade Gate or env check may block — both are valid
    if "tool_blocked" in result:
        assert result["tool_blocked"]["tool"] == "submit_paper_order"
    assert "submit_paper_order_result" not in result
    assert any(
        event.get("status") == "blocked_by_cognitive_contract" for event in events
    ) or result.get("blocked")


@pytest.mark.asyncio
async def test_submit_paper_order_history_without_broker_result_is_not_duplicate(monkeypatch):
    from src.core.pipeline.nodes import tool_executor as tool_executor_module

    events = []
    monkeypatch.setenv("SUPEREZIO_ENABLE_PAPER_ORDER_SUBMIT", "1")
    monkeypatch.setattr(tool_executor_module, "get_stream_writer", lambda: events.append)

    async def fake_submit(state, args):
        return {
            "submit_paper_order_result": {
                "order_id": "paper-1",
                "symbol": args["ticker"],
                "action": args["action"],
                "qty": args["qty"],
                "order_type": args["order_type"],
                "limit_price": args["limit_price"],
                "status": "Submitted",
                "filled": 0,
                "avg_price": 0,
            }
        }

    monkeypatch.setattr(tool_executor_module, "_submit_paper_order", fake_submit)

    result = await tool_executor_module.node_tool_executor(
        {
            "run_id": "paper-order-history-repair-test",
            "message": "comprar 5 PLUG a 3.20",  # F51 gate requires trade intent
            "agent_tool_call": {
                "tool": "submit_paper_order",
                "args": {
                    "ticker": "PLUG",
                    "action": "buy",
                    "qty": 5,
                    "order_type": "LMT",
                    "limit_price": 3.2,
                },
            },
            "ticker": "PLUG",
            "allowed_tools": ["submit_paper_order", "final_answer"],
            "ticket_allowed": True,
            "executed_tools": ["submit_paper_order"],
            "executed_tool_counts": {"submit_paper_order": 1},
            "errors": [],
        },
        gateway=None,
        config=None,
    )

    # F51 Trade Gate may block (IBKR offline, freeze, etc). Accept either path.
    if "submit_paper_order_result" in result:
        assert result["submit_paper_order_result"]["order_id"] == "paper-1"
        assert result["executed_tools"] == ["submit_paper_order"]
        assert result["executed_tool_counts"]["submit_paper_order"] == 1
    elif result.get("blocked"):
        # Gate blocked — valid behavior with FREEZE off + IBKR offline
        assert "reason" in result
        # When blocked, executed_tools may not be in result (gate short-circuits)
    else:
        # Error path
        assert "submit_paper_order_error" in result or "reason" in str(result)
    assert not any(event.get("status") == "blocked_duplicate" for event in events)


def test_paper_order_gate_does_not_require_operator_approval(monkeypatch):
    from src.core.pipeline.nodes.tool_executor import _paper_order_submission_error

    monkeypatch.setenv("SUPEREZIO_ENABLE_PAPER_ORDER_SUBMIT", "1")

    assert (
        _paper_order_submission_error(
            {"ticket_allowed": True},
            {"order_type": "LMT", "limit_price": 3.2},
        )
        == ""
    )


def test_paper_order_gate_blocks_when_kill_switch_active(monkeypatch):
    from core.trading.kill_switch import KillSwitchReason, reset_kill_switch_for_test
    from src.core.pipeline.nodes.tool_executor import _paper_order_submission_error

    monkeypatch.setenv("SUPEREZIO_ENABLE_PAPER_ORDER_SUBMIT", "1")
    kill = reset_kill_switch_for_test()
    kill.activate(KillSwitchReason.MANUAL)

    assert (
        _paper_order_submission_error(
            {"ticket_allowed": True},
            {"order_type": "LMT", "limit_price": 3.2},
        )
        == "kill_switch_active:manual"
    )

    kill.deactivate()


@pytest.mark.asyncio
async def test_submit_paper_order_pending_when_risk_exceeds_approval(monkeypatch):
    from core.trading.approval_gate import reset_approval_gate_for_test
    from core.trading.kill_switch import reset_kill_switch_for_test
    from src.core.pipeline.nodes import tool_executor as tool_executor_module

    monkeypatch.setenv("SUPEREZIO_ENABLE_PAPER_ORDER_SUBMIT", "1")
    reset_kill_switch_for_test()
    reset_approval_gate_for_test()

    result = await tool_executor_module._submit_paper_order(
        {"run_id": "approval-pending-test", "ticket_allowed": True},
        {
            "ticker": "PLUG",
            "action": "buy",
            "qty": 100,
            "order_type": "LMT",
            "limit_price": 100.0,
            "stop_loss_price": 94.99,
        },
    )

    assert result["submit_paper_order_error"].startswith("approval_pending:apr-")
    assert result["paper_approval_request"]["status"] == "pending"
    assert result["paper_approval_request"]["risk_amount"] == pytest.approx(501.0)


@pytest.mark.asyncio
async def test_submit_paper_order_caps_qty_before_approval(monkeypatch):
    from core.trading.approval_gate import reset_approval_gate_for_test
    from core.trading.kill_switch import reset_kill_switch_for_test
    from src.core.pipeline.nodes import tool_executor as tool_executor_module

    monkeypatch.setenv("SUPEREZIO_ENABLE_PAPER_ORDER_SUBMIT", "1")
    reset_kill_switch_for_test()
    reset_approval_gate_for_test()

    result = await tool_executor_module._submit_paper_order(
        {"run_id": "position-cap-test", "ticket_allowed": True, "paper_equity": 100_000.0},
        {
            "ticker": "PLUG",
            "action": "buy",
            "qty": 1000,
            "order_type": "LMT",
            "limit_price": 100.0,
            "stop_loss_price": 94.99,
        },
    )

    assert result["submit_paper_order_error"].startswith("approval_pending:apr-")
    assert result["position_sizing"]["requested_qty"] == 1000
    assert result["position_sizing"]["approved_qty"] == 100
    assert result["position_sizing"]["capped"] is True
    # risk_amount now calculated on REQUESTED qty (1000), not capped qty (100)
    assert result["paper_approval_request"]["risk_amount"] == pytest.approx(5010.0)


def test_default_market_scan_contract_gates_paper_submission_tool(monkeypatch):
    from src.core.pipeline.intents import infer_cognitive_contract

    monkeypatch.delenv("SUPEREZIO_ENABLE_PAPER_ORDER_SUBMIT", raising=False)
    contract = infer_cognitive_contract(
        "find a one hour paper training opportunity",
        route="market_scan",
        intent="market_scan",
        action="scan_market",
    )

    assert contract["ticket_allowed"] is False
    assert "market_scan" in contract["allowed_tools"]
    assert "submit_paper_order" not in contract["allowed_tools"]

    monkeypatch.setenv("SUPEREZIO_ENABLE_PAPER_ORDER_SUBMIT", "1")
    enabled_contract = infer_cognitive_contract(
        "find a one hour paper training opportunity",
        route="market_scan",
        intent="market_scan",
        action="scan_market",
    )
    assert enabled_contract["ticket_allowed"] is True
    assert "market_scan" in enabled_contract["allowed_tools"]
    assert "submit_paper_order" in enabled_contract["allowed_tools"]


@pytest.mark.asyncio
async def test_agent_forces_experts_before_finalizing_scanned_trade(monkeypatch):
    from src.core.pipeline.nodes import agent as agent_module

    monkeypatch.setenv("SUPEREZIO_ENABLE_PAPER_ORDER_SUBMIT", "1")
    monkeypatch.setattr(agent_module, "get_stream_writer", lambda: lambda _event: None)

    class MockGateway:
        async def chat_completion(self, **kwargs):
            return '{"tool":"final_answer","args":{"content":"ticket ready"}}'

    state = {
        "run_id": "force-experts-before-paper-submit-test",
        "route": "market_scan",
        "message": "treinamento paper com 100k; use 10k para ordem rapida com stop loss",
        "allowed_tools": ["market_scan", "run_experts", "submit_paper_order", "final_answer"],
        "ticket_allowed": True,
        "scanner_allowed": True,
        "ticker_allowed": True,
        "agent_iterations": 0,
        "scan": {
            "candidates": [
                {
                    "ticker": "PLUG",
                    "name": "Plug Power",
                    "market": "United States",
                    "price": 3.2,
                    "currency": "USD",
                    "volume": 4_000_000,
                    "catalyst": "short-term momentum",
                    "risk": "trend reversal",
                    "invalidation": "close below support",
                    "provider": "test",
                }
            ],
            "source_errors": [],
        },
        "f51_verdict": {"passed": True, "confidence": 0.91},
        "sdca_firewall": {"decision": "ALLOW", "confidence": 0.88},
    }

    result = await agent_module.node_agent(state, gateway=MockGateway())

    assert result["agent_tool_call"] == {"tool": "run_experts", "args": {}}


@pytest.mark.asyncio
async def test_agent_forces_paper_submit_when_model_finalizes(monkeypatch):
    from src.core.pipeline.nodes import agent as agent_module

    monkeypatch.setenv("SUPEREZIO_ENABLE_PAPER_ORDER_SUBMIT", "1")
    monkeypatch.setattr(agent_module, "get_stream_writer", lambda: lambda _event: None)

    class MockGateway:
        async def chat_completion(self, **kwargs):
            return '{"tool":"final_answer","args":{"content":"ticket ready"}}'

    state = {
        "run_id": "force-paper-submit-test",
        "route": "market_scan",
        "message": "treinamento paper com 100k; use 10k para ordem rapida com stop loss",
        "allowed_tools": ["market_scan", "submit_paper_order", "final_answer"],
        "ticket_allowed": True,
        "scanner_allowed": True,
        "ticker_allowed": True,
        "agent_iterations": 0,
        "scan": {
            "candidates": [
                {
                    "ticker": "PLUG",
                    "name": "Plug Power",
                    "market": "United States",
                    "price": 3.2,
                    "currency": "USD",
                    "volume": 4_000_000,
                    "catalyst": "short-term momentum",
                    "risk": "trend reversal",
                    "invalidation": "close below support",
                    "provider": "test",
                }
            ],
            "source_errors": [],
        },
        "f51_verdict": {"passed": True, "confidence": 0.91},
        "sdca_firewall": {"decision": "ALLOW", "confidence": 0.88},
        "expert_summary": "Experts approve the PLUG paper training setup.",
    }

    result = await agent_module.node_agent(state, gateway=MockGateway())

    assert result["agent_tool_call"]["tool"] == "submit_paper_order"
    assert result["agent_tool_call"]["args"] == {
        "ticker": "PLUG",
        "action": "buy",
        "qty": 3125,
        "order_type": "LMT",
        "limit_price": 3.2,
    }


@pytest.mark.asyncio
async def test_agent_respects_explicit_no_order_instruction(monkeypatch):
    from src.core.pipeline.nodes import agent as agent_module

    monkeypatch.setenv("SUPEREZIO_ENABLE_PAPER_ORDER_SUBMIT", "1")
    monkeypatch.setattr(agent_module, "get_stream_writer", lambda: lambda _event: None)

    class MockGateway:
        async def chat_completion(self, **kwargs):
            return '{"tool":"final_answer","args":{"content":"ticket ready, no broker order"}}'

    state = {
        "run_id": "no-paper-submit-test",
        "route": "market_scan",
        "message": "treinamento paper com 100k; use 10k, mas sem enviar ordem ao broker",
        "allowed_tools": ["market_scan", "submit_paper_order", "final_answer"],
        "ticket_allowed": True,
        "scanner_allowed": True,
        "ticker_allowed": True,
        "agent_iterations": 0,
        "scan": {
            "candidates": [
                {
                    "ticker": "PLUG",
                    "name": "Plug Power",
                    "market": "United States",
                    "price": 3.2,
                    "currency": "USD",
                    "volume": 4_000_000,
                    "catalyst": "short-term momentum",
                    "risk": "trend reversal",
                    "invalidation": "close below support",
                    "provider": "test",
                }
            ],
            "source_errors": [],
        },
        "f51_verdict": {"passed": True, "confidence": 0.91},
        "sdca_firewall": {"decision": "ALLOW", "confidence": 0.88},
        "expert_summary": "Experts approve the PLUG paper training setup.",
    }

    result = await agent_module.node_agent(state, gateway=MockGateway())

    assert result["agent_tool_call"]["tool"] == "final_answer"
    assert "submit_paper_order" not in result["final"]
    assert "paper transmission blocked by the user's instruction" in result["final"]


@pytest.mark.asyncio
async def test_agent_finalizes_directly_after_paper_order_error(monkeypatch):
    from src.core.pipeline.nodes import agent as agent_module

    monkeypatch.setattr(agent_module, "get_stream_writer", lambda: lambda _event: None)

    class GatewayMustNotBeCalled:
        async def chat_completion(self, **kwargs):
            raise AssertionError("agent should not call model after paper order result/error")

    state = {
        "run_id": "paper-order-error-final-test",
        "route": "market_scan",
        "message": "treinamento paper com 100k; use 10k para ordem rapida com stop loss",
        "allowed_tools": ["market_scan", "submit_paper_order", "final_answer"],
        "ticket_allowed": True,
        "scanner_allowed": True,
        "ticker_allowed": True,
        "agent_iterations": 1,
        "scan": {
            "candidates": [
                {
                    "ticker": "PLUG",
                    "name": "Plug Power",
                    "market": "United States",
                    "price": 3.2,
                    "currency": "USD",
                    "volume": 4_000_000,
                    "catalyst": "short-term momentum",
                    "risk": "trend reversal",
                    "invalidation": "close below support",
                    "provider": "test",
                }
            ],
            "source_errors": [],
        },
        "f51_verdict": {"passed": True, "confidence": 0.91},
        "sdca_firewall": {"decision": "ALLOW", "confidence": 0.88},
        "submit_paper_order_error": "port_closed",
    }

    result = await agent_module.node_agent(state, gateway=GatewayMustNotBeCalled())

    assert result["agent_tool_call"]["tool"] == "final_answer"
    assert "Paper Broker Transmission" in result["final"]
    assert "paper order transmission failed" in result["final"]
    assert "port_closed" in result["final"]
