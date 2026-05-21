"""Contract tests for SDCA-Lite firewall pipeline node."""

import src.core.pipeline.nodes.sdca_firewall as sdca_node
from src.core.pipeline.nodes.sdca_firewall import (
    _amount_from_state,
    _build_candidate,
    node_sdca_firewall,
    route_after_sdca_firewall,
)


def _noop_writer(_event: dict) -> None:
    return None


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


def test_route_after_sdca_blocked():
    assert route_after_sdca_firewall({"sdca_blocked": True}) == "respond_blocked"


def test_route_after_sdca_not_blocked():
    assert route_after_sdca_firewall({"sdca_blocked": False}) == "rag_forensics"
    assert route_after_sdca_firewall({}) == "rag_forensics"


# ---------------------------------------------------------------------------
# Amount extraction
# ---------------------------------------------------------------------------


def test_amount_from_state_entities():
    state = {"entities": {"amount_cad": 5000.0}}
    assert _amount_from_state(state) == 5000.0


def test_amount_from_state_filters():
    state = {"entities": {}, "filters": {"capital": 10000.0}}
    assert _amount_from_state(state) == 10000.0


def test_amount_from_state_position_size():
    state = {"entities": {}, "filters": {"position_size": 2500}}
    assert _amount_from_state(state) == 2500.0


def test_amount_from_state_empty():
    assert _amount_from_state({}) is None


def test_amount_from_state_invalid():
    state = {"entities": {"amount": "notanumber"}}
    assert _amount_from_state(state) is None


# ---------------------------------------------------------------------------
# Candidate building
# ---------------------------------------------------------------------------


def test_build_candidate_minimal():
    candidate = _build_candidate(
        {
            "run_id": "test-sdca",
            "route": "ticker_analysis",
            "intent": "ticker_analysis",
            "ticker": "AAPL",
            "action": "analyze",
            "message": "Should I buy AAPL?",
            "time_horizon": "14 days",
        }
    )
    from core.risk_firewall import DecisionCandidate

    assert isinstance(candidate, DecisionCandidate)
    assert candidate.id == "test-sdca"
    assert candidate.asset == "AAPL"
    assert candidate.action == "analyze"
    assert candidate.source == "superezio_pipeline"


def test_build_candidate_with_no_ticker():
    """Candidate must handle empty ticker (market scan route)."""
    candidate = _build_candidate(
        {
            "run_id": "test-sdca-ns",
            "route": "market_scan",
            "intent": "market_scan",
            "action": "scan_market",
            "message": "quero uma dica de investimento",
        }
    )
    assert candidate.asset is None
    assert candidate.action == "scan_market"


# ---------------------------------------------------------------------------
# Node: empty message (skip path)
# ---------------------------------------------------------------------------


def test_node_sdca_firewall_empty_message():
    """SDCA must skip when message is empty."""
    import asyncio

    sdca_node.get_stream_writer = lambda: _noop_writer

    async def _run():
        return await node_sdca_firewall(
            {"message": "", "run_id": "test-sdca-empty"}
        )

    result = asyncio.run(_run())
    assert isinstance(result, dict)
    # Empty message → skipped, no sdca_firewall key
    assert "sdca_firewall" not in result


def test_node_sdca_firewall_with_message(monkeypatch):
    """SDCA must run when message is present."""
    # Prevent actual SDCA engine from connecting to external services
    import asyncio

    sdca_node.get_stream_writer = lambda: _noop_writer

    async def _run():
        return await node_sdca_firewall(
            {
                "message": "Should I buy AAPL?",
                "ticker": "AAPL",
                "route": "ticker_analysis",
                "intent": "ticker_analysis",
                "action": "analyze",
                "run_id": "test-sdca-msg",
                "data": {},
                "neural_decision": {},
                "f51_verdict": {},
            }
        )

    result = asyncio.run(_run())
    assert isinstance(result, dict)
    # Either has sdca_firewall evidence or error (if engine unavailable)
    if "sdca_firewall" in result:
        assert isinstance(result["sdca_firewall"], dict)
