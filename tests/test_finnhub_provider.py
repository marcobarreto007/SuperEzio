"""Tests G & H — FinnhubProvider contract tests with mocked HTTP.

These tests pin down two things the market scan candidate gate relies on:

G. Successful enrichment shape
    - ``get_price`` returns ``{symbol, price, change, change_pct, prev_close,
      volume?, source="finnhub"}``.
    - ``get_profile`` returns ``{symbol, name, exchange, currency,
      market_cap, source="finnhub"}``.
    - ``get_short_term_catalyst`` returns a dict with ``catalyst``,
      ``invalidation``, ``event_date`` when an earnings event is in window,
      or ``{"error": "no_catalyst_in_window"}`` when not.

H. Failure modes must NOT produce empty payloads
    - Network timeout / RequestException → ``{"error": ...}``.
    - HTTP 500 → ``{"error": "http_500"}``.
    - Empty quote (``c == 0``) → ``{"error": "no_quote"}`` (so the gate
      rejects honestly instead of letting a zero-price candidate through).

The provider must also fail loudly when ``FINNHUB_API_KEY`` is missing —
no silent ``None`` returns, no zombie provider that breaks downstream.

All HTTP is mocked. No real API key required.
"""

from __future__ import annotations

import importlib
from unittest.mock import patch
from typing import Any, Dict, Optional

import pytest


@pytest.fixture(autouse=True)
def _fast_finnhub_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FINNHUB_MIN_INTERVAL_SEC", "0")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeResponse:
    """Minimal ``requests.Response`` substitute."""

    def __init__(
        self,
        *,
        status_code: int = 200,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    @property
    def content(self) -> bytes:
        import json as _json
        return _json.dumps(self._payload).encode("utf-8")

    def json(self) -> Dict[str, Any]:
        return self._payload


def _make_provider():
    """Construct FinnhubProvider with a dummy key (no env requirement)."""
    module = importlib.import_module("data.finnhub_provider")
    return module.FinnhubProvider(api_key="test-key-not-real")


# ---------------------------------------------------------------------------
# Test G — Successful mocked enrichment
# ---------------------------------------------------------------------------


def test_get_price_returns_finnhub_shape_when_quote_succeeds() -> None:
    provider = _make_provider()

    quote_payload = {
        "c": 195.50,
        "d": 1.25,
        "dp": 0.64,
        "pc": 194.25,
    }
    metric_payload = {"metric": {"10DayAverageTradingVolume": 50_000_000.0}}

    def fake_get(url: str, *_, **__):
        if "/quote" in url:
            return _FakeResponse(status_code=200, payload=quote_payload)
        if "/stock/metric" in url:
            return _FakeResponse(status_code=200, payload=metric_payload)
        return _FakeResponse(status_code=404, payload={})

    with patch("data.finnhub_provider.requests.get", side_effect=fake_get):
        result = provider.get_price("AAPL")

    assert result.get("source") == "finnhub"
    assert result.get("symbol") == "AAPL"
    assert result.get("price") == 195.50
    assert result.get("change") == 1.25
    assert result.get("change_pct") == 0.64
    assert result.get("prev_close") == 194.25
    assert result.get("volume") == 50_000_000.0
    assert "error" not in result


def test_get_profile_returns_normalized_market_cap_in_units() -> None:
    """Finnhub returns marketCap in millions; provider must scale up."""
    provider = _make_provider()

    profile_payload = {
        "name": "Apple Inc",
        "exchange": "NASDAQ",
        "currency": "USD",
        "marketCapitalization": 3_000_000.0,  # 3,000,000 million == 3T
        "country": "US",
        "ipo": "1980-12-12",
        "shareOutstanding": 15_000.0,
    }

    with patch(
        "data.finnhub_provider.requests.get",
        return_value=_FakeResponse(status_code=200, payload=profile_payload),
    ):
        result = provider.get_profile("AAPL")

    assert result.get("source") == "finnhub"
    assert result.get("name") == "Apple Inc"
    assert result.get("exchange") == "NASDAQ"
    assert result.get("currency") == "USD"
    assert result.get("market_cap") == 3_000_000 * 1_000_000
    assert "error" not in result


def test_short_term_catalyst_returns_event_when_earnings_in_window() -> None:
    provider = _make_provider()

    calendar_payload = {
        "earningsCalendar": [
            {
                "date": "2026-05-25",
                "symbol": "AAPL",
                "epsEstimate": 1.42,
                "revenueEstimate": 90_000_000_000,
                "hour": "amc",
            }
        ]
    }

    with patch(
        "data.finnhub_provider.requests.get",
        return_value=_FakeResponse(status_code=200, payload=calendar_payload),
    ):
        result = provider.get_short_term_catalyst("AAPL")

    assert result.get("source") == "finnhub"
    assert result.get("event_date") == "2026-05-25"
    assert "earnings release" in (result.get("catalyst") or "")
    assert "after market close" in (result.get("catalyst") or "")
    assert result.get("invalidation"), "Invalidation must be set for candidate gate."
    assert "error" not in result


def test_short_term_catalyst_returns_no_catalyst_when_empty_window() -> None:
    """When no earnings event sits inside the 14-day window, the provider
    must say so honestly so the candidate gate can reject the ticker for
    ``missing_short_term_thesis`` instead of fabricating a catalyst."""
    provider = _make_provider()

    with patch(
        "data.finnhub_provider.requests.get",
        return_value=_FakeResponse(status_code=200, payload={"earningsCalendar": []}),
    ):
        result = provider.get_short_term_catalyst("AAPL")

    assert result.get("error") == "no_catalyst_in_window"


# ---------------------------------------------------------------------------
# Test H — Failure paths must still return structured errors
# ---------------------------------------------------------------------------


def test_get_price_returns_error_on_zero_quote() -> None:
    """A zero ``c`` field is Finnhub's signal for unknown/inactive ticker.
    The provider must convert that into a structured error, never silently
    pass a zero-price candidate through."""
    provider = _make_provider()

    with patch(
        "data.finnhub_provider.requests.get",
        return_value=_FakeResponse(status_code=200, payload={"c": 0}),
    ):
        result = provider.get_price("ZZZZ")

    assert result.get("error") == "no_quote"
    assert result.get("symbol") == "ZZZZ"


def test_get_price_returns_http_error_on_429() -> None:
    provider = _make_provider()

    with patch(
        "data.finnhub_provider.requests.get",
        return_value=_FakeResponse(status_code=429, payload={}),
    ):
        result = provider.get_price("AAPL")

    assert result.get("error") == "http_429"


def test_get_price_returns_error_on_network_exception() -> None:
    provider = _make_provider()

    with patch(
        "data.finnhub_provider.requests.get",
        side_effect=TimeoutError("connection timed out"),
    ):
        result = provider.get_price("AAPL")

    assert "error" in result
    assert "timed out" in result["error"].lower()


def test_get_profile_returns_http_error_on_5xx() -> None:
    provider = _make_provider()

    with patch(
        "data.finnhub_provider.requests.get",
        return_value=_FakeResponse(status_code=500, payload={}),
    ):
        result = provider.get_profile("AAPL")

    assert result.get("error") == "http_500"


def test_get_profile_returns_error_when_payload_is_empty() -> None:
    """Finnhub responds 200 with ``{}`` for unknown tickers; the gate must
    not treat that as a valid profile."""
    provider = _make_provider()

    with patch(
        "data.finnhub_provider.requests.get",
        return_value=_FakeResponse(status_code=200, payload={}),
    ):
        result = provider.get_profile("ZZZZ")

    assert result.get("error") == "no_profile"


def test_short_term_catalyst_returns_http_error_on_5xx() -> None:
    provider = _make_provider()

    with patch(
        "data.finnhub_provider.requests.get",
        return_value=_FakeResponse(status_code=503, payload={}),
    ):
        result = provider.get_short_term_catalyst("AAPL")

    assert result.get("error") == "http_503"


# ---------------------------------------------------------------------------
# Absent-key safety net
# ---------------------------------------------------------------------------


def test_provider_raises_when_api_key_absent(monkeypatch) -> None:
    """A missing FINNHUB_API_KEY must surface as a loud RuntimeError at
    construction, never as a silent ``None`` instance downstream."""
    module = importlib.import_module("data.finnhub_provider")

    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)

    raised: Exception | None = None
    try:
        module.FinnhubProvider()
    except RuntimeError as exc:
        raised = exc

    assert raised is not None, "FinnhubProvider must reject construction without a key."
    assert "FINNHUB_API_KEY" in str(raised)
