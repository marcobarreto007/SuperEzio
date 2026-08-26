import pytest


@pytest.mark.asyncio
async def test_market_scan_run_experts_does_not_raise_collect_experts_import_error(monkeypatch):
    """Regression: run_experts must not import missing collect_experts module."""
    from src.core.pipeline.nodes import experts as experts_module
    from src.core.pipeline.nodes import tool_executor as tool_executor_module

    monkeypatch.setattr(experts_module, "get_stream_writer", lambda: lambda _event: None)

    async def fake_node_expert(state, *, gateway=None):
        role = state.get("role", "fundamental")
        return {
            "expert_results": [
                {
                    "role": role,
                    "ok": True,
                    "response": f"{role} summary",
                    "provider": "test",
                }
            ]
        }

    monkeypatch.setattr(tool_executor_module, "node_expert", fake_node_expert)

    state = {
        "run_id": "collect-experts-import-test",
        "route": "market_scan",
        "message": "What stock would you recommend if I want to profit within the next 2 weeks?",
        "scan": {
            "data_quality": "provider_or_computed",
            "source_errors": [],
            "candidates": [{"ticker": "ABCD", "price": 0.42, "provider": "fake-provider"}],
        },
        "ticker": "ABCD",
        "agent_tool_call": {"tool": "run_experts", "args": {}},
        "errors": [],
    }

    result = await tool_executor_module.node_tool_executor(state, gateway=object())

    assert "expert_summary" in result
    assert "collect_experts" not in " ".join(result.get("errors", []))
    assert all("No module named" not in err for err in result.get("errors", []))


@pytest.mark.asyncio
async def test_market_scan_result_finalizes_without_reentering_tool_loop(monkeypatch):
    """Scan results must finalise through the LLM gateway and respect the output format."""
    from src.core.pipeline.nodes import agent as agent_module

    events = []
    monkeypatch.setattr(agent_module, "get_stream_writer", lambda: events.append)

    class MockGateway:
        async def chat_completion(self, **kwargs):
            return '{"tool": "final_answer", "args": {"content": "Bob: Nenhum candidato passou no scan."}}'

    # ABCD has no price → the new gate rejects it. Under the updated answer
    # contract, the structured no-candidate response must be rendered and
    # the candidate must NOT leak into the final text.
    result = await agent_module.node_agent(
        {
            "run_id": "scan-loop-test",
            "route": "market_scan",
            "message": "Bob, eu tenho 100 cada para investir com risco alto, pesquisa mercado pequeno",
            "scan": {
                "data_quality": "provider_or_computed",
                "source_errors": [],
                "universe": "US_CANADA_LIQUID",
                "filters": {
                    "country": None,
                    "sector": None,
                    "resolved_countries": ["United States", "Canada"],
                    "allow_penny_otc": False,
                    "allow_microcap": False,
                },
                "candidates": [],
                "rejected": [
                    {"ticker": "ABCD", "rejected_reason": "missing_price"},
                    {"ticker": "WXYZ", "rejected_reason": "missing_price"},
                ],
                "rejected_count": 2,
                "rejection_summary": {"missing_price": 2},
            },
        },
        gateway=MockGateway(),
    )

    assert result["agent_tool_call"]["tool"] == "final_answer"
    final = result["final"]
    assert "[SYSTEM]" not in final
    assert "Too many tool calls" not in final
    # The bad legacy output must never appear.
    assert "preco indisponivel no scan" not in final
    assert "ABCD" not in final
    assert "WXYZ" not in final
    # Portuguese no-candidate structure should be visible.
    assert "Nenhum candidato passou" in final
    assert any(event.get("type") == "CHUNK" for event in events)


@pytest.mark.asyncio
async def test_market_scan_final_answer_uses_scan_state_not_model_hallucination(monkeypatch):
    from src.core.pipeline.nodes import agent as agent_module

    events = []
    monkeypatch.setattr(agent_module, "get_stream_writer", lambda: events.append)

    class MockGateway:
        async def chat_completion(self, **kwargs):
            return (
                '{"tool": "final_answer", "args": {"content": '
                '"Actually the scan returned TBR.TO at CAD 4.82 with a spin-off catalyst."}}'
            )

    result = await agent_module.node_agent(
        {
            "run_id": "scan-hallucination-test",
            "route": "market_scan",
            "message": "Find one US or Canadian small-cap stock under CAD 5 with liquidity and a real catalyst.",
            "scan": {
                "data_quality": "provider_or_computed",
                "source_errors": [],
                "universe": "US_CANADA_LIQUID",
                "filters": {
                    "resolved_countries": ["United States", "Canada"],
                    "allow_penny_otc": False,
                    "allow_microcap": False,
                    "max_price": 5.0,
                },
                "candidates": [],
                "rejected": [
                    {"ticker": "EXPENSIVE", "rejected_reason": "price_above_requested_max"}
                ],
                "rejected_count": 1,
                "rejection_summary": {"price_above_requested_max": 1},
            },
        },
        gateway=MockGateway(),
    )

    final = result["final"]
    assert "TBR.TO" not in final
    assert "spin-off catalyst" not in final
    assert "AAPL" not in final
    assert "MSFT" not in final
    assert "SPY" not in final
    assert "No candidate passed" in final
    assert "price above requested maximum" in final
    assert any(event.get("type") == "CHUNK" for event in events)


@pytest.mark.asyncio
async def test_ticker_analysis_forces_collect_data_before_model_final(monkeypatch):
    from src.core.pipeline.nodes import agent as agent_module

    monkeypatch.setattr(agent_module, "get_stream_writer", lambda: lambda _event: None)

    class GatewayMustNotRun:
        async def chat_completion(self, **kwargs):
            raise AssertionError("ticker_analysis must collect data before asking the model")

    result = await agent_module.node_agent(
        {
            "run_id": "ticker-force-collect-test",
            "route": "ticker_analysis",
            "message": "AAPL 14 dias analise",
            "ticker": "AAPL",
            "agent_iterations": 0,
        },
        gateway=GatewayMustNotRun(),
    )

    assert result["agent_tool_call"] == {"tool": "collect_data", "args": {"ticker": "AAPL"}}


@pytest.mark.asyncio
async def test_agent_loop_failsafe_is_user_safe(monkeypatch):
    from src.core.pipeline.nodes import agent as agent_module

    events = []
    monkeypatch.setattr(agent_module, "get_stream_writer", lambda: events.append)

    result = await agent_module.node_agent(
        {
            "run_id": "failsafe-test",
            "route": "market_scan",
            "message": "Bob, pesquisa mercado pequeno com risco alto",
            "agent_iterations": 8,
        },
        gateway=object(),
    )

    assert result["agent_tool_call"]["tool"] == "final_answer"
    assert result["final"]
    assert "[SYSTEM]" not in result["final"]
    assert "Too many tool calls" not in result["final"]
    assert any(event.get("type") == "CHUNK" for event in events)


@pytest.mark.asyncio
async def test_tool_executor_blocks_duplicate_tool_with_feedback(monkeypatch):
    from src.core.pipeline.nodes import tool_executor as tool_executor_module

    events = []
    monkeypatch.setattr(tool_executor_module, "get_stream_writer", lambda: events.append)

    async def neural_must_not_run(state):
        raise AssertionError("duplicate neural_decision must be blocked before execution")

    monkeypatch.setattr(tool_executor_module, "node_neural_decision", neural_must_not_run)

    state = {
        "run_id": "duplicate-tool-test",
        "agent_tool_call": {"tool": "neural_decision", "args": {}},
        "executed_tools": ["collect_data", "run_experts", "neural_decision"],
        "errors": [],
    }

    result = await tool_executor_module.node_tool_executor(state, gateway=object())

    assert result["executed_tools"] == ["collect_data", "run_experts", "neural_decision"]
    assert result["tool_blocked"]["tool"] == "neural_decision"
    assert "already executed" in result["tool_blocked"]["reason"]
    assert result["agent_tool_call"]["tool"] == "final_answer"
    assert any(event.get("status") == "blocked_duplicate" for event in events)


@pytest.mark.asyncio
async def test_agent_finalizes_when_tool_was_blocked(monkeypatch):
    from src.core.pipeline.nodes import agent as agent_module

    events = []
    monkeypatch.setattr(agent_module, "get_stream_writer", lambda: events.append)

    class GatewayMustNotRun:
        async def chat_completion(self, **kwargs):
            raise AssertionError("tool_blocked state must not re-enter CEO tool loop")

    result = await agent_module.node_agent(
        {
            "run_id": "blocked-agent-test",
            "route": "ticker_analysis",
            "message": "analise AAPL",
            "tool_blocked": {
                "tool": "neural_decision",
                "reason": "it already executed in this run",
            },
            "agent_iterations": 3,
        },
        gateway=GatewayMustNotRun(),
    )

    assert result["agent_tool_call"]["tool"] == "final_answer"
    assert result["final"]
    assert "neural_decision" in result["final"]
    assert any(event.get("type") == "CHUNK" for event in events)


@pytest.mark.asyncio
async def test_completed_decisive_scan_finalizes_from_evidence_without_model_or_order(monkeypatch):
    from src.core.pipeline.nodes import agent as agent_module

    events = []
    monkeypatch.setattr(agent_module, "get_stream_writer", lambda: events.append)

    class GatewayMustNotRun:
        def __init__(self):
            self.calls = 0

        async def chat_completion(self, **kwargs):
            self.calls += 1
            raise AssertionError(
                "completed market evidence must finalize without another model call"
            )

    candidate = {
        "ticker": "TEST.V",
        "name": "Test Ventures",
        "market": "Canada",
        "exchange": "TSXV",
        "price": 2.0,
        "currency": "CAD",
        "volume": 6_000_000,
        "market_cap": 120_000_000,
        "catalyst": "TEST.V reports Q2 earnings on 2026-08-24 inside the requested horizon.",
        "risk": "TEST.V Q2 revenue may miss the published CAD 12M consensus estimate.",
        "invalidation": "Invalidate on a close below CAD 1.80 after the Q2 report.",
        "provider": "test-provider",
        "provenance": {
            field: {"source": "test-provider"}
            for field in ("ticker", "price", "volume", "catalyst", "risk", "invalidation")
        },
    }
    gateway = GatewayMustNotRun()
    result = await agent_module.node_agent(
        {
            "run_id": "cad100-mini-cap-complete",
            "route": "market_scan",
            "intent": "market_scan",
            "message": "vamos investir 100 cad segunda , escolhe mini cap",
            "allowed_tools": [
                "market_scan",
                "collect_data",
                "run_experts",
                "f51_firewall",
                "neural_decision",
                "sdca_firewall",
                "submit_paper_order",
                "final_answer",
            ],
            "scanner_allowed": True,
            "ticker_allowed": True,
            "ticket_allowed": True,
            "agent_iterations": 6,
            "executed_tools": [
                "market_scan",
                "collect_data",
                "run_experts",
                "f51_firewall",
                "neural_decision",
                "sdca_firewall",
            ],
            "ticker": "TEST.V",
            "scan": {
                "universe": "CANADA_MICROCAP",
                "filters": {"country": "Canada", "allow_microcap": True},
                "candidates": [candidate],
                "ranked_candidates": [],
                "rejected": [],
                "rejected_count": 0,
                "rejection_summary": {},
                "source_errors": [],
            },
            "data": {
                "ticker": "TEST.V",
                "price": {"price": 2.0, "currency": "CAD"},
                "technicals": {"price": 2.0, "volume": 6_000_000},
            },
            "expert_summary": "Committee reviewed TEST.V; risks and invalidation are explicit.",
            "f51_verdict": {"passed": True, "confidence": 0.91},
            "neural_decision": {"recommendation": "BUY_CANDIDATE", "veto": False},
            "sdca_firewall": {"decision": "ALLOW", "confidence": 0.88},
        },
        gateway=gateway,
    )

    assert gateway.calls == 0
    assert result["agent_tool_call"]["tool"] == "final_answer"
    assert "TEST.V" in result["final"]
    assert "DECISIVE_TRADE_ORDER" in result["final"]
    assert "REJECT_ALL" not in result["final"]
    assert "PAPER_ORDER_SUBMITTED" not in result["final"]
    assert any(event.get("type") == "CHUNK" for event in events)


def test_parse_tool_call_rejects_legacy_unknown_tool():
    from src.core.pipeline.nodes.agent import _parse_tool_call

    assert _parse_tool_call('{"tool": "legacy_magic_tool", "args": {}}') is None


def test_empty_scan_with_price_provider_exceptions_does_not_invent_candidate():
    """Hub exceptions + zero candidates must say the data hub failed — not invent GRTS."""
    from src.core.pipeline.nodes.agent import _market_scan_answer

    state = {
        "message": "Bob, pesquisa mercado pequeno com risco alto",
        "scan": {
            "candidates": [],
            "rejected": [{"ticker": "GRTS", "rejected_reason": "missing_price"}],
            "rejected_count": 20,
            "rejection_summary": {"missing_price": 20},
            "universe": "US_CANADA_LIQUID",
            "filters": {
                "resolved_countries": ["United States", "Canada"],
                "allow_penny_otc": False,
                "allow_microcap": False,
            },
            "source_errors": ["price_provider: exception=20"],
        },
    }

    answer = _market_scan_answer(state)

    assert "Nenhum candidato passou" in answer
    assert "hub" in answer.lower()
    assert "preco falhou" in answer.lower()
    assert "GRTS" not in answer
    assert "ideia de compra" not in answer.lower() or "nao e ideia de compra" in answer.lower()


def test_candidate_without_venue_currency_is_not_formatted_as_buy_idea():
    from src.core.pipeline.nodes.agent import _format_candidate_block_pt

    lines = _format_candidate_block_pt(
        {
            "ticker": "GRTS",
            "price": 9.58,
            "catalyst": "Earnings release on 2026-05-27 after market close.",
        }
    )
    text = "\n".join(lines)
    assert "nao e ideia de compra" in text
    assert "Preco atual:" not in text
