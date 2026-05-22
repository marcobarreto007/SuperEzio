"""Regression tests for the market_scan candidate data-quality gate.

Five scenarios from the P0 spec:
    1. No unavailable-price candidate may reach the user.
    2. Generic English short-term prompts default to US+Canada liquid universe.
    3. The no-candidate state must remain useful and structured.
    4. Explicit China A-share scans are still allowed.
    5. Only candidates with full data appear in the candidates list.
"""

from __future__ import annotations

import sys
import types

import pytest


# ---------------------------------------------------------------------------
# Test 1 — unavailable price candidates are rejected, never shown
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unavailable_price_candidates_are_rejected(monkeypatch):
    """If providers can't price tickers, they must not surface as candidates."""
    from src.core import scanner as scanner_module
    from src.core.pipeline.nodes.collector import _run_scan

    class StubScanner:
        def scan_equities(self, country=None, sector=None, industry=None, limit=10):
            return ["AAPL", "MSFT", "TSLA"]

    class StubHub:
        def get_price(self, ticker):
            return {"error": "no quote"}
        def list_routes(self, capability=None):
            return []

    monkeypatch.setattr(scanner_module, "MarketScanner", StubScanner)
    monkeypatch.setitem(
        sys.modules, "data.data_hub", types.SimpleNamespace(hub=StubHub())
    )

    result = await _run_scan(
        "What stock would you recommend if I want to profit within the next 2 weeks?",
        {"country": "United States"},
    )

    assert result["candidates"] == []
    assert result["rejected_count"] >= 3
    assert "missing_price" in result["rejection_summary"]
    rejected_tickers = [r.get("ticker") for r in result["rejected"]]
    assert "AAPL" in rejected_tickers
    assert all(r.get("rejected_reason") for r in result["rejected"])


# ---------------------------------------------------------------------------
# Test 2 — generic English profit prompts default to US/Canada liquid universe
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generic_two_week_profit_prompt_defaults_to_us_canada(monkeypatch):
    """Generic English short-term prompts must never pick China by default."""
    from src.core import scanner as scanner_module
    from src.core.pipeline.nodes.collector import _run_scan

    seen_countries: list[str | None] = []

    class StubScanner:
        def scan_equities(self, country=None, sector=None, industry=None, limit=10):
            seen_countries.append(country)
            if country == "United States":
                return ["AAPL"]
            if country == "Canada":
                return ["RY.TO"]
            return ["000002.SZ"]  # must never be requested

    class StubHub:
        def get_price(self, ticker):
            return {"error": "no quote"}
        def list_routes(self, capability=None):
            return []

    monkeypatch.setattr(scanner_module, "MarketScanner", StubScanner)
    monkeypatch.setitem(
        sys.modules, "data.data_hub", types.SimpleNamespace(hub=StubHub())
    )

    result = await _run_scan(
        "What stock would you recommend if I want to profit within the next 2 weeks?",
        {},
    )

    assert result["universe"] == "US_CANADA_LIQUID"
    assert result["filters"]["resolved_countries"] == ["United States", "Canada"]
    assert "United States" in seen_countries
    assert "Canada" in seen_countries
    assert "China" not in seen_countries
    # Even if the scanner had returned junk, no Chinese ticker may reach output.
    all_tickers = [c.get("ticker") for c in result["candidates"]]
    all_tickers += [r.get("ticker") for r in result["rejected"]]
    assert not any(
        isinstance(t, str) and (t.endswith(".SZ") or t.endswith(".SS"))
        for t in all_tickers
    )


# ---------------------------------------------------------------------------
# Test 3 — the no-candidate state must be useful and structured
# ---------------------------------------------------------------------------


def test_no_candidate_answer_is_useful():
    """When zero candidates pass, the answer must still teach the user."""
    from src.core.pipeline.nodes.agent import _market_scan_answer

    state = {
        "message": "What stock would you recommend if I want to profit within the next 2 weeks?",
        "scan": {
            "candidates": [],
            "rejected": [
                {"ticker": "AAA", "rejected_reason": "missing_price"},
                {"ticker": "BBB", "rejected_reason": "missing_liquidity"},
                {"ticker": "CCC", "rejected_reason": "missing_short_term_thesis"},
            ],
            "rejected_count": 3,
            "rejection_summary": {
                "missing_price": 1,
                "missing_liquidity": 1,
                "missing_short_term_thesis": 1,
            },
            "universe": "US_CANADA_LIQUID",
            "filters": {
                "country": None,
                "sector": None,
                "resolved_countries": ["United States", "Canada"],
                "allow_penny_otc": False,
                "allow_microcap": False,
            },
            "source_errors": [],
        },
    }

    answer = _market_scan_answer(state)

    assert isinstance(answer, str)
    assert len(answer) > 300
    assert "No candidate passed" in answer
    assert "Filters used" in answer
    assert "Suggested next prompt" in answer
    assert "guaranteed profit" not in answer.lower() or "no guaranteed profit" in answer.lower()
    # No junk ticker should leak as a candidate
    assert "Scanner candidates:" not in answer
    assert "preco indisponivel no scan" not in answer
    assert "pick 3 tickers from the list" not in answer


# ---------------------------------------------------------------------------
# Test 4 — explicit China scans are still permitted
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_explicit_china_scan_is_allowed(monkeypatch):
    """Explicit Chinese A-share requests must enter the universe."""
    from src.core import scanner as scanner_module
    from src.core.pipeline.nodes.collector import _run_scan

    seen_countries: list[str | None] = []

    class StubScanner:
        def scan_equities(self, country=None, sector=None, industry=None, limit=10):
            seen_countries.append(country)
            return ["000002.SZ", "000004.SZ"]

    class StubHub:
        def get_price(self, ticker):
            # No price → still must be gated even when China is allowed.
            return {"error": "no quote"}
        def list_routes(self, capability=None):
            return []

    monkeypatch.setattr(scanner_module, "MarketScanner", StubScanner)
    monkeypatch.setitem(
        sys.modules, "data.data_hub", types.SimpleNamespace(hub=StubHub())
    )

    result = await _run_scan(
        "Scan Chinese A-shares for high-risk 2-week opportunities.",
        {},
    )

    assert result["universe"] == "CHINA_A_SHARES"
    assert "China" in seen_countries
    rejected_tickers = [r.get("ticker") for r in result["rejected"]]
    assert "000002.SZ" in rejected_tickers
    # Gate still applies — missing price keeps them out of candidates.
    assert result["candidates"] == []
    assert "missing_price" in result["rejection_summary"]


# ---------------------------------------------------------------------------
# Test 5 — a valid candidate appears only with full data
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_valid_candidate_requires_full_data(monkeypatch):
    """Only fully-enriched candidates with all required fields may pass."""
    from src.core import scanner as scanner_module
    from src.core.pipeline.nodes.collector import _run_scan

    class StubScanner:
        def scan_equities(self, country=None, sector=None, industry=None, limit=10):
            return ["AAPL", "INCOMPLETE"]

    class StubHub:
        def get_price(self, ticker):
            if ticker == "AAPL":
                return {
                    "price": 180.0,
                    "volume": 50_000_000,
                    "currency": "USD",
                    "provider": "stub-quote",
                    "catalyst": "Q1 earnings next week with guided revenue beat.",
                    "risk": "Macro tape risk and sector rotation pressure.",
                    "invalidation": "Close below 20-day moving average.",
                    "name": "Apple Inc.",
                    "confidence": "medium",
                }
            return {
                "price": 50.0,
                "volume": 100_000,
                "currency": "USD",
                "provider": "stub-quote",
            }

    monkeypatch.setattr(scanner_module, "MarketScanner", StubScanner)
    monkeypatch.setitem(
        sys.modules, "data.data_hub", types.SimpleNamespace(hub=StubHub())
    )

    result = await _run_scan(
        "Scan US technology equities for 2-week opportunities.",
        {"country": "United States"},
    )

    candidate_tickers = [c["ticker"] for c in result["candidates"]]
    assert "AAPL" in candidate_tickers
    assert "INCOMPLETE" not in candidate_tickers

    aapl = next(c for c in result["candidates"] if c["ticker"] == "AAPL")
    for required in ("ticker", "price", "volume", "catalyst", "risk", "invalidation"):
        assert aapl.get(required), f"valid candidate missing required field {required}"

    # The rejected entry must explain *why* it was filtered.
    incomplete = next(
        (r for r in result["rejected"] if r.get("ticker") == "INCOMPLETE"), None
    )
    assert incomplete is not None
    assert incomplete.get("rejected_reason") == "missing_short_term_thesis"


@pytest.mark.asyncio
async def test_priced_candidates_fail_on_thesis_not_price(monkeypatch):
    """When prices resolve, rejections should mix thesis/liquidity — not all missing_price."""
    from src.core import scanner as scanner_module
    from src.core.pipeline.nodes.collector import _run_scan

    class StubScanner:
        def scan_equities(self, country=None, sector=None, industry=None, limit=10):
            if country == "United States":
                return ["AAPL", "MSFT"]
            return []

    class StubHub:
        def get_price(self, ticker, **kwargs):
            return {
                "price": 150.0,
                "volume": 25_000_000,
                "source": "finnhub",
            }

        def get_profile(self, ticker):
            return {"name": ticker, "exchange": "NASDAQ", "source": "finnhub"}

        def route(self, capability, ticker):
            return {"error": "no_catalyst_in_window"}

    monkeypatch.setattr(scanner_module, "MarketScanner", StubScanner)
    monkeypatch.setitem(
        sys.modules, "data.data_hub", types.SimpleNamespace(hub=StubHub())
    )

    result = await _run_scan(
        "What stock would you recommend if I want to profit within the next 2 weeks?",
        {},
    )

    assert result["candidates"] == []
    summary = result["rejection_summary"]
    assert summary.get("missing_price", 0) == 0
    assert summary.get("missing_short_term_thesis", 0) >= 1
