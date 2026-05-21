"""Contract tests for guardrails — blocked response node and security sanitizers."""

import src.core.pipeline.nodes.guardrails as guard_node
from src.core.pipeline.nodes.guardrails import (
    VAGUE_FINANCIAL_RESPONSE,
    _sdca_blocked_response,
    node_blocked,
)
from src.core.pipeline.security import sanitize_output, validate_input


def _noop_writer(_event: dict) -> None:
    return None


# ---------------------------------------------------------------------------
# Vague financial response
# ---------------------------------------------------------------------------


def test_vague_financial_response_contains_required_parts():
    assert "ticker" in VAGUE_FINANCIAL_RESPONSE.lower()
    assert "research" in VAGUE_FINANCIAL_RESPONSE.lower()
    assert len(VAGUE_FINANCIAL_RESPONSE) > 100


# ---------------------------------------------------------------------------
# SDCA blocked response
# ---------------------------------------------------------------------------


def test_sdca_blocked_response_with_tokens():
    state = {
        "sdca_firewall": {
            "human_summary": "High risk detected.",
            "ghost_tokens": ["flow_toxicity_high", "macro_uncertainty_high"],
        }
    }
    result = _sdca_blocked_response(state)
    assert "BLOCKED" in result
    assert "High risk detected" in result
    assert "flow_toxicity_high" in result


def test_sdca_blocked_response_empty():
    """Empty state must produce a safe fallback message."""
    result = _sdca_blocked_response({})
    assert "BLOCKED" in result
    assert len(result) > 50


# ---------------------------------------------------------------------------
# node_blocked
# ---------------------------------------------------------------------------


def test_node_blocked_vague():
    """node_blocked without SDCA blocked flag returns vague response."""
    import asyncio

    guard_node.get_stream_writer = lambda: _noop_writer

    async def _run():
        return await node_blocked({"sdca_blocked": False, "run_id": "test-blocked-1"})

    result = asyncio.run(_run())
    assert "final" in result
    assert "ticker" in result["final"].lower()


def test_node_blocked_sdca():
    """node_blocked with SDCA blocked flag returns firewall response."""
    import asyncio

    guard_node.get_stream_writer = lambda: _noop_writer

    async def _run():
        return await node_blocked(
            {
                "sdca_blocked": True,
                "sdca_firewall": {
                    "human_summary": "Pattern matches pump and dump.",
                    "ghost_tokens": ["fraud_signal"],
                },
                "run_id": "test-blocked-2",
            }
        )

    result = asyncio.run(_run())
    assert "final" in result
    assert "BLOCKED" in result["final"]


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


def test_validate_input_empty_message():
    result = validate_input("")
    assert result is not None
    assert result is not None  # Must reject empty input


def test_validate_input_valid():
    result = validate_input("What is AAPL's risk profile?")
    assert result is None  # None means valid


def test_validate_input_too_long():
    result = validate_input("X" * 10001)
    assert result is not None


# ---------------------------------------------------------------------------
# Output sanitization
# ---------------------------------------------------------------------------


def test_sanitize_output_passthrough():
    assert sanitize_output("Hello world") == "Hello world"


def test_sanitize_output_trims():
    assert sanitize_output("  text  ") == "text"


def test_sanitize_output_empty():
    assert sanitize_output("") == ""


def test_sanitize_output_none():
    # sanitize_output returns the input unchanged when falsy (early return)
    result = sanitize_output(None)  # type: ignore[arg-type]
    assert result is None or result == ""
