"""
TMX Money provider — official Toronto Stock Exchange site, free and keyless.

Data source: the internal GraphQL API of money.tmx.com
(``https://app-money.tmx.com/graphql``), operation ``getQuoteBySymbol``.
Verified live 2026-08-23 against TD, RY, SHOP, CSU (TSX) and HITI (TSXV):
one POST per symbol, no API key, no cookies, no Origin header required
(~0.5 s per call; 5 rapid calls in sequence all returned 200).

Symbol mapping: the site URL accepts ``TD.TO`` but the API resolves bare
symbols (``TD`` / ``TD:CA``) to the TSX/TSXV listing; ``TD.TO`` returns an
explicit GraphQL 404. This provider therefore strips a ``.TO``/``.V`` suffix
before querying and reports ``exchange_code`` (TSX/TSXV) so consumers can
see exactly which listing was resolved (e.g. bare ``AAPL`` resolves to the
TSX-listed Apple CDR, not the Nasdaq security).

Honest failure: unknown symbols, network errors, and non-numeric fields
(TSXV issuers often report ``peRatio`` as ``""`` or ``eps`` as null) become
explicit ``{"error": ...}`` dicts — never silent zeros or fabricated data.
"""

from __future__ import annotations

from typing import Any, Dict

import requests

_TMX_GRAPHQL_URL = "https://app-money.tmx.com/graphql"
_QUOTE_OPERATION = "getQuoteBySymbol"

# Field selection mirrors the site's own quote page query (captured from the
# app bundle 2026-08-23). The GraphQL endpoint returns the requested fields
# verbatim; requesting a subset we do not parse keeps the payload small.
_QUOTE_FIELDS = """
    symbol
    name
    price
    priceChange
    percentChange
    exchangeName
    exchangeCode
    sector
    industry
    volume
    openPrice
    dayHigh
    dayLow
    MarketCap
    MarketCapAllClasses
    peRatio
    prevClose
    dividendFrequency
    dividendYield
    dividendAmount
    dividendCurrency
    beta
    eps
    exDividendDate
    longDescription
    website
    email
    phoneNumber
    fullAddress
    employees
    shareOutStanding
    totalDebtToEquity
    vwap
    dividendPayDate
    weeks52high
    weeks52low
    averageVolume10D
    averageVolume20D
    averageVolume50D
    priceToBook
    priceToCashFlow
    returnOnEquity
    returnOnAssets
    day200MovingAvg
    close
    currency
    __typename
"""

_QUERY = (
    "query getQuoteBySymbol($symbol: String, $locale: String) {\n"
    "  getQuoteBySymbol(symbol: $symbol, locale: $locale) {\n"
    f"{_QUOTE_FIELDS}\n"
    "  }\n"
    "}"
)


def tmx_symbol(symbol: str | None) -> str | None:
    """Map a user ticker to the bare symbol the TMX API resolves.

    ``TD.TO`` -> ``TD``, ``HITI.V`` -> ``HITI``, ``TD:CA``/``TD`` pass
    through. Anything else (empty, US suffix) returns None — the provider
    is for Canadian listings on the official exchange site.
    """
    if not symbol:
        return None
    raw = symbol.strip().upper()
    if raw.endswith(".TO"):
        raw = raw[:-3]
    elif raw.endswith(".V"):
        raw = raw[:-2]
    if not raw or not raw.replace("-", "").replace(":", "").isalnum():
        return None
    return raw


def _to_float(value: Any) -> float | None:
    """Robust numeric cast; TMX reports some fields as ``""`` (e.g. TSXV peRatio)."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class TmxProvider:
    """Real-time TSX/TSXV quotes through the official TMX Money GraphQL API."""

    name = "tmx"

    def __init__(self, timeout: float = 20.0) -> None:
        self.timeout = timeout

    # ── internal ──────────────────────────────────────────────────────────
    def _fetch(self, symbol: str) -> Dict[str, Any]:
        """Query getQuoteBySymbol; returns the raw company dict or an error."""
        tmx_sym = tmx_symbol(symbol)
        if tmx_sym is None:
            return {"error": "invalid_symbol"}
        payload = {
            "operationName": _QUOTE_OPERATION,
            "variables": {"symbol": tmx_sym, "locale": "en"},
            "query": _QUERY,
        }
        try:
            response = requests.post(_TMX_GRAPHQL_URL, json=payload, timeout=self.timeout)
        except (requests.RequestException, OSError) as exc:
            return {"error": f"tmx_http: {exc}"}
        if response.status_code != 200:
            return {"error": f"tmx_http_status_{response.status_code}"}
        try:
            body = response.json()
        except ValueError:
            return {"error": "tmx_bad_json"}

        errors = body.get("errors")
        if errors:
            message = errors[0].get("message", "unknown") if isinstance(errors, list) else "unknown"
            code = errors[0].get("code", "") if isinstance(errors, list) else ""
            return {"error": f"tmx_not_found_{code}: {message}"}

        company = (body.get("data") or {}).get(_QUOTE_OPERATION)
        if not isinstance(company, dict) or not company.get("symbol"):
            return {"error": "tmx_no_data"}
        return company

    def _base(self, symbol: str, company: Dict[str, Any]) -> Dict[str, Any]:
        """Shared envelope fields for every public method."""
        return {
            "symbol": symbol,
            "tmx_symbol": company.get("symbol"),
            "name": company.get("name"),
            "exchange": company.get("exchangeName"),
            "exchange_code": company.get("exchangeCode"),
            "currency": company.get("currency"),
            "source": self.name,
            "provider": self.name,
        }

    # ── public contract (DataHub) ─────────────────────────────────────────
    def get_price(self, symbol: str, **_: Any) -> Dict[str, Any]:
        """Real-time price snapshot: last price, volume, change, day range."""
        company = self._fetch(symbol)
        if "error" in company:
            return company
        price = _to_float(company.get("price"))
        if price is None or price <= 0:
            return {"error": "tmx_no_price", "symbol": symbol}
        return {
            **self._base(symbol, company),
            "price": price,
            "volume": _to_float(company.get("volume")),
            "change": _to_float(company.get("priceChange")),
            "change_pct": _to_float(company.get("percentChange")),
            "prev_close": _to_float(company.get("prevClose")),
            "open": _to_float(company.get("openPrice")),
            "day_high": _to_float(company.get("dayHigh")),
            "day_low": _to_float(company.get("dayLow")),
            "vwap": _to_float(company.get("vwap")),
        }

    def get_profile(self, symbol: str, **_: Any) -> Dict[str, Any]:
        """Company profile: name, sector/industry, description, website, size."""
        company = self._fetch(symbol)
        if "error" in company:
            return company
        name = company.get("name")
        if not name:
            return {"error": "tmx_no_profile", "symbol": symbol}
        return {
            **self._base(symbol, company),
            "sector": company.get("sector"),
            "industry": company.get("industry"),
            "description": company.get("longDescription"),
            "website": company.get("website"),
            "email": company.get("email"),
            "phone": company.get("phoneNumber"),
            "address": company.get("fullAddress"),
            "employees": int(company["employees"])
            if _to_float(company.get("employees")) is not None
            else None,
            "market_cap": int(company["MarketCap"])
            if _to_float(company.get("MarketCap")) is not None
            else None,
            "shares_outstanding": int(company["shareOutStanding"])
            if _to_float(company.get("shareOutStanding")) is not None
            else None,
        }

    def get_fundamentals(self, symbol: str, **_: Any) -> Dict[str, Any]:
        """Key ratios: P/E, dividend yield, beta, EPS, 52-week range, ROE/ROA."""
        company = self._fetch(symbol)
        if "error" in company:
            return company
        envelope: Dict[str, Any] = self._base(symbol, company)
        payload: Dict[str, Any] = dict(envelope)
        mappings = (
            ("pe_ratio", "peRatio"),
            ("forward_pe", None),  # not exposed by the TMX API — honest absence
            ("beta", "beta"),
            ("eps", "eps"),
            ("dividend_yield", "dividendYield"),  # percent, same unit as Finnhub/yfinance
            ("dividend_amount", "dividendAmount"),
            ("price_to_book", "priceToBook"),
            ("price_to_cash_flow", "priceToCashFlow"),
            ("return_on_equity", "returnOnEquity"),
            ("return_on_assets", "returnOnAssets"),
            ("debt_to_equity", "totalDebtToEquity"),
            ("weeks52high", "weeks52high"),
            ("weeks52low", "weeks52low"),
            ("avg_daily_volume_shares", "averageVolume20D"),
            ("day200_moving_avg", "day200MovingAvg"),
        )
        for target, source in mappings:
            if source is None:
                continue
            value = _to_float(company.get(source))
            if value is not None:
                payload[target] = value
        # Non-numeric fields pass through verbatim (dates, frequency, sector).
        for target, source in (
            ("sector", "sector"),
            ("industry", "industry"),
            ("dividend_frequency", "dividendFrequency"),
            ("dividend_currency", "dividendCurrency"),
            ("ex_dividend_date", "exDividendDate"),
            ("dividend_pay_date", "dividendPayDate"),
        ):
            if company.get(source):
                payload[target] = company[source]
        market_cap = _to_float(company.get("MarketCap"))
        if market_cap is not None:
            payload["market_cap"] = int(market_cap)
        shares = _to_float(company.get("shareOutStanding"))
        if shares is not None:
            payload["shares_outstanding"] = int(shares)
        # Envelope-only (no metric keys) means the API returned no usable
        # numbers — say so explicitly instead of presenting an empty payload.
        if len(payload) <= len(envelope):
            return {"error": "tmx_no_fundamentals", "symbol": symbol}
        return payload
