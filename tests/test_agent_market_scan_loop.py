import pytest


@pytest.mark.asyncio
async def test_market_scan_run_experts_does_not_raise_collect_experts_import_error(monkeypatch):
    """Regression: run_experts must not import missing collect_experts module."""
    from src.core.pipeline.nodes import experts as experts_module
    from src.core.pipeline.nodes import tool_executor as tool_executor_module

    monkeypatch.setattr(experts_module, "get_stream_writer", lambda: (lambda _event: None))

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
async def test_collect_experts_compat_shim_imports():
    from src.core.pipeline.nodes.collect_experts import node_collect_experts as shim_collect
    from src.core.pipeline.nodes.experts import node_collect_experts as experts_collect

    assert shim_collect is experts_collect


@pytest.mark.asyncio
async def test_market_scan_result_finalizes_without_reentering_tool_loop(monkeypatch):
    """Scan results must finalize deterministically and respect the gate."""
    from src.core.pipeline.nodes import agent as agent_module

    events = []
    monkeypatch.setattr(agent_module, "get_stream_writer", lambda: events.append)

    class GatewayMustNotRun:
        async def chat_completion(self, **kwargs):
            raise AssertionError(
                "market_scan with scan results should finalize deterministically"
            )

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
        gateway=GatewayMustNotRun(),
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
