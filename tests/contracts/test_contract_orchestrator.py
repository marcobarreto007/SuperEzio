"""Contract tests for orchestrator node — intent classification and routing."""

import os

import src.core.pipeline.nodes.orchestrator as orchestrator_node
from src.core.pipeline.nodes.orchestrator import (
    ALLOWED_INTENTS,
    ALLOWED_ROUTES,
    _extract_time_horizon,
    _render_plan,
    node_orchestrator,
    route_after_orchestrator,
)


def _noop_writer(_event: dict) -> None:
    return None


# ---------------------------------------------------------------------------
# Route constants
# ---------------------------------------------------------------------------


def test_allowed_routes_are_non_empty():
    assert len(ALLOWED_ROUTES) >= 3
    assert "general" in ALLOWED_ROUTES
    assert "ticker_analysis" in ALLOWED_ROUTES
    assert "market_scan" in ALLOWED_ROUTES


def test_allowed_intents_cover_all_routes():
    assert len(ALLOWED_INTENTS) >= 5
    assert "general_question" in ALLOWED_INTENTS
    assert "market_scan" in ALLOWED_INTENTS


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


def test_route_after_orchestrator_always_returns_data():
    assert route_after_orchestrator({}) == "data"
    assert route_after_orchestrator({"route": "ticker_analysis"}) == "data"
    assert route_after_orchestrator({"route": "market_scan"}) == "data"
    assert route_after_orchestrator({"route": "general"}) == "data"


# ---------------------------------------------------------------------------
# Time horizon extraction
# ---------------------------------------------------------------------------


def test_extract_time_horizon_english_days():
    assert _extract_time_horizon("AAPL 14 days") == "14 days"
    assert _extract_time_horizon("analyze 3 day forecast") == "3 days"


def test_extract_time_horizon_english_weeks():
    assert _extract_time_horizon("2 weeks outlook") == "2 weeks"


def test_extract_time_horizon_english_months():
    assert _extract_time_horizon("1 month forecast") == "1 months"


def test_extract_time_horizon_portuguese():
    assert _extract_time_horizon("14 dias") == "14 days"
    assert _extract_time_horizon("2 semanas") == "2 weeks"
    assert _extract_time_horizon("3 meses") == "3 months"
    assert _extract_time_horizon("1 ano") == "12 months"


def test_extract_time_horizon_empty():
    assert _extract_time_horizon("") == ""
    assert _extract_time_horizon("no time mentioned here") == ""


# ---------------------------------------------------------------------------
# Plan rendering
# ---------------------------------------------------------------------------


def test_render_plan_minimal():
    result = _render_plan({"route": "general", "intent": "general_question"})
    assert "general" in result
    assert "general_question" in result


def test_render_plan_with_ticker():
    result = _render_plan(
        {
            "route": "ticker_analysis",
            "intent": "ticker_analysis",
            "ticker": "AAPL",
            "intent_confidence": 0.95,
        }
    )
    assert "AAPL" in result
    assert "ticker_analysis" in result


# ---------------------------------------------------------------------------
# Node: empty state (deterministic path)
# ---------------------------------------------------------------------------


def test_node_orchestrator_empty_state():
    """Orchestrator must produce a valid plan even with empty state."""
    os.environ["UNIVERSAL_SKIP_GATEWAY"] = "1"
    import asyncio

    orchestrator_node.get_stream_writer = lambda: _noop_writer

    async def _run():
        return await node_orchestrator(
            {"message": "Hello", "rigor": "strict", "run_id": "test-orch-1"}
        )

    result = asyncio.run(_run())
    assert isinstance(result, dict)
    assert "route" in result
    assert result["route"] in ALLOWED_ROUTES
    assert "intent" in result
    assert result["intent"] in ALLOWED_INTENTS


def test_node_orchestrator_portuguese_prompt():
    """Portuguese financial prompts must not be blocked."""
    os.environ["UNIVERSAL_SKIP_GATEWAY"] = "1"
    import asyncio

    orchestrator_node.get_stream_writer = lambda: _noop_writer

    async def _run():
        return await node_orchestrator(
            {
                "message": "quero uma dica de investimento",
                "rigor": "strict",
                "run_id": "test-orch-pt",
            }
        )

    result = asyncio.run(_run())
    assert isinstance(result, dict)
    # Must not route to needs_scope for Portuguese financial prompts
    assert result.get("route") != "needs_scope"


def test_node_orchestrator_extracts_time_horizon():
    """Time horizon from user message must be extracted into plan."""
    os.environ["UNIVERSAL_SKIP_GATEWAY"] = "1"
    import asyncio

    orchestrator_node.get_stream_writer = lambda: _noop_writer

    async def _run():
        return await node_orchestrator(
            {
                "message": "AAPL 14 days analysis",
                "rigor": "strict",
                "run_id": "test-orch-horizon",
            }
        )

    result = asyncio.run(_run())
    assert "time_horizon" in result
    assert "14 days" in result.get("time_horizon", "")
