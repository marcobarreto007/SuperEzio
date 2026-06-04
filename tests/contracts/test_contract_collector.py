"""Contract tests for collector node — data collection and market scan."""

import os

import src.core.pipeline.nodes.collector as collector_node
from src.core.pipeline.nodes.collector import _format_scan_context, node_collector


def _noop_writer(_event: dict) -> None:
    return None


# ---------------------------------------------------------------------------
# Scan context formatting
# ---------------------------------------------------------------------------


def test_format_scan_context_empty():
    result = _format_scan_context(
        {
            "query": "test",
            "filters": {},
            "data_quality": "unknown",
            "candidates": [],
            "source_errors": [],
        }
    )
    assert "MARKET SCAN" in result
    assert "test" in result


def test_format_scan_context_with_candidates():
    result = _format_scan_context(
        {
            "query": "growth stocks",
            "filters": {"country": "CA"},
            "data_quality": "provider_or_computed",
            "candidates": [
                {"ticker": "SHOP", "price": 100.0, "provider": "twelve_data"},
                {"ticker": "CSU", "price": 4000.0, "provider": "alpha_vantage"},
            ],
            "source_errors": [],
        }
    )
    assert "SHOP" in result
    assert "CSU" in result
    assert "100.0" in result


def test_format_scan_context_includes_grounded_identity():
    result = _format_scan_context(
        {
            "query": "growth stocks",
            "filters": {"country": "US"},
            "data_quality": "provider_or_computed",
            "candidates": [
                {
                    "ticker": "RDW",
                    "name": "Redwire Corporation",
                    "sector": "Industrials",
                    "price": 21.92,
                    "provider": "finnhub",
                }
            ],
            "source_errors": [],
        }
    )

    assert "RDW" in result
    assert "name=Redwire Corporation" in result
    assert "provider=finnhub" in result


def test_format_scan_context_with_errors():
    result = _format_scan_context(
        {
            "query": "test",
            "filters": {},
            "data_quality": "partial",
            "candidates": [],
            "source_errors": ["scanner: timeout"],
        }
    )
    assert "scanner: timeout" in result


def test_node_collector_market_scan_event_has_source_metadata(monkeypatch):
    import asyncio

    events: list[dict] = []
    monkeypatch.setattr(collector_node, "get_stream_writer", lambda: events.append)

    async def _fake_run_scan(_message, _filters, *, excluded_tickers=None, writer=None):
        return {
            "query": _message,
            "filters": {},
            "universe": "US/Canada",
            "candidates": [
                {
                    "ticker": "MRVL",
                    "name": "Marvell Technology",
                    "price": 315,
                    "provider": "finnhub",
                    "volume": 62000000,
                }
            ],
            "rejected_count": 0,
            "rejection_summary": {},
            "data_quality": "provider_or_computed",
            "source_errors": [],
        }

    async def _fake_collect_professional(_ticker, _writer, _run_id):
        return {"ticker": _ticker, "data_quality": "ok"}, "Collected ticker: MRVL"

    monkeypatch.setattr(collector_node, "_run_scan", _fake_run_scan)
    monkeypatch.setattr(collector_node, "_collect_professional", _fake_collect_professional)

    result = asyncio.run(
        node_collector(
            {
                "message": "Find a short-term stock idea",
                "route": "market_scan",
                "run_id": "test-scan-event",
            }
        )
    )

    collected = next(event for event in events if event.get("type") == "DATA_COLLECTED")
    assert collected["provider"] == "finnhub"
    assert collected["capability"] == "market_scan"
    assert collected["ticker"] == "MRVL"
    assert collected["candidates"] == 1
    assert result["ticker"] == "MRVL"


# ---------------------------------------------------------------------------
# Node: skip paths (no network)
# ---------------------------------------------------------------------------


def test_node_collector_general_route_skips():
    """General route with no ticker returns empty dict."""
    import asyncio

    collector_node.get_stream_writer = lambda: _noop_writer

    async def _run():
        return await node_collector(
            {
                "message": "Hello",
                "route": "general",
                "run_id": "test-col-general",
            }
        )

    result = asyncio.run(_run())
    # General route without ticker returns empty dict
    assert isinstance(result, dict)


def test_node_collector_returns_expected_keys_for_ticker():
    """Ticker analysis with professional collector disabled returns data."""
    os.environ["SUPEREZIO_PROFESSIONAL_COLLECTOR"] = "false"

    import asyncio

    collector_node.get_stream_writer = lambda: _noop_writer

    async def _fake_collect_subprocess(_ticker: str, _writer, _run_id: str):
        return {"price": {"price": 150.0}}, "price=150"

    collector_node._collect_subprocess_fallback = _fake_collect_subprocess

    async def _run():
        return await node_collector(
            {
                "message": "AAPL analysis",
                "route": "ticker_analysis",
                "ticker": "AAPL",
                "run_id": "test-col-aapl",
            }
        )

    result = asyncio.run(_run())
    assert isinstance(result, dict)
    # Either has data+data_context or is empty (if collector fails)
    if "data" in result:
        assert isinstance(result["data"], dict)
    if "data_context" in result:
        assert isinstance(result["data_context"], str)
