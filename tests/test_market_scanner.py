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
    from src.core import scanner as scanner_module
    from src.core.pipeline.nodes.collector import _run_scan

    class FakeScanner:
        def scan_equities(self, country=None, sector=None, industry=None, limit=10):
            assert country == "United States"
            assert sector == "Technology"
            assert limit == 30
            return ["AAPL", "MSFT"]

    class FakeHub:
        def get_price(self, ticker):
            return {
                "price": 100.0,
                "currency": "USD",
                "provider": f"fake-{ticker}",
            }

    monkeypatch.setattr(scanner_module, "MarketScanner", FakeScanner)
    monkeypatch.setitem(sys.modules, "data.data_hub", types.SimpleNamespace(hub=FakeHub()))

    result = await _run_scan(
        "scan technology stocks",
        {"country": "United States", "sector": "Technology"},
    )

    assert result["source_errors"] == []
    assert result["data_quality"] == "provider_or_computed"
    assert [c["ticker"] for c in result["candidates"]] == ["AAPL", "MSFT"]
    assert result["candidates"][0]["source"] == "financedatabase"
    assert result["candidates"][0]["price"] == 100.0
