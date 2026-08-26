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


@pytest.fixture(autouse=True)
def _disable_mangala_seed(monkeypatch):
    """These gate tests own their stubbed universe — the daily-seed fallback
    must not inject real candidates into the counts (c428def)."""
    monkeypatch.setenv("SUPEREZIO_MANGALA_SEED_PATH", "tests/.no_seed.json")


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
    monkeypatch.setitem(sys.modules, "data.data_hub", types.SimpleNamespace(hub=StubHub()))
    try:
        import src.core.scanner.openbb_scanner as _obb_mod

        monkeypatch.setattr(_obb_mod, "_OPENBB_AVAILABLE", False)
    except ImportError:
        pass

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
    monkeypatch.setitem(sys.modules, "data.data_hub", types.SimpleNamespace(hub=StubHub()))
    try:
        import src.core.scanner.openbb_scanner as _obb_mod

        monkeypatch.setattr(_obb_mod, "_OPENBB_AVAILABLE", False)
    except ImportError:
        pass

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
        isinstance(t, str) and (t.endswith(".SZ") or t.endswith(".SS")) for t in all_tickers
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
    monkeypatch.setitem(sys.modules, "data.data_hub", types.SimpleNamespace(hub=StubHub()))
    try:
        import src.core.scanner.openbb_scanner as _obb_mod

        monkeypatch.setattr(_obb_mod, "_OPENBB_AVAILABLE", False)
    except ImportError:
        pass

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
                    "risk": "Q1 guidance may fall below the current analyst consensus.",
                    "invalidation": "Close below 20-day moving average.",
                    "name": "Apple Inc.",
                    "confidence": "medium",
                }
            # INCOMPLETE: no price → gate rejects for missing_price,
            # fallback catalyst cannot save it.
            return {"error": "no_price_available"}

        def get_profile(self, ticker):
            return {"name": ticker, "exchange": "NASDAQ", "source": "finnhub"}

        def route(self, capability, ticker):
            return {}

        def list_routes(self, capability=None):
            return [{"name": "finnhub", "configured": True}]

    monkeypatch.setattr(scanner_module, "MarketScanner", StubScanner)
    monkeypatch.setitem(sys.modules, "data.data_hub", types.SimpleNamespace(hub=StubHub()))

    # Patch the actual module-level flag — _run_scan imports from
    # ...scanner.openbb_scanner, not from the scanner package re-export.
    try:
        import src.core.scanner.openbb_scanner as _obb_mod

        monkeypatch.setattr(_obb_mod, "_OPENBB_AVAILABLE", False)
    except ImportError:
        pass

    result = await _run_scan(
        "Scan US technology equities for 2-week opportunities.",
        {"country": "United States"},
    )

    candidate_tickers = [c["ticker"] for c in result["candidates"]]
    assert "AAPL" in candidate_tickers

    aapl = next(c for c in result["candidates"] if c["ticker"] == "AAPL")
    for required in ("ticker", "price", "volume", "catalyst", "risk", "invalidation"):
        assert aapl.get(required), f"valid candidate missing required field {required}"

    # INCOMPLETE lacks price — the fallback catalyst cannot save it,
    # and the gate rejects for missing_price.
    incomplete = next((r for r in result["rejected"] if r.get("ticker") == "INCOMPLETE"), None)
    assert incomplete is not None
    assert incomplete.get("rejected_reason") == "missing_price"


def test_candidate_gate_rejects_missing_evidence_and_provenance():
    """Price and liquidity alone must never become an investment candidate."""
    from src.core.pipeline.nodes.collector import _apply_candidate_gate

    base = {
        "ticker": "A",
        # A country label alone no longer proves a TD-listed venue (TD lock,
        # 2026-08-23); use a real venue so this test exercises provenance.
        "market": "NYSE",
        "price": 114.96,
        "volume": 2_200_000,
    }

    ok, reason = _apply_candidate_gate(
        base,
        allow_penny_otc=False,
        allow_microcap=False,
    )
    assert not ok
    assert reason == "missing_ticker_provenance"


def test_final_decision_is_not_buy_just_because_ranked_list_exists():
    from src.core.pipeline.nodes.collector import _final_scan_decision

    waiting = [{"candidate": {"ticker": "ZZZZ"}, "eligible": False, "decision": "WAIT"}]

    assert _final_scan_decision(waiting) == "WAIT"
    assert _final_scan_decision([]) == "REJECT_ALL"
    assert (
        _final_scan_decision(
            [
                {
                    "candidate": {"ticker": "REAL"},
                    "eligible": True,
                    "gate_failures": [],
                    "decision": "BUY_CANDIDATE",
                }
            ]
        )
        == "BUY_CANDIDATE"
    )


@pytest.mark.asyncio
async def test_priced_candidates_fail_on_thesis_not_price(monkeypatch):
    """Price and volume cannot be promoted through a generic thesis fallback."""
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
            # Generic catalyst text cannot authorize a candidate (fail-closed
            # contract since 413e1ea) — unlike an error, which now triggers
            # the computed price+volume fallback and would PASS.
            return {"catalyst": "Liquid equity on major exchange", "source": "finnhub"}

        def list_routes(self, capability=None):
            return [{"name": "finnhub", "configured": True}]

    monkeypatch.setattr(scanner_module, "MarketScanner", StubScanner)
    monkeypatch.setitem(sys.modules, "data.data_hub", types.SimpleNamespace(hub=StubHub()))

    # Patch the actual module-level flag — _run_scan imports from
    # ...scanner.openbb_scanner, not from the scanner package re-export.
    try:
        import src.core.scanner.openbb_scanner as _obb_mod

        monkeypatch.setattr(_obb_mod, "_OPENBB_AVAILABLE", False)
    except ImportError:
        pass

    result = await _run_scan(
        "What large-cap stock would you recommend if I want to profit within the next 2 weeks?",
        {},
    )

    assert result["candidates"] == []
    summary = result["rejection_summary"]
    assert summary.get("missing_price", 0) == 0
    assert summary.get("missing_catalyst", 0) == 2
    assert result["scan_trace"]["final_decision"] == "REJECT_ALL"


@pytest.mark.asyncio
async def test_under_cad_price_request_filters_expensive_candidates(monkeypatch):
    from src.core import scanner as scanner_module
    from src.core.pipeline.nodes.collector import _run_scan

    class StubScanner:
        def scan_equities(self, country=None, sector=None, industry=None, limit=10):
            return ["CHEAP", "EXPENSIVE"]

    class StubHub:
        def get_price(self, ticker, **kwargs):
            price = 4.25 if ticker == "CHEAP" else 12.50
            return {
                "ticker": ticker,
                "price": price,
                "volume": 3_000_000,
                "currency": "CAD",
                "provider": "stub",
                "market": "Canada",
                "exchange": "TSX",
                "catalyst": f"{ticker} reports audited FY results on 2026-09-02.",
                "risk": f"{ticker} FY revenue may miss the published CAD 20M consensus.",
                "invalidation": f"Invalidate if {ticker} closes below CAD 3.80 after results.",
            }

        def get_profile(self, ticker):
            return {"name": f"{ticker} Corp", "sector": "Technology", "provider": "stub"}

        def route(self, capability, ticker):
            return {
                "catalyst": f"{ticker} reports audited FY results on 2026-09-02.",
                "risk": f"{ticker} FY revenue may miss the published CAD 20M consensus.",
                "invalidation": f"Invalidate if {ticker} closes below CAD 3.80 after results.",
                "provider": "stub",
            }

        def get_fundamentals(self, ticker):
            return {"market_cap": 1_000_000_000, "provider": "stub"}

        def list_routes(self, capability=None):
            return [{"name": "stub", "configured": True}]

    monkeypatch.setattr(scanner_module, "MarketScanner", StubScanner)
    monkeypatch.setitem(sys.modules, "data.data_hub", types.SimpleNamespace(hub=StubHub()))
    try:
        import src.core.scanner.openbb_scanner as _obb_mod

        monkeypatch.setattr(_obb_mod, "_OPENBB_AVAILABLE", False)
    except ImportError:
        pass

    result = await _run_scan(
        "Find one US or Canadian small-cap stock under CAD 5 with liquidity and a real catalyst.",
        {"country": "Canada"},
    )

    assert result["filters"]["max_price"] == 5.0
    assert [c["ticker"] for c in result["candidates"]] == ["CHEAP"]
    assert any(r.get("ticker") == "EXPENSIVE" for r in result["rejected"])
    assert result["rejection_summary"]["price_above_requested_max"] == 1


@pytest.mark.asyncio
async def test_fundamentals_failures_do_not_skip_catalyst_enrichment(monkeypatch):
    """Fundamentals is optional enrichment; its failures must not trip catalyst."""
    from src.core import scanner as scanner_module
    from src.core.pipeline.nodes.collector import _run_scan

    tickers = [f"TEST{i}" for i in range(6)]
    monkeypatch.setenv("SUPEREZIO_SCAN_MAX_CANDIDATES_AFTER_GATE", "5")

    class StubScanner:
        def scan_equities(self, country=None, sector=None, industry=None, limit=10):
            if country == "United States":
                return tickers
            return []

    class StubHub:
        def __init__(self):
            self.catalyst_calls: list[str] = []

        def get_price(self, ticker, **kwargs):
            return {
                "price": 150.0,
                "volume": 25_000_000,
                "source": "finnhub",
            }

        def get_profile(self, ticker):
            return {"name": ticker, "exchange": "NASDAQ", "source": "finnhub"}

        def get_fundamentals(self, ticker):
            return {"error": "no_metrics"}

        def route(self, capability, ticker):
            if capability == "short_term_catalyst":
                self.catalyst_calls.append(ticker)
                return {
                    "catalyst": f"{ticker} reports Q2 earnings on 2026-09-02.",
                    "risk": f"{ticker} Q2 revenue may miss the published consensus estimate.",
                    "invalidation": "Close below the 20-day moving average.",
                    "source": "finnhub",
                }
            return {}

        def list_routes(self, capability=None):
            return [{"name": "finnhub", "configured": True}]

    hub = StubHub()
    monkeypatch.setattr(scanner_module, "MarketScanner", StubScanner)
    monkeypatch.setitem(sys.modules, "data.data_hub", types.SimpleNamespace(hub=hub))

    try:
        import src.core.scanner.openbb_scanner as _obb_mod

        monkeypatch.setattr(_obb_mod, "_OPENBB_AVAILABLE", False)
    except ImportError:
        pass

    result = await _run_scan(
        "Scan US technology equities for 2-week opportunities.",
        {"country": "United States"},
    )

    # Operator decision 2026-08-23: discovery scans include the penny/microcap
    # universe by default, so enrichment covers MORE than the stubbed tickers.
    assert set(tickers) <= set(hub.catalyst_calls)
    assert result["scan_trace"]["gated_candidate_count"] >= len(tickers)
    # Penny-universe additions may legitimately reject (OTC venue lock) —
    # what matters is that every stubbed listed candidate made it through.
    # Cap is 5 and the stub set has 6 — at least 5 stubs must survive.
    stub_hits = sum(any(c.get("ticker") == t for c in result["candidates"]) for t in tickers)
    assert stub_hits >= 5
    assert len(result["candidates"]) == 5
    breakers = result["scan_trace"]["circuit_breakers"]
    assert breakers["finnhub"]["state"] == "closed"
    assert "finnhub_fundamentals" in breakers
    assert all("Q2 earnings on 2026-09-02" in c.get("catalyst", "") for c in result["candidates"])
    assert all(c["provenance"]["catalyst"]["source"] == "finnhub" for c in result["candidates"])


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
    monkeypatch.setitem(sys.modules, "data.data_hub", types.SimpleNamespace(hub=StubHub()))

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
        assert not _wants_china_universe(text), f"False positive China trigger: '{text}'"


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
        assert _wants_china_universe(text), f"Missed China trigger: '{text}'"


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

USD_25K_ALLOCATION_PROMPT = (
    "I have $25,000 to invest. I am 35 years old, moderate risk tolerance. "
    "How should I allocate this capital? Give me a specific allocation with percentages and tickers."
)

DIRECT_STOCK_PROMPT = (
    "What stock would you recommend me to buy if I want to make a profit within the next 14 days?"
)


def test_cad_1000_capital_allocation_no_scan():
    """CAD 1,000 allocation prompt must route to capital_allocation, not market_scan."""
    from src.core.pipeline.intents import (
        _is_market_scan_request,
        detect_capital_allocation_intent,
        detect_complex_finance_intent,
        parse_user_intent,
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
    assert result.route == "general", f"Expected route=general, got route={result.route}"
    assert result.intent == "capital_allocation", (
        f"Expected intent=capital_allocation, got intent={result.intent}"
    )


def test_stock_trade_as_one_option_no_scan():
    """Mentioning stock trade as one option among cash/ETF/debt must not trigger scan."""
    from src.core.pipeline.intents import (
        _is_market_scan_request,
        detect_capital_allocation_intent,
        parse_user_intent,
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


def test_usd_25k_allocation_with_tickers_routes_to_capital_allocation():
    """Allocation with amount/risk/percentages is advisory, not a generic chat answer."""
    from src.core.pipeline.intents import detect_capital_allocation_intent, parse_user_intent

    assert detect_capital_allocation_intent(USD_25K_ALLOCATION_PROMPT)

    result = parse_user_intent(USD_25K_ALLOCATION_PROMPT, rigor="strict", ticker="")
    assert result.route == "general"
    assert result.intent == "capital_allocation"


def test_direct_stock_recommendation_delegates_scan_decision_to_bob():
    """Direct stock recommendation lets Bob decide whether a scan is needed."""
    from src.core.pipeline.intents import (
        detect_capital_allocation_intent,
        detect_decisive_trade_intent,
        parse_user_intent,
    )

    # Direct stock recommendation is NOT capital allocation
    assert not detect_capital_allocation_intent(DIRECT_STOCK_PROMPT), (
        "Direct stock recommendation must not be detected as capital allocation"
    )

    # It IS a decisive trade / market scan
    assert detect_decisive_trade_intent(DIRECT_STOCK_PROMPT), (
        "Direct stock recommendation must trigger decisive trade intent"
    )

    # With no ticker detected from text, "What stock to buy" now routes
    # directly to market_scan — the user expects scanner evidence, not a
    # DISCOVERY_DECISION framework. Expanded SCAN_COMMAND_HINTS + English
    # financial hints ensure English prompts get the full pipeline.
    result = parse_user_intent(DIRECT_STOCK_PROMPT, rigor="strict", ticker="")
    plan = result.to_plan()

    assert result.route == "market_scan"
    assert result.intent == "market_scan"
    assert result.action == "scan_market"
    assert plan["scanner_allowed"] is True
    assert "market_scan" in plan["allowed_tools"]


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
    from src.agent_server.endpoints import _is_advisory_scanner_violation

    # Valid: advisory route + no scanner
    for route in ("general", "capital_allocation", "personal_finance"):
        assert not _is_advisory_scanner_violation(
            route_used=route,
            detected_intent="CAPITAL_ALLOCATION",
            scanner_invoked=False,
        )

    # Invalid: advisory route + scanner invoked
    for route in ("capital_allocation", "personal_finance"):
        assert _is_advisory_scanner_violation(
            route_used=route,
            detected_intent="general_question",
            scanner_invoked=True,
        )

    # Invalid: advisory intent + scanner invoked, even if route is generic
    for intent in ("MACRO_THESIS", "CAPITAL_ALLOCATION", "PERSONAL_FINANCE"):
        assert _is_advisory_scanner_violation(
            route_used="general",
            detected_intent=intent,
            scanner_invoked=True,
        )

    # Valid: sovereign opportunity search can keep route=general while scanning
    assert not _is_advisory_scanner_violation(
        route_used="general",
        detected_intent="buscar_oportunidade",
        scanner_invoked=True,
    )
    assert not _is_advisory_scanner_violation(
        route_used="market_scan",
        detected_intent="market_scan",
        scanner_invoked=True,
    )


# ---------------------------------------------------------------------------
# P0 regression: chart ticker must NOT hijack market scan routing
# ---------------------------------------------------------------------------

SCAN_WITH_CHART_TICKER_PROMPT = (
    "Find one US or Canadian small-cap stock with a real 14-day catalyst. "
    "Use only US_CANADA_LIQUID universe. "
    "Do not use China A-shares. "
    "Do not use penny stocks. "
    "Do not use microcaps below $300M. "
    "Give me one decisive model order: BUY_CANDIDATE, WAIT, or REJECT_ALL."
)


def test_market_scan_not_hijacked_by_chart_ticker():
    """Explicit scan request must route to market_scan even when chart ticker is set."""
    from src.core.pipeline.intents import _is_market_scan_request, parse_user_intent

    # The message itself IS a market scan request
    assert _is_market_scan_request(SCAN_WITH_CHART_TICKER_PROMPT), (
        "Scan request must be detected as market_scan"
    )

    # With a chart ticker lingering (e.g., AAPL in UI), routing must still be market_scan
    result = parse_user_intent(SCAN_WITH_CHART_TICKER_PROMPT, rigor="strict", ticker="AAPL")
    assert result.route == "market_scan", (
        f"Expected market_scan, got {result.route} — chart ticker hijacked routing"
    )
    assert result.intent == "market_scan"


def test_portuguese_search_word_busca_is_not_ticker():
    """Portuguese discovery commands must not route as ticker BUSCA/ETFS."""
    from src.core.pipeline.intents import detect_ticker, parse_user_intent

    prompt = (
        "FACA UMA BUSCA DE 3 SUGESTOES COM UM HISTORICO DE 6 MESES PARA TRAS "
        "E ME SUGIRA 3 OPORTUNIDADE PARA ESTES 12 MESES , FOCADO NO MERCADO CANADENSE"
    )

    assert detect_ticker(prompt) == ""

    result = parse_user_intent(prompt, rigor="strict", ticker="")
    plan = result.to_plan()

    assert result.route == "market_scan"
    assert result.intent == "market_scan"
    assert result.ticker == ""
    assert result.filters.get("country") == "Canada"
    assert plan["cognitive_mode"] == "MARKET_DISCOVERY"
    assert plan["scanner_allowed"] is True


def test_portuguese_research_commands_do_not_become_tickers():
    """Parser must treat Portuguese search words as intent, not assets."""
    from src.core.pipeline.intents import detect_ticker

    false_ticker_prompts = [
        "BUSCA 3 oportunidades no mercado canadense",
        "PESQUISE ETFs canadenses de alta volatilidade",
        "PROCURE 3 sugestoes para os proximos 12 meses",
        "SUGIRA uma lista de oportunidades canadenses",
        "FACA uma pesquisa de historico de 6 meses",
    ]

    for prompt in false_ticker_prompts:
        assert detect_ticker(prompt) == "", f"False ticker detected for: {prompt}"


def test_money_amount_suffixes_are_not_tickers():
    """Amounts such as 5K and 10M must not hijack advisory routing."""
    from src.core.pipeline.intents import detect_ticker

    amount_prompts = [
        "I have 5K to invest in my TFSA",
        "Tenho 10k CAD para investir",
        "Allocate 2M for a moderate risk portfolio",
        "Should I keep 25K in cash or buy ETFs?",
    ]

    for prompt in amount_prompts:
        assert detect_ticker(prompt) == "", f"Money amount detected as ticker: {prompt}"


def test_numeric_letter_tickers_still_work_when_not_money_suffixes():
    """Rare alphanumeric tickers stay detectable when not K/M/B amounts."""
    from src.core.pipeline.intents import detect_ticker

    assert detect_ticker("Analyze 88E for a speculative setup") == "88E"


def test_real_canadian_tickers_still_route_to_ticker_analysis():
    """Killing ticker-first must not break explicit ticker analysis."""
    from src.core.pipeline.intents import detect_ticker, parse_user_intent

    prompt = "Analise RY.TO e ENB.TO para os proximos 12 meses"

    assert detect_ticker(prompt) in {"RY.TO", "ENB.TO"}
    result = parse_user_intent(prompt, rigor="strict", ticker="")

    assert result.route == "ticker_analysis"
    assert result.intent == "ticker_analysis"
    assert result.ticker in {"RY.TO", "ENB.TO"}


def test_fax_industry_research_is_thesis_first_no_scanner():
    from src.core.pipeline.intents import parse_user_intent

    result = parse_user_intent(
        "Research the fax industry as an investment theme. Should I look for fax stocks, "
        "or is there a better adjacent opportunity? Do not scan tickers unless needed.",
        rigor="strict",
        ticker="",
    )
    plan = result.to_plan()

    assert result.route == "general"
    assert plan["cognitive_mode"] == "ANSWER_ONLY"
    assert plan["scanner_allowed"] is False
    assert plan["ticker_allowed"] is False


def test_cad50_weekly_risk_lab_is_not_scanner_by_default():
    from src.core.pipeline.intents import parse_user_intent

    result = parse_user_intent(
        "I like risking CAD 50 per week instead of lottery tickets. "
        "Treat it as a risk lab and tell me the rules before any trade.",
        rigor="strict",
        ticker="",
    )
    plan = result.to_plan()

    assert result.route == "general"
    assert plan["cognitive_mode"] == "ANSWER_ONLY"
    assert plan["scanner_allowed"] is False
    assert plan["ticket_allowed"] is False


def test_dividend_passive_income_is_final_only_advisory():
    from src.core.pipeline.intents import parse_user_intent

    result = parse_user_intent(
        "I want to build a passive income portfolio with dividend stocks. "
        "What are 5 solid dividend stocks or ETFs for a Canadian investor? "
        "Consider tax efficiency and withholding taxes.",
        rigor="strict",
        ticker="",
    )
    plan = result.to_plan()

    assert result.route == "general"
    assert plan["scanner_allowed"] is False
    assert plan["ticker_allowed"] is False


def test_etf_comparison_is_not_single_ticker_analysis():
    from src.core.pipeline.intents import parse_user_intent

    result = parse_user_intent(
        "Compare VOO, VTI, and SCHD for a long-term buy-and-hold investor. "
        "Which one would you recommend and why? Consider fees, diversification, and historical performance.",
        rigor="strict",
        ticker="",
    )
    plan = result.to_plan()

    assert result.route == "general"
    assert result.ticker == ""
    assert plan["scanner_allowed"] is False
    assert plan["ticker_allowed"] is False


def test_concentrated_position_is_personal_finance_not_single_ticker_analysis():
    from src.core.pipeline.intents import parse_user_intent

    result = parse_user_intent(
        "I hold a concentrated position in AAPL (40% of my portfolio). "
        "Is this too risky? How should I diversify without triggering a huge tax bill?",
        rigor="strict",
        ticker="",
    )
    plan = result.to_plan()

    assert result.route == "general"
    assert result.intent == "personal_finance"
    assert result.ticker == ""
    assert plan["scanner_allowed"] is False
    assert plan["ticker_allowed"] is False


def test_explicit_smallcap_discovery_keeps_scanner_allowed():
    from src.core.pipeline.intents import parse_user_intent

    result = parse_user_intent(
        "Find one US or Canadian small-cap stock under CAD 5 with liquidity and a real catalyst.",
        rigor="strict",
        ticker="",
    )
    plan = result.to_plan()

    assert result.route == "market_scan"
    assert plan["cognitive_mode"] == "MARKET_DISCOVERY"
    assert plan["scanner_allowed"] is True
    assert "market_scan" in plan["allowed_tools"]


def test_exact_cad100_mini_cap_prompt_is_decisive_microcap_scan():
    from src.core.pipeline.intents import (
        detect_decisive_trade_intent,
        parse_user_intent,
    )
    from src.core.pipeline.nodes.collector import _wants_microcap

    prompt = "vamos investir 100 cad segunda , escolhe mini cap"
    result = parse_user_intent(prompt, rigor="strict", ticker="")

    assert result.route == "market_scan"
    assert result.intent == "market_scan"
    assert result.filters.get("country") == "Canada"
    assert detect_decisive_trade_intent(prompt) is True
    assert _wants_microcap(prompt) is True


def test_cognitive_contract_blocks_tool_misuse(monkeypatch):
    monkeypatch.setenv("SUPEREZIO_BOB_SOVEREIGN", "0")
    from src.core.pipeline.nodes.tool_executor import _tool_permission_error

    advisory_state = {
        "cognitive_mode": "INDUSTRY_RESEARCH",
        "allowed_tools": ["final_answer"],
        "scanner_allowed": False,
        "ticker_allowed": False,
    }
    assert "cognitive_contract" in _tool_permission_error(
        advisory_state,
        "market_scan",
        {"query": "fax stocks"},
    )

    scanner_state = {
        "cognitive_mode": "DISCOVERY_SCAN",
        "allowed_tools": ["market_scan", "final_answer"],
        "scanner_allowed": True,
        "ticker_allowed": True,
    }
    assert _tool_permission_error(scanner_state, "market_scan", {"query": "smallcaps"}) == ""


def test_ticker_analysis_still_works_with_chart_ticker():
    """When the user asks about the chart ticker, it must still route to ticker_analysis."""
    from src.core.pipeline.intents import parse_user_intent

    result = parse_user_intent(
        "What do you think about this stock for the next 14 days?",
        rigor="strict",
        ticker="AAPL",
    )
    assert result.route == "ticker_analysis", f"Expected ticker_analysis, got {result.route}"


def test_cockpit_ticker_command_routes_to_ticker_analysis_even_with_tese_wording():
    """Cockpit-generated TICKER commands must not be downgraded to industry research."""
    from src.core.pipeline.intents import detect_ticker, parse_user_intent

    prompt = (
        "TICKER DIBS: sincronize grafico + Sentimento Vivo. "
        "Bob, analise tese, risco, invalidacao e alvo/stop. "
        "Sentimento=NEUTRAL flat, score=0.03, Reddit=0 mencoes. "
        "Se virar trade, rode ferramentas antes de PAPER_TICKET."
    )

    assert detect_ticker(prompt) == "DIBS"
    result = parse_user_intent(prompt, rigor="strict", ticker="DIBS")

    assert result.route == "ticker_analysis"
    assert result.intent == "ticker_analysis"
    assert result.action == "collect_data"
    assert result.ticker == "DIBS"


# ---------------------------------------------------------------------------
# TD specialization (2026-08-23): OTC venues are never TD-tradable
# ---------------------------------------------------------------------------


def _td_candidate(ticker, exchange, price, volume):
    """Enriched candidate in the canonical gate shape (see parity tests)."""
    item = {
        "ticker": ticker,
        "name": ticker,
        "market": "United States",
        "source": "financedatabase",
        "price": price,
        "volume": volume,
        "exchange": exchange,
        "currency": "USD",
        "provider": "finnhub",
        "catalyst": f"{ticker} reports Q2 earnings on 2026-09-02 inside the requested horizon.",
        "risk": f"{ticker} Q2 revenue may miss the published consensus estimate.",
        "invalidation": "Invalidate on a close below the 20-day moving average.",
        "provenance": {
            "ticker": {"source": "financedatabase"},
            "market": {"source": "financedatabase"},
            "price": {"source": "finnhub"},
            "volume": {"source": "finnhub"},
            "catalyst": {"source": "finnhub"},
            "risk": {"source": "finnhub"},
            "invalidation": {"source": "finnhub"},
        },
    }
    return item


def test_otc_candidate_rejected_even_when_penny_otc_allowed():
    from src.core.pipeline.nodes.collector import _apply_candidate_gate

    item = _td_candidate("FAKEO", "OTC Markets", 0.8, 5_000_000)
    item["venue"] = "OTC"
    ok, reason = _apply_candidate_gate(item, allow_penny_otc=True, allow_microcap=True)
    assert not ok
    assert reason == "otc_filtered", f"expected otc_filtered, got {reason}"


def test_listed_candidate_accepted_on_td_exchanges():
    from src.core.pipeline.nodes.collector import _apply_candidate_gate

    for venue in ("TSE", "NYSE", "NASDAQ"):
        ok, reason = _apply_candidate_gate(
            _td_candidate("GOOD", venue, 25.0, 5_000_000),
            allow_penny_otc=False,
            allow_microcap=False,
        )
        assert ok, f"{venue} must be TD-tradable, got {reason}"


def test_pink_sheet_candidate_rejected():
    from src.core.pipeline.nodes.collector import _apply_candidate_gate

    item = _td_candidate("FAKE", "PNK", 2.0, 1_000_000)
    item["venue"] = "PNK"
    ok, reason = _apply_candidate_gate(item, allow_penny_otc=True, allow_microcap=True)
    assert not ok
    assert reason == "otc_filtered"


def test_foreign_exchange_candidate_rejected():
    """TD lock (2026-08-23): non-TD listed venues fail closed with their own reason."""
    from src.core.pipeline.nodes.collector import _apply_candidate_gate

    for venue in ("LSE", "BVMF", "JPX"):
        ok, reason = _apply_candidate_gate(
            _td_candidate("FAKE", venue, 25.0, 5_000_000),
            allow_penny_otc=False,
            allow_microcap=True,
        )
        assert not ok, f"{venue} must not be TD-tradable"
        assert reason == "exchange_not_td_supported", (
            f"expected exchange_not_td_supported for {venue}, got {reason}"
        )


def test_cse_neo_candidate_rejected():
    """CSE and NEO/Cboe Canada are not TD-confirmed venues — fail closed."""
    from src.core.pipeline.nodes.collector import _apply_candidate_gate

    for venue in ("CSE", "NEO"):
        item = _td_candidate("FAKE", "TSX", 4.0, 2_000_000)
        item["venue"] = venue
        ok, reason = _apply_candidate_gate(item, allow_penny_otc=True, allow_microcap=True)
        assert not ok, f"{venue} must not be TD-tradable"
        assert reason == "exchange_not_td_supported"


def test_generic_us_market_without_exchange_rejected():
    """A generic bucket like "US" cannot prove a listed venue — fail closed."""
    from src.core.pipeline.nodes.collector import _apply_candidate_gate

    item = _td_candidate("FAKE", "US", 25.0, 5_000_000)
    item.pop("venue", None)
    ok, reason = _apply_candidate_gate(item, allow_penny_otc=False, allow_microcap=True)
    assert not ok
    assert reason == "exchange_not_td_supported"


def test_country_label_item_vouched_by_fresh_manifest(monkeypatch):
    """A venue-less item passes ONLY when the fresh full manifest vouches it."""
    from core.trading import td_universe
    from src.core.pipeline.nodes.collector import _apply_candidate_gate

    monkeypatch.setattr(td_universe, "_tradable_symbols_cached", lambda: frozenset({"NVDA"}))
    vouched = _td_candidate("NVDA", "United States", 100.0, 25_000_000)
    vouched.pop("venue", None)
    ok, reason = _apply_candidate_gate(vouched, allow_penny_otc=False, allow_microcap=False)
    assert ok, f"manifest-vouched NVDA must pass, got {reason}"

    unknown = _td_candidate("ZZZZZZ", "United States", 100.0, 25_000_000)
    unknown.pop("venue", None)
    ok, reason = _apply_candidate_gate(unknown, allow_penny_otc=False, allow_microcap=True)
    assert not ok
    assert reason == "exchange_not_td_supported"


def test_country_label_item_rejected_without_manifest(monkeypatch):
    """No venue + no fresh manifest + no vouching symbol -> fail closed."""
    from core.trading import td_universe
    from src.core.pipeline.nodes.collector import _apply_candidate_gate

    monkeypatch.setattr(td_universe, "_tradable_symbols_cached", lambda: None)
    item = _td_candidate("NVDA", "United States", 100.0, 25_000_000)
    item.pop("venue", None)
    ok, reason = _apply_candidate_gate(item, allow_penny_otc=False, allow_microcap=True)
    assert not ok
    assert reason == "exchange_not_td_supported"


def test_tsx_suffix_watchlist_item_stamped_and_accepted():
    """pennylab-style .TO/.V items carry a proven exchange stamp."""
    from src.core.pipeline.nodes.collector import _apply_candidate_gate

    for ticker, exchange in (("SOMETHING.TO", "TSX"), ("OTHER.V", "TSXV")):
        item = _td_candidate(ticker, "Canada", 4.0, 2_000_000)
        item.pop("venue", None)
        item["exchange"] = exchange
        item["currency"] = "CAD"
        item["market"] = "Canada"
        ok, reason = _apply_candidate_gate(item, allow_penny_otc=True, allow_microcap=True)
        assert ok, f"{ticker} stamped {exchange} must pass, got {reason}"


def test_arca_and_amex_candidates_accepted():
    """Commission-free ETFs (SPY/GLD/SMH/GDX) live on NYSE Arca; AMEX listings exist."""
    from src.core.pipeline.nodes.collector import _apply_candidate_gate

    for venue in ("PCX", "ARCA", "NYSEARCA", "AMEX", "ASE"):
        ok, reason = _apply_candidate_gate(
            _td_candidate("GOOD", venue, 150.0, 20_000_000),
            allow_penny_otc=False,
            allow_microcap=False,
        )
        assert ok, f"{venue} must be TD-tradable (Arca/NYSE American), got {reason}"
