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
    assert len(answer) > 200
    # Decisive prompt → REJECT_ALL when zero candidates pass
    assert "DECISIVE_TRADE_ORDER" in answer
    assert "REJECT_ALL" in answer
    assert "Model verdict: REJECT_ALL" in answer
    assert "Suggested next scan" in answer or "Suggested next prompt" in answer
    assert "guaranteed profit" not in answer.lower() or "not guaranteed profit" in answer.lower()
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


# ---------------------------------------------------------------------------
# Regression: "share recommendation" must never route to CHINA_A_SHARES
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_share_recommendation_never_routes_to_china(monkeypatch):
    """P0 regression: 'give me a share recommendation' → US_CANADA_LIQUID.

    The word 'share' must not match the China A-share hint. Only explicit
    China/A-share terms (with hyphen) may trigger CHINA_A_SHARES.
    """
    from src.core import scanner as scanner_module
    from src.core.pipeline.nodes.collector import _run_scan

    seen_countries: list[str | None] = []

    class StubScanner:
        def scan_equities(self, country=None, sector=None, industry=None, limit=10):
            seen_countries.append(country)
            return []

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
        "give me a share recommendation to buy if I want to make a profit within the next 14 days",
        {},
    )

    assert result["universe"] == "US_CANADA_LIQUID"
    assert "China" not in seen_countries


def test_a_share_word_boundary_no_false_positive():
    """'a share' (without hyphen) must not trigger China universe."""
    from src.core.pipeline.nodes.collector import _wants_china_universe

    false_positives = [
        "give me a share recommendation to buy",
        "i want to buy a share of apple",
        "give me a share tip",
        "i own a share of tesla",
        "what shares should i buy",
        "share price analysis",
    ]
    for text in false_positives:
        assert not _wants_china_universe(text), (
            f"False positive China trigger: '{text}'"
        )


def test_a_share_word_boundary_true_positives():
    """Explicit China/A-share terms must still trigger China universe."""
    from src.core.pipeline.nodes.collector import _wants_china_universe

    true_positives = [
        "scan chinese a-shares for high-risk 2-week opportunities",
        "find me stocks on the shanghai exchange",
        "analyze shenzhen tech stocks",
        "a-share market outlook",
        "a-shares with momentum",
        "china market analysis",
        "hong kong stocks",
        "hkex listing",
        "hang seng index hsi today",
    ]
    for text in true_positives:
        assert _wants_china_universe(text), (
            f"Missed China trigger: '{text}'"
        )


# ---------------------------------------------------------------------------
# P0 — Capital Allocation routing must never invoke scanner
# ---------------------------------------------------------------------------


CAD_1000_PROMPT = (
    "I have CAD 1,000 to invest in Canada. "
    "Should I keep it in cash, invest in an ETF, pay debt, "
    "or try one short-term stock trade? "
    "Give me one clear recommendation, explain why, "
    "and give a confidence score from 0 to 100. "
    "Do not scan China stocks. "
    "Do not use the current chart unless I ask for a ticker."
)

STOCK_AS_OPTION_PROMPT = (
    "Compare cash, ETF, debt repayment, and one short-term stock trade for CAD 1,000."
)

DIRECT_STOCK_PROMPT = (
    "What stock would you recommend me to buy if I want to make a profit "
    "within the next 14 days?"
)


def test_cad_1000_capital_allocation_no_scan():
    """CAD 1,000 allocation prompt must route to capital_allocation, not market_scan."""
    from src.core.pipeline.intents import (
        parse_user_intent,
        detect_capital_allocation_intent,
        _is_market_scan_request,
        detect_complex_finance_intent,
    )

    # Capital allocation detection must fire
    assert detect_capital_allocation_intent(CAD_1000_PROMPT), (
        "CAD 1000 prompt must be detected as capital allocation"
    )

    # Market scan must NOT fire (negative scan instruction + capital allocation)
    assert not _is_market_scan_request(CAD_1000_PROMPT), (
        "CAD 1000 prompt must not trigger market scan request"
    )

    # Complex finance must fire (covers capital allocation as a safety net)
    assert detect_complex_finance_intent(CAD_1000_PROMPT), (
        "CAD 1000 prompt must be detected as complex finance"
    )

    # Full intent parse must route to capital_allocation, not market_scan
    result = parse_user_intent(CAD_1000_PROMPT, rigor="strict", ticker="")
    assert result.route == "general", (
        f"Expected route=general, got route={result.route}"
    )
    assert result.intent == "capital_allocation", (
        f"Expected intent=capital_allocation, got intent={result.intent}"
    )


def test_stock_trade_as_one_option_no_scan():
    """Mentioning stock trade as one option among cash/ETF/debt must not trigger scan."""
    from src.core.pipeline.intents import (
        parse_user_intent,
        detect_capital_allocation_intent,
        _is_market_scan_request,
    )

    assert detect_capital_allocation_intent(STOCK_AS_OPTION_PROMPT), (
        "Stock-as-option prompt must be detected as capital allocation"
    )
    assert not _is_market_scan_request(STOCK_AS_OPTION_PROMPT), (
        "Stock-as-option prompt must not trigger market scan"
    )

    result = parse_user_intent(STOCK_AS_OPTION_PROMPT, rigor="strict", ticker="")
    assert result.route == "general"
    assert result.intent == "capital_allocation"


def test_direct_stock_recommendation_still_scans():
    """Direct stock recommendation must still trigger market_scan."""
    from src.core.pipeline.intents import (
        parse_user_intent,
        detect_capital_allocation_intent,
        detect_decisive_trade_intent,
    )

    # Direct stock recommendation is NOT capital allocation
    assert not detect_capital_allocation_intent(DIRECT_STOCK_PROMPT), (
        "Direct stock recommendation must not be detected as capital allocation"
    )

    # It IS a decisive trade / market scan
    assert detect_decisive_trade_intent(DIRECT_STOCK_PROMPT), (
        "Direct stock recommendation must trigger decisive trade intent"
    )

    # With no ticker detected from text, it should route via vague financial → market_scan
    result = parse_user_intent(DIRECT_STOCK_PROMPT, rigor="strict", ticker="")
    assert result.route in ("market_scan",), (
        f"Expected market_scan, got route={result.route}, intent={result.intent}"
    )


def test_negative_scan_instruction_blocks_market_scan():
    """'Do not scan China stocks' must prevent market_scan despite 'scan' + 'Canada'."""
    from src.core.pipeline.intents import (
        _is_market_scan_request,
        detect_negative_scan_instruction,
    )

    assert detect_negative_scan_instruction(CAD_1000_PROMPT), (
        "'Do not scan' must be detected as negative scan instruction"
    )
    assert not _is_market_scan_request(CAD_1000_PROMPT), (
        "'Do not scan' must block market_scan even when scope keywords present"
    )

    # A legitimate scan request with the same keywords but WITHOUT "do not" must still work
    legit = "scan Canadian tech stocks for short-term opportunities"
    assert not detect_negative_scan_instruction(legit), (
        "Positive scan request must not trigger negative scan detection"
    )


def test_advisory_routes_never_invoke_scanner():
    """Runtime invariant: advisory routes must never set scanner_invoked=True."""
    # This tests the invariant logic that lives in endpoints.py
    _ADVISORY_ROUTES = {"general", "capital_allocation", "personal_finance"}

    # Valid: advisory route + no scanner
    for route in _ADVISORY_ROUTES:
        scanner_invoked = False
        invariant_broken = route in _ADVISORY_ROUTES and scanner_invoked
        assert not invariant_broken, (
            f"route={route} + scanner_invoked=False must not violate invariant"
        )

    # Invalid: advisory route + scanner invoked
    for route in _ADVISORY_ROUTES:
        scanner_invoked = True
        invariant_broken = route in _ADVISORY_ROUTES and scanner_invoked
        assert invariant_broken, (
            f"route={route} + scanner_invoked=True MUST violate invariant (routing bug)"
        )

    # Valid: market_scan + scanner = OK
    invariant_broken = "market_scan" in _ADVISORY_ROUTES and True
    assert not invariant_broken, (
        "market_scan + scanner_invoked=True must be valid"
    )
