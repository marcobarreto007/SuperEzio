"""Tests for YahooConversationProvider — real captured response, no mocks.

The fixture tests/fixtures/yahoo_search_td.json is the LIVE response
captured on 2026-08-23 from:

    GET https://query1.finance.yahoo.com/v1/finance/search
        ?q=TD&newsCount=10&quotesCount=0

(9,240 bytes, 10 news rows, HTTP 200). Every news row in the capture
carries TD in relatedTickers. HTTP is patched to serve the exact bytes
Yahoo returned — nothing is fabricated, and no network is needed offline.
"""

from __future__ import annotations

import datetime
import importlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest

_FIXTURE = Path(__file__).parent / "fixtures" / "yahoo_search_td.json"


class _FakeResponse:
    """Minimal ``requests.Response`` substitute serving captured bytes."""

    def __init__(self, status_code: int = 200, body: str = "{}") -> None:
        self.status_code = status_code
        self._body = body

    def json(self) -> dict:
        return json.loads(self._body)


def _make_provider():
    module = importlib.import_module("data.yahoo_conversation_provider")
    return module.YahooConversationProvider()


@pytest.fixture()
def real_capture() -> str:
    return _FIXTURE.read_text(encoding="utf-8")


def test_base_ticker_strips_exchange_suffix() -> None:
    provider = _make_provider()
    assert provider._base_ticker("TD.TO") == "TD"
    assert provider._base_ticker("RY.V") == "RY"
    assert provider._base_ticker("AAPL") == "AAPL"
    assert provider._base_ticker("  ") == ""


def test_related_matches_accepts_suffix_variants() -> None:
    provider = _make_provider()
    assert provider._related_matches(["TD", "3772.T"], "TD.TO", "TD")
    assert provider._related_matches(["TUST.TO", "TD"], "TD.TO", "TD")
    assert not provider._related_matches(["TGT", "NVDA"], "TD.TO", "TD")
    assert not provider._related_matches(None, "TD.TO", "TD")


def test_get_news_parses_real_capture_and_filters_by_related_tickers(
    real_capture: str,
) -> None:
    """Every returned item must be TD-related (real filter behavior)."""
    provider = _make_provider()
    with patch(
        "data.yahoo_conversation_provider.requests.get",
        return_value=_FakeResponse(status_code=200, body=real_capture),
    ):
        result = provider.get_news("TD.TO", limit=5)

    assert isinstance(result, list)
    assert len(result) == 5
    for item in result:
        assert item["provider"] == "yahoo_conversation"
        assert item["symbol"] == "TD.TO"
        assert item["title"]
        assert item["url"].startswith("https://")
        assert item["source"]  # publisher name
        assert item["published_date"]  # ISO from providerPublishTime
        datetime.datetime.fromisoformat(item["published_date"])
        assert item["sentiment_label"] in {"POSITIVE", "NEGATIVE", "NEUTRAL"}
        assert -1.0 <= item["sentiment_score"] <= 1.0
    # The real capture is TD-heavy: press releases from CNW Group / Business Wire.
    assert any("TD" in item["title"] for item in result)


def test_get_news_drops_irrelevant_rows_from_real_capture(real_capture: str) -> None:
    """A ticker absent from the capture's relatedTickers must yield an error."""
    provider = _make_provider()
    with patch(
        "data.yahoo_conversation_provider.requests.get",
        return_value=_FakeResponse(status_code=200, body=real_capture),
    ):
        result = provider.get_news("ZZZ.TO")

    assert isinstance(result, dict)
    assert result.get("error") == "yahoo_no_relevant_news"


def test_get_news_http_error_is_explicit(real_capture: str) -> None:
    provider = _make_provider()
    with patch(
        "data.yahoo_conversation_provider.requests.get",
        return_value=_FakeResponse(status_code=429, body="{}"),
    ):
        result = provider.get_news("TD.TO")

    assert isinstance(result, dict)
    assert result.get("error") == "yahoo_http_429"


def test_get_news_invalid_symbol() -> None:
    provider = _make_provider()
    assert provider.get_news("  ").get("error") == "invalid_symbol"


def test_get_sentiment_summary_from_real_capture(real_capture: str) -> None:
    provider = _make_provider()
    with patch(
        "data.yahoo_conversation_provider.requests.get",
        return_value=_FakeResponse(status_code=200, body=real_capture),
    ):
        result = provider.get_sentiment_summary("TD.TO", limit=10)

    assert result["provider"] == "yahoo_conversation"
    assert result["news_count"] > 0
    assert result["top_headline"]
    assert result["sentiment_label"] in {"BULLISH", "BEARISH", "NEUTRAL"}
    assert -1.0 <= result["sentiment_score"] <= 1.0
    # Average of the per-item scores must match the real captured news.
    with patch(
        "data.yahoo_conversation_provider.requests.get",
        return_value=_FakeResponse(status_code=200, body=real_capture),
    ):
        news = provider.get_news("TD.TO", limit=10)
    expected = round(sum(float(n["sentiment_score"]) for n in news) / len(news), 2)
    assert result["sentiment_score"] == expected


def test_get_sentiment_summary_no_data_on_failure(real_capture: str) -> None:
    provider = _make_provider()
    with patch(
        "data.yahoo_conversation_provider.requests.get",
        return_value=_FakeResponse(status_code=503, body="{}"),
    ):
        result = provider.get_sentiment_summary("TD.TO")

    assert result["sentiment_label"] == "NO_DATA"
    assert result["news_count"] == 0
