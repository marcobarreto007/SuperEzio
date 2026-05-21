"""Contract tests for expert nodes: fan-out execution and result collection."""

import src.core.pipeline.nodes.experts as experts_node
from src.core.pipeline.nodes.experts import (
    EXPERT_PROVIDERS,
    node_collect_experts,
    node_expert,
)


def _noop_writer(_event: dict) -> None:
    return None


def test_expert_providers_has_required_roles():
    required = {"fundamental", "technical", "risk", "macro", "quant", "sentiment"}
    assert required.issubset(set(EXPERT_PROVIDERS))
    for role in required:
        assert EXPERT_PROVIDERS[role] == "deepseek"


def test_node_expert_skips_when_gateway_none():
    """Expert must skip gracefully when gateway is None."""
    import asyncio

    experts_node.get_stream_writer = lambda: _noop_writer

    async def _run():
        return await node_expert(
            {
                "role": "fundamental",
                "ticker": "AAPL",
                "data_context": "price=150",
                "run_id": "test-exp-1",
            },
            gateway=None,
        )

    result = asyncio.run(_run())
    assert "expert_results" in result
    assert isinstance(result["expert_results"], list)
    assert len(result["expert_results"]) == 1
    assert result["expert_results"][0]["ok"] is False
    assert result["expert_results"][0]["role"] == "fundamental"
    assert "gateway_unavailable" in result["expert_results"][0]["error"]


def test_expert_call_model():
    from src.core.pipeline.contracts import ExpertCall

    call = ExpertCall(role="technical", ticker="MSFT")
    assert call.role == "technical"
    assert call.ticker == "MSFT"
    assert call.context == ""
    assert call.provider_name == ""
    assert call.timeout == 60.0


def test_node_collect_experts_empty_results():
    """Collect with no expert results returns skip summary."""
    import asyncio

    experts_node.get_stream_writer = lambda: _noop_writer

    async def _run():
        return await node_collect_experts(
            {
                "run_id": "test-collect-empty",
                "route": "general",
            }
        )

    result = asyncio.run(_run())
    assert "expert_summary" in result
    assert "not triggered" in result["expert_summary"]


def test_node_collect_experts_with_results():
    """Collect with expert results produces summary."""
    import asyncio

    experts_node.get_stream_writer = lambda: _noop_writer

    async def _run():
        return await node_collect_experts(
            {
                "run_id": "test-collect-results",
                "route": "ticker_analysis",
                "expert_results": [
                    {"role": "fundamental", "ok": True, "response": "Strong buy, PE=15"},
                    {"role": "technical", "ok": True, "response": "RSI=45, neutral"},
                    {"role": "risk", "ok": False, "error": "timeout"},
                ],
            }
        )

    result = asyncio.run(_run())
    assert "expert_summary" in result
    summary = result["expert_summary"]
    assert "EXPERTS" in summary
    assert "fundamental" in summary
    assert "technical" in summary
    assert "risk" in summary
    assert "FAILED" in summary
    assert "timeout" in summary


def test_node_collect_experts_partial_data_without_results():
    """Partial data quality with no expert results flags error."""
    import asyncio

    experts_node.get_stream_writer = lambda: _noop_writer

    async def _run():
        return await node_collect_experts(
            {
                "run_id": "test-collect-partial",
                "route": "ticker_analysis",
                "data": {"data_quality": "partial"},
            }
        )

    result = asyncio.run(_run())
    assert "expert_summary" in result
    assert "errors" in result
    assert "partial_data_without_expert_results" in result["errors"]
