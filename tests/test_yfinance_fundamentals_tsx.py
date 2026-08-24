"""TSX (.TO) fundamentals gap — yfinance keyless fallback (P2, 2026-08-23).

Regression guards for the TD.TO pipeline failure where the fundamentals
capability exhausted every provider (Finnhub key invalid, no other route).

Covered here, all hermetic (no network):
  1. YFinanceProvider.get_fundamentals maps Yahoo `Ticker.info` fields onto
     the DataHub fundamentals contract for .TO tickers.
  2. Empty Yahoo info degrades to an explicit error (never a fake payload).
  3. yfinance 1.5.x timezone KeyError branch falls back to get_info().
  4. DataHub routes `fundamentals` to yfinance when the Finnhub key is absent.
  5. ProfessionalCollector fundamentals mesh spec surfaces hub fundamentals.
"""

from __future__ import annotations

import sys
import types

from data.data_hub import DataHub
from data.yfinance_provider import YFinanceProvider

# ── Fake yfinance module (injected into sys.modules; no network) ────────────

_FAKE_INFO = {
    "longName": "Toronto Dominion Bank",
    "shortName": "TD Bank",
    "trailingPE": 12.5,
    "forwardPE": 11.9,
    "beta": 1.1,
    "trailingEps": 8.51,
    "forwardEps": 9.2,
    "dividendYield": 2.78,
    "priceToBook": 1.4,
    "priceToSalesTrailing12Months": 3.1,
    "returnOnEquity": 0.16,
    "returnOnAssets": 0.008,
    "profitMargins": 0.31,
    "operatingMargins": 0.42,
    "grossMargins": 1.0,
    "revenueGrowth": 0.05,
    "earningsGrowth": 0.07,
    "debtToEquity": 1.7,
    "currentRatio": 0.9,
    "enterpriseToEbitda": 14.2,
    "sector": "Financial Services",
    "industry": "Banks — Diversified",
    "marketCap": 145000000000,
    "averageVolume": 3500000,
    "currency": "CAD",
    "country": "Canada",
    "exchange": "TOR",
}


class _FakeTicker:
    def __init__(self, symbol: str, info: dict, raise_timezone: bool = False) -> None:
        self._symbol = symbol
        self._info = info
        self._raise_timezone = raise_timezone

    @property
    def info(self) -> dict:
        if self._raise_timezone:
            raise KeyError("exchangeTimezoneName")
        return self._info

    def get_info(self) -> dict:
        return self._info


def _install_fake_yfinance(monkeypatch, info: dict, raise_timezone: bool = False) -> None:
    """Inject a fake `yfinance` module so no provider method touches the network."""

    def ticker_factory(symbol: str) -> _FakeTicker:
        return _FakeTicker(symbol, info=info, raise_timezone=raise_timezone)

    fake = types.SimpleNamespace(Ticker=ticker_factory, download=lambda *a, **k: None)
    monkeypatch.setitem(sys.modules, "yfinance", fake)


# ── YFinanceProvider.get_fundamentals ───────────────────────────────────────


def test_get_fundamentals_maps_info_for_to_ticker(monkeypatch) -> None:
    _install_fake_yfinance(monkeypatch, _FAKE_INFO)
    provider = YFinanceProvider()

    result = provider.get_fundamentals("TD.TO")

    assert "error" not in result
    assert result["symbol"] == "TD.TO"
    assert result["yahoo_symbol"] == "TD.TO"
    assert result["provider"] == "yfinance"
    assert result["name"] == "Toronto Dominion Bank"
    assert result["pe_ratio"] == 12.5
    assert result["forward_pe"] == 11.9
    assert result["beta"] == 1.1
    assert result["eps"] == 8.51
    assert result["dividend_yield"] == 2.78
    assert result["roe"] == 0.16
    assert result["profit_margin"] == 0.31
    assert result["revenue_growth_yoy"] == 0.05
    assert result["sector"] == "Financial Services"
    assert result["industry"] == "Banks — Diversified"
    assert result["market_cap"] == 145000000000
    assert result["avg_daily_volume_shares"] == 3500000


def test_get_fundamentals_empty_info_returns_explicit_error(monkeypatch) -> None:
    _install_fake_yfinance(monkeypatch, {})
    provider = YFinanceProvider()

    result = provider.get_fundamentals("TD.TO")

    assert result == {"error": "yfinance_no_fundamentals", "symbol": "TD.TO"}


def test_get_fundamentals_timezone_keyerror_falls_back_to_get_info(monkeypatch) -> None:
    _install_fake_yfinance(monkeypatch, _FAKE_INFO, raise_timezone=True)
    provider = YFinanceProvider()

    result = provider.get_fundamentals("RY.TO")

    assert result["pe_ratio"] == 12.5
    assert result["yahoo_symbol"] == "RY.TO"


def test_get_fundamentals_invalid_symbol_is_an_error() -> None:
    provider = YFinanceProvider()
    assert provider.get_fundamentals("")["error"] == "invalid_symbol"


# ── DataHub fundamentals routing (Finnhub key absent → yfinance) ────────────


def test_datahub_routes_fundamentals_to_yfinance_when_finnhub_key_missing(
    monkeypatch,
) -> None:
    monkeypatch.setenv("FINNHUB_API_KEY", "")  # invalid/missing key → route off
    _install_fake_yfinance(monkeypatch, _FAKE_INFO)

    class _OfflineTmx:
        """Deterministic TMX: no real money.tmx.com GraphQL call in unit tests."""

        def get_fundamentals(self, symbol: str, **_: object) -> dict[str, object]:
            return {"error": "tmx_offline_in_test", "symbol": symbol}

    import data.data_hub as _data_hub_module

    monkeypatch.setattr(_data_hub_module, "_make_tmx_provider", lambda: _OfflineTmx())

    hub = DataHub(register_defaults=True)
    fundamentals_routes = [r["name"] for r in hub.list_routes("fundamentals")]
    # TMX (priority 25, Canadian fallback) joined the chain on 2026-08-23,
    # sitting just above the yfinance last resort.
    assert fundamentals_routes == ["finnhub", "tmx", "yfinance"]

    result = hub.get_fundamentals("TD.TO")

    assert "error" not in result
    assert result["provider"] == "yfinance"
    assert result["pe_ratio"] == 12.5
    assert result["sector"] == "Financial Services"


def test_datahub_fundamentals_result_is_usable_by_capability_validation() -> None:
    payload = {
        "symbol": "TD.TO",
        "source": "yfinance",
        "provider": "yfinance",
        "pe_ratio": 12.5,
    }
    assert DataHub._is_usable_result(payload, "fundamentals") is True
    assert (
        DataHub._is_usable_result(
            {"symbol": "TD.TO", "source": "yfinance", "provider": "yfinance"}, "fundamentals"
        )
        is False
    )


# ── ProfessionalCollector mesh fundamentals spec ────────────────────────────


def test_professional_collector_fetch_hub_fundamentals_passes_through(monkeypatch) -> None:
    import data.data_hub as datahub_module
    from core.data_collector import professional as pro

    fake_hub = types.SimpleNamespace(
        get_fundamentals=lambda ticker: {"symbol": ticker, "pe_ratio": 12.5, "source": "yfinance"}
    )
    monkeypatch.setattr(datahub_module, "hub", fake_hub)

    result = pro.ProfessionalCollector._fetch_hub_fundamentals("TD.TO")

    assert result["symbol"] == "TD.TO"
    assert result["pe_ratio"] == 12.5
    assert result["source"] == "datahub"
    assert result["timestamp"]


def test_professional_collector_fetch_hub_fundamentals_surfaces_hub_error(monkeypatch) -> None:
    import data.data_hub as datahub_module
    from core.data_collector import professional as pro

    fake_hub = types.SimpleNamespace(
        get_fundamentals=lambda ticker: {"error": "no_provider_result_for_fundamentals"}
    )
    monkeypatch.setattr(datahub_module, "hub", fake_hub)

    result = pro.ProfessionalCollector._fetch_hub_fundamentals("TD.TO")

    assert result["error"] == "no_provider_result_for_fundamentals"
