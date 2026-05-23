"""DataHub provider priority chain."""

from __future__ import annotations

from data.data_hub import DataHub


def test_market_price_route_order() -> None:
    hub = DataHub(register_defaults=True)
    routes = hub.list_routes("price")
    # Finnhub may be unconfigured in CI; still check relative order of fallbacks.
    ordered = [r["name"] for r in sorted(routes, key=lambda x: x["priority"])]
    assert ordered.index("finnhub") < ordered.index("twelve_data")
    assert ordered.index("twelve_data") < ordered.index("yfinance")
    assert ordered.index("yfinance") < ordered.index("stooq")


def test_finnhub_has_candles_and_news_capabilities() -> None:
    hub = DataHub(register_defaults=True)
    finn = next(r for r in hub.list_routes() if r["name"] == "finnhub")
    assert "candles" in finn["capabilities"]
    assert "news" in finn["capabilities"]
    assert finn["priority"] == 1
