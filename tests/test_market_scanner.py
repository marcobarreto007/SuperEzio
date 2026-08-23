import sys
import types

import pytest


def test_english_scan_requests_route_to_market_scan():
    from src.core.pipeline.intents import parse_user_intent

    cases = [
        "scan technology stocks in United States",
        "market scan technology US equities",
    ]

    for message in cases:
        plan = parse_user_intent(message).to_plan()
        assert plan["route"] == "market_scan"
        assert plan["intent"] == "market_scan"
        assert plan["ticker"] == ""
        assert plan["filters"]["country"] == "United States"
        assert plan["filters"]["sector"] == "Information Technology"


def test_portuguese_high_risk_small_market_request_routes_to_market_scan():
    from src.core.pipeline.intents import parse_user_intent

    message = (
        "Bob , eu tenho 100 cada para investir com risco alto , "
        "pesquisa para mim mercado de pequeno $$$"
    )

    plan = parse_user_intent(message).to_plan()

    assert plan["route"] == "market_scan"
    assert plan["intent"] == "market_scan"
    assert plan["ticker"] == ""


def test_market_scanner_imports_from_production_path():
    from src.core.scanner import MarketScanner

    assert MarketScanner is not None


@pytest.mark.asyncio
async def test_run_scan_uses_restored_market_scanner(monkeypatch):
    """The restored MarketScanner must drive _run_scan and feed the gate."""
    import core.trading.td_universe as _td_universe
    from src.core import scanner as scanner_module
    from src.core.pipeline.nodes.collector import _run_scan

    # FakeScanner has no scan_equities_detailed, so items reach the TD gate
    # with only a country label — the fresh-manifest fallback must vouch for
    # them. Pin the manifest deterministically (no real-manifest freshness
    # dependency in unit tests).
    monkeypatch.setattr(
        _td_universe, "_tradable_symbols_cached", lambda: frozenset({"NVDA", "MSFT"})
    )

    class FakeScanner:
        def scan_equities(self, country=None, sector=None, industry=None, limit=10):
            assert country == "United States"
            assert sector == "Technology"
            assert limit == 12
            return ["NVDA", "MSFT"]

    class FakeHub:
        def get_price(self, ticker):
            # Fully-enriched stub so candidates clear the data-quality gate.
            return {
                "price": 100.0,
                "volume": 25_000_000,
                "currency": "USD",
                "provider": f"fake-{ticker}",
                "catalyst": f"{ticker} reports Q2 earnings on 2026-08-27.",
                "risk": f"{ticker} Q2 revenue may miss published consensus.",
                "invalidation": f"Invalidate {ticker} on a close below USD 92 after Q2.",
                "provenance": {
                    field: {"source": f"fake-{ticker}"}
                    for field in (
                        "ticker",
                        "price",
                        "volume",
                        "catalyst",
                        "risk",
                        "invalidation",
                    )
                },
            }

    monkeypatch.setattr(scanner_module, "MarketScanner", FakeScanner)
    monkeypatch.setitem(sys.modules, "data.data_hub", types.SimpleNamespace(hub=FakeHub()))
    try:
        import src.core.scanner.openbb_scanner as _obb_mod

        monkeypatch.setattr(_obb_mod, "_OPENBB_AVAILABLE", False)
    except ImportError:
        pass

    result = await _run_scan(
        "scan technology stocks",
        {"country": "United States", "sector": "Technology"},
    )

    assert result["source_errors"] == []
    assert result["data_quality"] == "provider_or_computed"
    assert result["universe"] == "explicit:United States"
    assert [c["ticker"] for c in result["candidates"]] == ["NVDA", "MSFT"]
    nvda = result["candidates"][0]
    assert nvda["source"] == "financedatabase"
    assert nvda["price"] == 100.0
    assert nvda["volume"] == 25_000_000
    assert nvda["catalyst"]
