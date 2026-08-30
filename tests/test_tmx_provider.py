"""TmxProvider — contract tests with REAL responses captured from the live
money.tmx.com GraphQL API on 2026-08-23 (see
runtime/checkpoints/tmx_capture/gql_*.json for the raw captures).

Deterministic: no network — `requests.post` is monkeypatched to replay the
captured payloads, including the explicit GraphQL 404 for unknown symbols.
"""

from __future__ import annotations

from data.data_hub import DataHub
from data.tmx_provider import TmxProvider, _to_float, tmx_symbol

# ── Real captures (2026-08-23, app-money.tmx.com/graphql) ────────────────

CAPTURED_TD = {
    "symbol": "TD",
    "name": "Toronto-Dominion Bank (The)",
    "price": 161.24,
    "priceChange": -0.18,
    "percentChange": -0.11151,
    "exchangeName": "Toronto Stock Exchange",
    "exchangeCode": "TSX",
    "sector": "Finance",
    "industry": "Banking",
    "volume": 2781994,
    "openPrice": 161.88,
    "dayHigh": 163.28,
    "dayLow": 160.88,
    "MarketCap": 265210081050,
    "peRatio": 19.26,
    "prevClose": 161.42,
    "dividendFrequency": "Quarterly",
    "dividendYield": 2.778,
    "dividendAmount": 1.12,
    "dividendCurrency": "CAD",
    "beta": 0.893892,
    "eps": 12.34,
    "exDividendDate": "2026-07-10 00:00:00.0",
    "longDescription": "TD Bank US Holding Company and its subsidiaries...",
    "website": "https://www.td.com",
    "email": "tdir@td.com",
    "phoneNumber": "+1 416 944-6367",
    "fullAddress": "P.O. Box 1,Toronto Dominion Centre, Toronto, Ontario, CA",
    "employees": "101759",
    "shareOutStanding": 1644815685,
    "totalDebtToEquity": 4.21,
    "vwap": 161.440969,
    "dividendPayDate": "2026-07-31",
    "weeks52high": 175.33,
    "weeks52low": 100.01,
    "averageVolume20D": 4011326,
    "priceToBook": 2.36,
    "priceToCashFlow": 6.5,
    "returnOnEquity": 12.59,
    "returnOnAssets": 0.69,
    "day200MovingAvg": 140.80109,
    "close": 161.24,
    "currency": "CAD",
    "__typename": "Company",
}

CAPTURED_SHOP = {
    "symbol": "SHOP",
    "name": "Shopify Inc. Class A Subordinate Voting Shares",
    "price": 205.63,
    "priceChange": 2.26,
    "percentChange": 1.111275,
    "exchangeName": "Toronto Stock Exchange",
    "exchangeCode": "TSX",
    "volume": 1306027,
    "openPrice": 203.83,
    "dayHigh": 205.95,
    "dayLow": 199.6,
    "MarketCap": 248546787049,
    "peRatio": 99.81,
    "prevClose": 203.37,
    "dividendFrequency": None,
    "dividendYield": None,
    "dividendAmount": None,
    "beta": 2.452781,
    "eps": 1.42,
    "shareOutStanding": 1208708783,
    "vwap": 204.910701,
    "weeks52high": 253.1,
    "weeks52low": 129.01,
    "averageVolume20D": 2452497,
    "priceToBook": 15.09,
    "currency": "CAD",
    "__typename": "Company",
}

# TSXV issuer: peRatio is an empty string, eps is null (real HITI capture).
CAPTURED_HITI = {
    "symbol": "HITI",
    "name": "High Tide Inc.",
    "price": 3.38,
    "priceChange": -0.01,
    "percentChange": -0.294985,
    "exchangeName": "TSX Venture Exchange",
    "exchangeCode": "TSXV",
    "volume": 52117,
    "MarketCap": 297358573,
    "peRatio": "",
    "prevClose": 3.39,
    "beta": 1.046394,
    "eps": None,
    "currency": "CAD",
    "__typename": "Company",
}

CAPTURED_404 = {
    "errors": [
        {
            "message": 'Sorry, we couldn\'t find any results for "ZZZZ". Please try again.',
            "code": "404",
            "locations": [{"line": 2, "column": 3}],
            "path": ["getQuoteBySymbol"],
        }
    ],
    "data": {"getQuoteBySymbol": None},
}


def _replay(company_or_error: dict):
    """Monkeypatch helper: make requests.post return a captured body.

    Raw captures are stored as the inner company dict; wrap them in the
    GraphQL envelope the API actually returns. Error payloads already carry
    the ``errors`` envelope and pass through untouched.
    """

    class _FakeResponse:
        status_code = 200

        def json(self):
            if "errors" in company_or_error or "data" in company_or_error:
                return company_or_error
            return {"data": {"getQuoteBySymbol": company_or_error}}

    def _fake_post(url, json=None, timeout=None):
        return _FakeResponse()

    return _fake_post


def test_tmx_symbol_strips_to_suffix():
    assert tmx_symbol("TD.TO") == "TD"
    assert tmx_symbol("hitI.v") == "HITI"
    assert tmx_symbol("TD:CA") == "TD:CA"
    assert tmx_symbol("TD") == "TD"
    assert tmx_symbol("") is None
    assert tmx_symbol(None) is None
    assert tmx_symbol("X..") is None


def test_to_float_tolerates_tmx_empty_strings():
    assert _to_float("") is None
    assert _to_float(None) is None
    assert _to_float("12.34") == 12.34
    assert _to_float("not a number") is None


def test_get_price_parses_real_td_capture(monkeypatch):
    monkeypatch.setattr("data.tmx_provider.requests.post", _replay(CAPTURED_TD))
    result = TmxProvider().get_price("TD.TO")
    assert "error" not in result
    assert result["symbol"] == "TD.TO"  # requested symbol preserved, not the bare one
    assert result["price"] == 161.24
    assert result["volume"] == 2781994
    assert result["change"] == -0.18
    assert result["change_pct"] == -0.11151
    assert result["prev_close"] == 161.42
    assert result["day_high"] == 163.28
    assert result["day_low"] == 160.88
    assert result["exchange_code"] == "TSX"
    assert result["currency"] == "CAD"
    assert result["provider"] == "tmx"


def test_get_profile_parses_real_td_capture(monkeypatch):
    monkeypatch.setattr("data.tmx_provider.requests.post", _replay(CAPTURED_TD))
    result = TmxProvider().get_profile("TD")
    assert result["name"] == "Toronto-Dominion Bank (The)"
    assert result["exchange"] == "Toronto Stock Exchange"
    assert result["sector"] == "Finance"
    assert result["industry"] == "Banking"
    assert result["website"] == "https://www.td.com"
    assert result["employees"] == 101759
    assert result["market_cap"] == 265210081050
    assert result["shares_outstanding"] == 1644815685


def test_get_fundamentals_parses_real_td_capture(monkeypatch):
    monkeypatch.setattr("data.tmx_provider.requests.post", _replay(CAPTURED_TD))
    result = TmxProvider().get_fundamentals("TD.TO")
    assert result["pe_ratio"] == 19.26
    assert result["dividend_yield"] == 2.778  # percent, same unit as Finnhub/yfinance
    assert result["dividend_amount"] == 1.12
    assert result["dividend_frequency"] == "Quarterly"
    assert result["beta"] == 0.893892
    assert result["eps"] == 12.34
    assert result["weeks52high"] == 175.33
    assert result["weeks52low"] == 100.01
    assert result["price_to_book"] == 2.36
    assert result["return_on_equity"] == 12.59
    assert result["debt_to_equity"] == 4.21
    assert result["market_cap"] == 265210081050
    assert result["shares_outstanding"] == 1644815685
    assert result["source"] == "tmx"


def test_get_fundamentals_null_dividend_is_honest_absence(monkeypatch):
    """SHOP pays no dividend — nulls must be absent, not fabricated zeros."""
    monkeypatch.setattr("data.tmx_provider.requests.post", _replay(CAPTURED_SHOP))
    result = TmxProvider().get_fundamentals("SHOP.TO")
    assert "dividend_yield" not in result
    assert "dividend_amount" not in result
    assert result["pe_ratio"] == 99.81
    assert result["weeks52high"] == 253.1


def test_get_fundamentals_tsxv_empty_strings_are_omitted(monkeypatch):
    """TSXV issuers report peRatio='' and eps=null — must not crash nor fabricate."""
    monkeypatch.setattr("data.tmx_provider.requests.post", _replay(CAPTURED_HITI))
    result = TmxProvider().get_fundamentals("HITI.V")
    assert "pe_ratio" not in result
    assert "eps" not in result
    assert result["beta"] == 1.046394
    assert result["exchange_code"] == "TSXV"


def test_unknown_symbol_is_explicit_404_error(monkeypatch):
    monkeypatch.setattr("data.tmx_provider.requests.post", _replay(CAPTURED_404))
    result = TmxProvider().get_price("ZZZZ")
    assert "error" in result
    assert "tmx_not_found_404" in result["error"]
    assert "ZZZZ" in result["error"]


def test_http_failure_is_honest_error(monkeypatch):
    def _boom(url, json=None, timeout=None):
        raise OSError("connection refused")

    monkeypatch.setattr("data.tmx_provider.requests.post", _boom)
    result = TmxProvider().get_price("TD.TO")
    assert result["error"].startswith("tmx_http:")


def test_invalid_symbol_rejected_before_network(monkeypatch):
    def _fail_if_called(*a, **k):
        raise AssertionError("network must not be touched")

    monkeypatch.setattr("data.tmx_provider.requests.post", _fail_if_called)
    assert "error" in TmxProvider().get_price("")
    assert "error" in TmxProvider().get_price("BRK.B")  # US-style suffix unsupported


def test_datahub_registers_tmx_as_canadian_fallback():
    hub = DataHub(register_defaults=True)
    routes = {r["name"]: r for r in hub.list_routes()}
    tmx = routes["tmx"]
    assert tmx["priority"] == 25
    assert set(tmx["capabilities"]) == {"price", "market_price", "quote", "profile", "fundamentals"}
    assert tmx["configured"] is True  # keyless
    assert tmx["priority"] > routes["yfinance"]["priority"]
    # Canadian fallback: must never outrank the general-purpose price chain.
    assert tmx["priority"] > routes["twelve_data"]["priority"]


def test_datahub_usable_result_accepts_tmx_price():
    """A tmx-style price payload must satisfy the hub's usability gate."""
    hub = DataHub(register_defaults=True)
    price_payload = {"symbol": "TD.TO", "price": 161.24, "provider": "tmx"}
    assert hub._is_usable_result(price_payload, "price") is True
    assert hub._is_usable_result({"error": "tmx_not_found_404"}, "price") is False
