import pytest


@pytest.mark.asyncio
async def test_market_scan_result_finalizes_without_reentering_tool_loop(monkeypatch):
    from src.core.pipeline.nodes import agent as agent_module

    events = []
    monkeypatch.setattr(agent_module, "get_stream_writer", lambda: events.append)

    class GatewayMustNotRun:
        async def chat_completion(self, **kwargs):
            raise AssertionError("market_scan with scan results should finalize deterministically")

    result = await agent_module.node_agent(
        {
            "run_id": "scan-loop-test",
            "route": "market_scan",
            "message": "Bob, eu tenho 100 cada para investir com risco alto, pesquisa mercado pequeno",
            "scan": {
                "data_quality": "provider_or_computed",
                "source_errors": [],
                "candidates": [
                    {"ticker": "ABCD", "price": 0.42, "provider": "fake-provider"},
                    {"ticker": "WXYZ", "source": "financedatabase"},
                ],
            },
        },
        gateway=GatewayMustNotRun(),
    )

    assert result["agent_tool_call"]["tool"] == "final_answer"
    assert "ABCD" in result["final"]
    assert "[SYSTEM]" not in result["final"]
    assert "Too many tool calls" not in result["final"]
    assert any(
        event.get("type") == "CHUNK" and "watchlist" in event.get("content", "")
        for event in events
    )


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
