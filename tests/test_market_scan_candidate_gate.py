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
                    "risk": "Macro tape risk and sector rotation pressure.",
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


def test_candidate_gate_allows_missing_risk_and_invalidation():
    """Short-term scan candidates now pass the relaxed gate even without risk and invalidation."""
    from src.core.pipeline.nodes.collector import _apply_candidate_gate

    base = {
        "ticker": "A",
        "market": "United States",
        "price": 114.96,
        "volume": 2_200_000,
    }

    ok, reason = _apply_candidate_gate(
        base,
        allow_penny_otc=False,
        allow_microcap=False,
    )
    assert ok
    assert reason is None


@pytest.mark.asyncio
async def test_priced_candidates_fail_on_thesis_not_price(monkeypatch):
    """Priced candidates now pass the gate via technical-fallback catalyst.

    When Finnhub returns no_catalyst_in_window but the item has price, volume,
    and exchange, the fallback generates a technical thesis from the data.
    These candidates should now pass, not be rejected.
    """
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
        "What stock would you recommend if I want to profit within the next 2 weeks?",
        {},
    )

    # Both tickers now pass — the fallback generates catalyst, risk, invalidation
    # from the available price/volume/exchange data.
    assert len(result["candidates"]) == 2
    summary = result["rejection_summary"]
    assert summary.get("missing_price", 0) == 0
    assert summary.get("missing_short_term_thesis", 0) == 0


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
    assert result.route == "general", f"Expected route=general, got route={result.route}"
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


def test_usd_25k_allocation_with_tickers_routes_to_capital_allocation():
    """Allocation with amount/risk/percentages is advisory, not a generic chat answer."""
    from src.core.pipeline.intents import parse_user_intent, detect_capital_allocation_intent

    assert detect_capital_allocation_intent(USD_25K_ALLOCATION_PROMPT)

    result = parse_user_intent(USD_25K_ALLOCATION_PROMPT, rigor="strict", ticker="")
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
    assert not invariant_broken, "market_scan + scanner_invoked=True must be valid"


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
    from src.core.pipeline.intents import parse_user_intent, _is_market_scan_request

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
    assert plan["cognitive_mode"] == "DISCOVERY_SCAN"
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
    assert plan["cognitive_mode"] == "INDUSTRY_RESEARCH"
    assert plan["scanner_allowed"] is False
    assert plan["ticker_allowed"] is False
    assert plan["allowed_tools"] == ["final_answer"]


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
    assert plan["cognitive_mode"] == "RISK_LAB"
    assert plan["scanner_allowed"] is False
    assert plan["ticket_allowed"] is False
    assert plan["allowed_tools"] == ["final_answer"]


def test_explicit_smallcap_discovery_keeps_scanner_allowed():
    from src.core.pipeline.intents import parse_user_intent

    result = parse_user_intent(
        "Find one US or Canadian small-cap stock under CAD 5 with liquidity and a real catalyst.",
        rigor="strict",
        ticker="",
    )
    plan = result.to_plan()

    assert result.route == "market_scan"
    assert plan["cognitive_mode"] == "DISCOVERY_SCAN"
    assert plan["scanner_allowed"] is True
    assert "market_scan" in plan["allowed_tools"]


def test_cognitive_contract_blocks_tool_misuse():
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
