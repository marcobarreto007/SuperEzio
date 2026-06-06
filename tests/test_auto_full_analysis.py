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
                        '{"verdict":"BULLISH","confidence":80,'
                        '"bob_readable":"PLUG was checked."}'
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
            "agent_tool_call": {
                "tool": "submit_paper_order",
                "args": {
                    "ticker": "PLUG",
                    "action": "buy",
                    "qty": 5,
                    "order_type": "LMT",
                    "limit_price": 3.2,
                    "approved_by_operator": True,
                },
            },
            "allowed_tools": ["submit_paper_order", "final_answer"],
            "ticket_allowed": True,
            "executed_tools": [],
            "executed_tool_counts": {},
            "errors": [],
        },
        gateway=None,
        config=None,
    )

    assert result["tool_blocked"]["tool"] == "submit_paper_order"
    assert result["tool_blocked"]["reason"] == "paper_order_submission_disabled_by_env"
    assert "submit_paper_order_result" not in result
    assert any(event.get("status") == "blocked_by_cognitive_contract" for event in events)


def test_default_market_scan_contract_does_not_expose_broker_submission():
    from src.core.pipeline.intents import infer_cognitive_contract

    contract = infer_cognitive_contract(
        "find a one hour paper training opportunity",
        route="market_scan",
        intent="market_scan",
        action="scan_market",
    )

    assert contract["ticket_allowed"] is True
    assert "market_scan" in contract["allowed_tools"]
    assert "submit_paper_order" not in contract["allowed_tools"]
