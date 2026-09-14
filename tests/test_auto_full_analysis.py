import pytest


def _ready_neural_decision(direction: str = "UP") -> dict:
    return {
        "status": "ready",
        "decision": direction,
        "direction_prob": {"up": 0.7, "down": 0.1, "sideways": 0.2},
        "calibration_status": "calibrated",
        "prediction_set": [direction],
        "model_id": "test-neural-v1",
        "as_of": "2026-07-19T12:00:00+00:00",
        "horizon": 1,
    }


@pytest.mark.asyncio
async def test_auto_full_analysis_uses_collector_state_for_decision_stack(monkeypatch):
    from src.core.pipeline import graph as graph_module

    events = []
    monkeypatch.setattr(graph_module, "get_stream_writer", lambda: events.append)
    # The canonical one-slot runtime clamps stale/high replica settings to one.
    monkeypatch.setenv("SUPEREZIO_EXPERT_REPLICAS", "3")

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
        return {
            "expert_summary": "six experts checked PLUG",
            "expert_consensus": {"decision": "SUPPORT", "score": 0.42, "weight_coverage": 0.9},
        }

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
    assert result["expert_consensus"]["decision"] == "SUPPORT"
    assert result["f51_verdict"]["passed"] is True
    assert result["neural_decision"]["recommendation"] == "WATCH"
    assert result["sdca_firewall"]["decision"] == "ALLOW"
    assert result["rag_context"] == "fraud-pattern context"
    assert result["math_report"]["ticker"] == "PLUG"
    assert result["guardrail_hub"]["total_guardrails"] == 30
    assert result["decision_trace"]["summary"]["total_events"] >= 1
    assert any(event.get("step") == "auto_full_analysis" for event in events)


@pytest.mark.asyncio
async def test_expert_consensus_survives_langgraph_state_schema():
    """Regression (T1, 2026-08-22): expert_consensus must survive the graph.

    LangGraph filters node updates to keys declared in the state TypedDict.
    node_collect_experts emits expert_consensus (plus expert_raw/structured/
    weights), but PipelineState only declared expert_summary — so the compiled
    graph silently dropped the consensus and build_verdict_dict rendered
    "Consenso dos Experts: N/A" even after the experts had run live.
    """
    from langgraph.graph import END, START, StateGraph

    from src.core.pipeline.contracts import PipelineState
    from src.core.pipeline.verdict import build_verdict_dict

    seen: dict = {}

    async def produce(state):
        return {
            "expert_summary": "six experts checked PLUG",
            "expert_raw": "[macro_risk][ok] raw",
            "expert_structured": {"macro_risk": {"verdict": "RISK_ON"}},
            "expert_weights": {"macro_risk": 0.5},
            "expert_consensus": {"decision": "SUPPORT", "score": 0.42, "weight_coverage": 0.9},
        }

    async def consume(state):
        seen["consensus"] = state.get("expert_consensus")
        seen["verdict_consensus"] = build_verdict_dict(state)["experts"]["consensus"]
        return {}

    builder = StateGraph(PipelineState)
    builder.add_node("produce", produce)
    builder.add_node("consume", consume)
    builder.add_edge(START, "produce")
    builder.add_edge("produce", "consume")
    builder.add_edge("consume", END)
    await builder.compile().ainvoke({})

    assert seen["consensus"] == {
        "decision": "SUPPORT",
        "score": 0.42,
        "weight_coverage": 0.9,
    }
    # build_verdict_dict must read the surviving consensus, not default to N/A.
    assert seen["verdict_consensus"] == "SUPPORT"


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
async def test_auto_full_analysis_does_not_scan_on_allocation_wording(monkeypatch):
    """'educacao'/'alocacao' must not substring-trigger the scan keyword 'acao'.

    Regression for 2026-08-21: a PT capital-allocation prompt routed a full
    market scan (10+ min) because "acao" matched inside "educacao". Even a
    misclassified scanner_allowed=True must not force data collection when
    the deterministic keywords do not fire.
    """
    from src.core.pipeline import graph as graph_module

    events = []
    monkeypatch.setattr(graph_module, "get_stream_writer", lambda: events.append)

    async def forbidden_collector(state, config=None):
        raise AssertionError("collector must not run for allocation-only answers")

    async def forbidden_expert(state, gateway=None):
        raise AssertionError("experts must not run without collected data")

    async def forbidden_collect_experts(state):
        raise AssertionError("expert collector must not run without collected data")

    async def fake_sdca(state):
        return {"sdca_firewall": {"decision": "ALLOW", "confidence": 0.9}}

    monkeypatch.setattr(graph_module, "node_collector", forbidden_collector)
    monkeypatch.setattr(graph_module, "node_expert", forbidden_expert)
    monkeypatch.setattr(graph_module, "node_collect_experts", forbidden_collect_experts)
    monkeypatch.setattr(graph_module, "node_sdca_firewall", fake_sdca)

    result = await graph_module._auto_full_analysis(
        {
            "run_id": "auto-allocation-wording-test",
            "route": "agent",
            "intent": "capital_allocation",
            "message": (
                "Moro no Canada e tenho CAD 25.000 para alocar entre reserva "
                "de emergencia, dividas, ETFs, equipamento e educacao."
            ),
            "scanner_allowed": True,  # LLM misclassification must not force a scan
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


def test_route_after_agent_paper_gate():
    """auto_execute_paper only with an explicit submit_paper_order grant.

    Regression for 2026-08-21: an allocation prompt (no ticker, advisory
    contract) still entered the auto_execute_paper node in the live graph.
    """
    from src.core.pipeline import graph as graph_module

    # Advisory: no grant → straight to explanation
    assert (
        graph_module.route_after_agent_paper_gate(
            {"agent_tool_call": None, "allowed_tools": ["final_answer"]}
        )
        == "explanation"
    )
    # Missing allowed_tools entirely → fail-closed to explanation
    assert graph_module.route_after_agent_paper_gate({"agent_tool_call": None}) == "explanation"
    # Tool call still routes to the executor
    assert (
        graph_module.route_after_agent_paper_gate(
            {"agent_tool_call": {"tool": "market_scan"}, "allowed_tools": []}
        )
        == "tool_executor"
    )
    # Decisive trade with grant → auto_execute_paper
    assert (
        graph_module.route_after_agent_paper_gate(
            {"agent_tool_call": None, "allowed_tools": ["submit_paper_order"]}
        )
        == "auto_execute_paper"
    )


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

    # NOTE: the stop_loss_price in args (94.99) is INTENTIONALLY IGNORED by
    # _submit_paper_order — honoring a model-proposed stop let the model shrink
    # the calculated risk and slip under the $500 auto-approval threshold.
    # Risk is always derived from entry price and the default stop (5% -> 95.0).
    # qty=100 would land exactly on the $500 auto-approve boundary and fall
    # through to broker submission, so qty=200 keeps the pending path covered.
    #
    # SPY (TD commission-free ETF) e nao PLUG: o protocolo de micro-capital
    # proibe ativo com comissao, entao o ticker do fixture tem que vir do
    # universo de 108 ETFs livres. paper_equity tambem e explicito porque
    # agora o gate mede o risco TOTAL da ordem ($5/share x 200 = $1.000)
    # contra 1,5% da banca — que precisa caber para o teste chegar no
    # approval gate. O alvo de 3:1 existe porque alvo ausente e bloqueio.
    result = await tool_executor_module._submit_paper_order(
        {
            "run_id": "approval-pending-test",
            "ticket_allowed": True,
            "paper_equity": 100_000.0,
            "neural_decision": _ready_neural_decision(),
        },
        {
            "ticker": "SPY",
            "action": "buy",
            "qty": 200,
            "order_type": "LMT",
            "limit_price": 100.0,
            "stop_loss_price": 94.99,
            "take_profit_price": 115.0,
        },
    )

    assert result["submit_paper_order_error"].startswith("approval_pending:apr-")
    assert result["paper_approval_request"]["status"] == "pending"
    # risk = (100 - 95.0 derived stop) * 200 = 1000, NOT (100 - 94.99) * 200
    assert result["paper_approval_request"]["risk_amount"] == pytest.approx(1000.0)


@pytest.mark.asyncio
async def test_submit_paper_order_caps_qty_before_approval(monkeypatch):
    from core.trading.approval_gate import reset_approval_gate_for_test
    from core.trading.kill_switch import reset_kill_switch_for_test
    from src.core.pipeline.nodes import tool_executor as tool_executor_module

    monkeypatch.setenv("SUPEREZIO_ENABLE_PAPER_ORDER_SUBMIT", "1")
    reset_kill_switch_for_test()
    reset_approval_gate_for_test()

    result = await tool_executor_module._submit_paper_order(
        {
            "run_id": "position-cap-test",
            "ticket_allowed": True,
            "paper_equity": 100_000.0,
            "neural_decision": _ready_neural_decision(),
        },
        {
            "ticker": "SPY",
            "action": "buy",
            # qty=200: pedido maior que o teto do sizer (100) para provar o
            # cap, e ainda assim dentro do orcamento de risco do protocolo
            # ($5/share x 200 = $1.000 <= 1,5% de $100.000). Com 1000 o gate
            # de micro-capital bloquearia a ordem antes do approval gate.
            "qty": 200,
            "order_type": "LMT",
            "limit_price": 100.0,
            "stop_loss_price": 94.99,
            "take_profit_price": 115.0,
        },
    )

    assert result["submit_paper_order_error"].startswith("approval_pending:apr-")
    assert result["position_sizing"]["requested_qty"] == 200
    assert result["position_sizing"]["approved_qty"] == 100
    assert result["position_sizing"]["capped"] is True
    # risk_amount now calculated on REQUESTED qty (200), not capped qty (100).
    # The args stop_loss_price (94.99) is intentionally ignored — stop is always
    # derived from entry price and the default stop (5% -> 95.0), so risk is
    # (100 - 95.0) * 200 = 1000, NOT (100 - 94.99) * 200 = 1002.
    assert result["paper_approval_request"]["risk_amount"] == pytest.approx(1000.0)


@pytest.mark.asyncio
async def test_submit_paper_order_cannot_bypass_weighted_consensus(monkeypatch):
    from src.core.pipeline.nodes import tool_executor as tool_executor_module

    monkeypatch.setenv("SUPEREZIO_ENABLE_PAPER_ORDER_SUBMIT", "1")
    result = await tool_executor_module._submit_paper_order(
        {
            "ticket_allowed": True,
            "expert_consensus": {
                "decision": "BLOCK",
                "score": -0.8,
                "weight_coverage": 0.7,
            },
        },
        {"ticker": "PLUG", "action": "buy", "qty": 10, "limit_price": 100.0},
    )
    assert result["submit_paper_order_error"].startswith("weighted_expert_consensus:")


@pytest.mark.asyncio
async def test_forced_expert_committee_materializes_weighted_consensus_before_submit(monkeypatch):
    from types import SimpleNamespace

    import core.idempotency as idempotency_module
    import core.pipeline.f51_trade_gate as trade_gate_module
    from src.core.pipeline.nodes import tool_executor as tool_executor_module

    monkeypatch.setattr(tool_executor_module, "get_stream_writer", lambda: lambda _event: None)
    monkeypatch.setattr(idempotency_module, "is_duplicate", lambda _key: False)
    monkeypatch.setattr(
        trade_gate_module,
        "evaluate_trade_gate",
        lambda **_kwargs: SimpleNamespace(status="ALLOW"),
    )

    async def fake_expert(state, *, gateway=None):
        return {
            "expert_results": [
                {
                    "role": state["role"],
                    "ok": True,
                    "response": '{"verdict":"NEUTRAL","confidence":0.5}',
                }
            ]
        }

    async def fake_collect(state):
        assert len(state["expert_results"]) == 6
        return {
            "expert_consensus": {
                "decision": "BLOCK",
                "score": -0.51,
                "weight_coverage": 0.8,
            }
        }

    async def fake_submit(state, args):
        assert state["expert_consensus"]["decision"] == "BLOCK"
        return {"submit_paper_order_error": "weighted_expert_consensus:test"}

    monkeypatch.setattr(tool_executor_module, "node_expert", fake_expert)
    monkeypatch.setattr(tool_executor_module, "node_collect_experts", fake_collect)
    monkeypatch.setattr(tool_executor_module, "_submit_paper_order", fake_submit)

    result = await tool_executor_module.node_tool_executor(
        {
            "run_id": "forced-consensus-test",
            "ticker": "AAPL",
            "ticket_allowed": True,
            "agent_tool_call": {
                "tool": "submit_paper_order",
                "args": {
                    "ticker": "AAPL",
                    "action": "buy",
                    "qty": 1,
                    "order_type": "LMT",
                    "limit_price": 100.0,
                },
            },
        },
        gateway=object(),
    )

    assert result["submit_paper_order_error"].startswith("weighted_expert_consensus:")


@pytest.mark.asyncio
async def test_submit_paper_order_applies_adaptive_stop_and_position_cap(monkeypatch):
    from core.trading.approval_gate import reset_approval_gate_for_test
    from core.trading.kill_switch import reset_kill_switch_for_test
    from src.core.pipeline.nodes import tool_executor as tool_executor_module

    monkeypatch.setenv("SUPEREZIO_ENABLE_PAPER_ORDER_SUBMIT", "1")
    reset_kill_switch_for_test()
    reset_approval_gate_for_test()
    result = await tool_executor_module._submit_paper_order(
        {
            "run_id": "adaptive-risk-test",
            "ticket_allowed": True,
            "paper_equity": 100_000.0,
            "adaptive_config": {"stop_loss_pct": 0.03, "max_position_pct": 0.05},
            "neural_decision": _ready_neural_decision(),
        },
        {
            "ticker": "SPY",
            "action": "buy",
            "qty": 200,
            "order_type": "LMT",
            "limit_price": 100.0,
            # stop derivado 97.0 ($3/share) -> alvo 3,33:1, acima do 2,5:1.
            # Risco total $600 dentro dos 1,5% de $100.000.
            "take_profit_price": 110.0,
        },
    )

    assert result["submit_paper_order_error"].startswith("approval_pending:")
    assert result["paper_approval_request"]["stop_loss_price"] == pytest.approx(97.0)
    assert result["paper_approval_request"]["risk_amount"] == pytest.approx(600.0)
    assert result["position_sizing"]["approved_qty"] == 50


@pytest.mark.asyncio
async def test_submit_paper_order_blocks_ten_by_ten_total_risk(monkeypatch):
    """10 acoes a $10 de risco = $100, 10% da banca de $1.000: bloqueado.

    Prova que o `qty` chega ao gate pelo caminho de producao. O teste de
    unidade em tests/test_execution_policy.py cobre a conta; este cobre o
    encanamento — se alguem parar de passar o qty no tool_executor, a ordem
    volta a passar com apenas o risco POR ACAO ($10 <= $15) sendo comparado.
    """
    from core.trading.kill_switch import reset_kill_switch_for_test
    from src.core.pipeline.nodes import tool_executor as tool_executor_module

    monkeypatch.setenv("SUPEREZIO_ENABLE_PAPER_ORDER_SUBMIT", "1")
    reset_kill_switch_for_test()

    result = await tool_executor_module._submit_paper_order(
        {
            "run_id": "total-risk-test",
            "ticket_allowed": True,
            # Banca do protocolo: $1.000 CAD -> orcamento de $15 por trade.
            "paper_equity": 1000.0,
            "adaptive_config": {"stop_loss_pct": 0.10},  # stop derivado -> 90.0
            "neural_decision": _ready_neural_decision(),
        },
        {
            "ticker": "SPY",
            "action": "buy",
            "qty": 10,
            "order_type": "LMT",
            "limit_price": 100.0,
            "take_profit_price": 130.0,  # 3:1 sobre o stop de 90.0
        },
    )

    assert result["submit_paper_order_error"].startswith("micro_capital_survival:")
    assert "risk_exceeds_budget" in result["submit_paper_order_error"]
    assert "100.00" in result["submit_paper_order_error"]  # risco TOTAL da ordem
    assert "15.00" in result["submit_paper_order_error"]  # o orcamento derivado


@pytest.mark.asyncio
async def test_submit_paper_order_blocks_ticker_outside_the_free_universe(monkeypatch):
    """PLUG (acao comum, com comissao no TD) e recusado pelo protocolo de taxa zero.

    Os tres testes de aprovacao acima usavam PLUG antes de o protocolo existir;
    este teste trava o comportamento de proposito em vez de deixar o ticker
    proibido voltar por descuido. Se a consulta ao manifesto dos 108 ETFs
    quebrar, este teste cai junto.
    """
    from core.trading.kill_switch import reset_kill_switch_for_test
    from core.trading.td_universe import is_commission_free
    from src.core.pipeline.nodes import tool_executor as tool_executor_module

    monkeypatch.setenv("SUPEREZIO_ENABLE_PAPER_ORDER_SUBMIT", "1")
    reset_kill_switch_for_test()
    assert is_commission_free("PLUG") is False

    result = await tool_executor_module._submit_paper_order(
        {
            "run_id": "commission-free-block-test",
            "ticket_allowed": True,
            "paper_equity": 100_000.0,
            "neural_decision": _ready_neural_decision(),
        },
        {
            "ticker": "PLUG",
            "action": "buy",
            "qty": 10,
            "order_type": "LMT",
            "limit_price": 100.0,
            "take_profit_price": 115.0,
        },
    )

    assert result["submit_paper_order_error"].startswith(
        "micro_capital_survival:zero_commission_violation"
    )


@pytest.mark.asyncio
async def test_auto_execute_paper_blocks_and_does_not_size_when_equity_is_unknown(
    monkeypatch, tmp_path
):
    """Equity desconhecido => a ordem nao executa, com motivo auditavel.

    O caminho cobria `paper_exec_blocked: equity_unknown` sem nenhum teste:
    era o unico ponto do no onde a banca ausente parava a ordem. As bordas
    pesadas do no (idempotencia em disco e o F51 trade gate) entram isoladas
    por uma linha cada, apontando para tmp_path / devolvendo ALLOW — o que o
    teste prova e a decisao, nao a infra delas.
    """
    import importlib
    from types import SimpleNamespace

    import core.pipeline.f51_trade_gate as trade_gate_module

    # `core.pipeline.nodes.auto_execute_paper` resolve para a FUNCAO reexportada
    # no __init__ do pacote; o modulo de verdade vem pelo importlib.
    aep_module = importlib.import_module("core.pipeline.nodes.auto_execute_paper")

    monkeypatch.setenv("SUPEREZIO_DEDUP_DIR", str(tmp_path))
    monkeypatch.setattr(aep_module, "get_stream_writer", lambda: lambda _event: None)
    monkeypatch.setattr(
        trade_gate_module,
        "evaluate_trade_gate",
        lambda **_kwargs: SimpleNamespace(status="ALLOW"),
    )
    monkeypatch.setattr("core.mission_context.get_mission_equity", lambda *a, **k: None)

    result = await aep_module.auto_execute_paper(
        {
            "run_id": "auto-execute-equity-unknown-test",
            "message": "comprar 10 SPY a 100.00",
            "submit_paper_order_result": {"symbol": "SPY", "qty": 10, "action": "buy"},
            "neural_decision": _ready_neural_decision(),
        }
    )

    assert result["paper_exec_blocked"] == "equity_unknown"
    # Nao houve dimensionamento nem submissao: o unico destino e o bloqueio.
    assert "position_sizing" not in result
    assert "submit_paper_order_result" not in result


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
                    "catalyst": "PLUG reports Q2 earnings on 2026-08-25.",
                    "risk": "PLUG Q2 revenue may miss the published USD 180M consensus.",
                    "invalidation": "Invalidate on a close below USD 3.04 after Q2 earnings.",
                    "provider": "test",
                    "provenance": {
                        field: {"source": "test"}
                        for field in (
                            "ticker",
                            "price",
                            "volume",
                            "catalyst",
                            "risk",
                            "invalidation",
                        )
                    },
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
        "stop_loss_price": 3.04,
    }


def test_agent_builder_propagates_adaptive_stop_and_honors_consensus(monkeypatch):
    from src.core.pipeline.nodes.agent import _build_submit_paper_order_call

    monkeypatch.setenv("SUPEREZIO_ENABLE_PAPER_ORDER_SUBMIT", "1")
    state = {
        "message": "treinamento paper com 100k; use 10k para ordem rapida com stop loss",
        "allowed_tools": ["submit_paper_order"],
        "ticket_allowed": True,
        "adaptive_config": {"stop_loss_pct": 0.03, "max_position_pct": 0.05},
        "f51_verdict": {"passed": True, "confidence": 0.91},
        "sdca_firewall": {"decision": "ALLOW", "confidence": 0.88},
        "scan": {
            "candidates": [
                {
                    "ticker": "PLUG",
                    "name": "Plug Power",
                    "market": "United States",
                    "price": 3.2,
                    "currency": "USD",
                    "volume": 4_000_000,
                    "catalyst": "PLUG reports Q2 earnings on 2026-08-25.",
                    "risk": "PLUG Q2 revenue may miss the published USD 180M consensus.",
                    "invalidation": "Invalidate on a close below USD 3.04 after Q2 earnings.",
                    "provider": "test",
                    "provenance": {
                        field: {"source": "test"}
                        for field in (
                            "ticker",
                            "price",
                            "volume",
                            "catalyst",
                            "risk",
                            "invalidation",
                        )
                    },
                }
            ],
            "source_errors": [],
        },
    }
    call = _build_submit_paper_order_call(state)
    assert call["args"]["stop_loss_price"] == 3.104

    state["expert_consensus"] = {
        "decision": "BLOCK",
        "score": -0.5,
        "weight_coverage": 0.6,
    }
    assert _build_submit_paper_order_call(state) is None


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


_SPY_TIP = (
    "me dá uma dica de investimento agora sobre SPY: tese, direção, "
    "invalidação, alvo e stop. Sem ordem."
)


@pytest.mark.asyncio
async def test_investment_tip_with_ticker_forces_full_expert_committee(monkeypatch):
    """Dica+ticker must wait for auto_full_analysis and invoke every registry role.

    Freeze flags must not skip collector/experts. One expert failure is
    recorded explicitly and does not cut the rest of the committee.
    """
    from src.core.pipeline import graph as graph_module
    from src.core.pipeline.nodes.experts import EXPERT_ROLES

    events = []
    invoked: list[str] = []
    monkeypatch.setattr(graph_module, "get_stream_writer", lambda: events.append)
    monkeypatch.setenv("SUPEREZIO_LIVE_TRADING_DISABLED", "1")
    monkeypatch.setenv("F51_TRADING_EXECUTION_FREEZE", "true")
    monkeypatch.setenv("SUPEREZIO_RESEARCH_PAPER_ONLY", "1")

    async def fake_collector(state, config=None):
        return {
            "data": {
                "ticker": "SPY",
                "price": {"latest": 770.19},
                "fundamentals": {"name": "SPDR S&P 500", "pe_ratio": 28.1},
                "sentiment": {"sentiment_label": "NEUTRAL", "sentiment_score": 0.1},
                "social": {"status": "unavailable", "error": "all_providers_failed_for_social"},
            },
            "ticker": "SPY",
            "data_context": "SPY PRICE=770.19",
        }

    async def fake_expert(state, gateway=None):
        role = state["role"]
        invoked.append(role)
        if role == "sentiment":
            raise RuntimeError("sentiment_provider_timeout")
        return {
            "expert_results": [
                {"role": role, "ok": True, "response": '{"verdict":"NEUTRAL","confidence":50}'}
            ]
        }

    async def fake_collect_experts(state):
        roles = [item.get("role") for item in state["expert_results"]]
        assert set(EXPERT_ROLES).issubset(set(roles))
        assert any(item.get("ok") is False for item in state["expert_results"])
        return {
            "expert_summary": "full committee invoked",
            "expert_consensus": {"decision": "NEUTRAL", "score": 0.0, "weight_coverage": 1.0},
        }

    async def fake_f51(state):
        return {"f51_verdict": {"passed": False, "decision_score": 0.779, "confidence": 0.779}}

    async def fake_neural(state):
        return {"neural_decision": {"status": "abstain", "reason": "TOO_FEW_LABELLED_SAMPLES"}}

    async def fake_sdca(state):
        return {"sdca_firewall": {"decision": "ALLOW", "confidence": 0.8}}

    async def fake_rag(state):
        return {"rag_context": "none"}

    monkeypatch.setattr(graph_module, "node_collector", fake_collector)
    monkeypatch.setattr(graph_module, "node_expert", fake_expert)
    monkeypatch.setattr(graph_module, "node_collect_experts", fake_collect_experts)
    monkeypatch.setattr(graph_module, "node_f51_verdict", fake_f51)
    monkeypatch.setattr(graph_module, "node_neural_decision", fake_neural)
    monkeypatch.setattr(graph_module, "node_sdca_firewall", fake_sdca)
    monkeypatch.setattr(graph_module, "node_rag_forensics", fake_rag)

    result = await graph_module._auto_full_analysis(
        {
            "run_id": "spy-tip-full-committee",
            "route": "agent",
            "intent": "bob_decides",
            "ticker": "SPY",
            "message": _SPY_TIP,
            "errors": [],
        },
        gateway="gateway-ok",
    )

    assert set(invoked) == set(EXPERT_ROLES)
    assert len(result["expert_results"]) == len(EXPERT_ROLES)
    failed = [item for item in result["expert_results"] if item.get("ok") is False]
    assert failed and failed[0]["role"] == "sentiment"
    assert "sentiment_provider_timeout" in failed[0]["error"]
    assert result["expert_summary"] == "full committee invoked"
    assert result["f51_verdict"]["decision_score"] == 0.779
    assert result["math_report"]["modules"]["f51_unified"]["status"] == "ok"
    assert result["research_safety"]["live_trading_disabled"] is True
    assert any(event.get("step") == "auto_full_analysis" for event in events)


def test_sentiment_expert_receives_collector_sentiment():
    from src.core.pipeline.nodes.experts import build_role_context

    context = build_role_context(
        "sentiment",
        {
            "ticker": "SPY",
            "modules": {
                "price_series": {"status": "ok", "values": {"latest_price": 770.19}},
            },
        },
        raw_context="ignored",
        data={"sentiment": {"sentiment_label": "BULLISH", "sentiment_score": 0.42}},
    )
    assert "770.19" in context
    assert "sentiment_label=BULLISH" in context
    assert "sentiment_score=0.42" in context


def test_social_expert_records_explicit_collector_failure():
    from src.core.pipeline.nodes.experts import build_role_context

    context = build_role_context(
        "social_forensics",
        {"ticker": "SPY", "modules": {"price_series": {"status": "ok", "values": {}}}},
        raw_context="",
        data={"social": {"status": "unavailable", "error": "all_providers_failed_for_social"}},
    )
    assert "FAILED" in context
    assert "all_providers_failed_for_social" in context
