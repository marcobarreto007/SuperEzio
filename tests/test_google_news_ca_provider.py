"""Tests for GoogleNewsCAProvider — real captured response, no mocks.

The fixture tests/fixtures/google_news_ca_td_to.xml is the LIVE RSS feed
captured on 2026-08-23 from:

    GET https://news.google.com/rss/search
        ?q="TD.TO"&hl=en-CA&gl=CA&ceid=CA:en

(131,677 bytes, 100 items, HTTP 200). HTTP is patched to serve the exact
bytes Google returned — nothing is fabricated, and no network is needed
offline. The capture is real-world noisy (NFL "touchdown" headlines from
Sportsnet among the TSX coverage): tests assert the parse contract, not a
cleaned dataset.
"""

from __future__ import annotations

import importlib
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

import pytest

_FIXTURE = Path(__file__).parent / "fixtures" / "google_news_ca_td_to.xml"


class _FakeResponse:
    """Minimal ``requests.Response`` substitute serving captured bytes."""

    def __init__(self, status_code: int = 200, text: str = "") -> None:
        self.status_code = status_code
        self.text = text


def _make_provider():
    module = importlib.import_module("data.google_news_ca_provider")
    return module.GoogleNewsCAProvider()


@pytest.fixture()
def real_capture() -> str:
    return _FIXTURE.read_text(encoding="utf-8")


def test_fixture_is_valid_xml_with_100_items(real_capture: str) -> None:
    """Sanity check: the capture is the real Google RSS payload, unmodified."""
    root = ET.fromstring(real_capture)
    assert len(root.findall(".//item")) == 100
    assert root.find(".//title") is not None  # channel title present


def test_get_news_parses_real_google_response(real_capture: str) -> None:
    provider = _make_provider()
    with patch(
        "data.google_news_ca_provider.requests.get",
        return_value=_FakeResponse(status_code=200, text=real_capture),
    ):
        result = provider.get_news("TD.TO", limit=5)

    assert isinstance(result, list)
    assert len(result) == 5
    for item in result:
        assert item["provider"] == "google_news_ca"
        assert item["symbol"] == "TD.TO"
        assert item["title"]
        assert item["url"].startswith("https://news.google.com/")
        assert item["source"]  # outlet name (Sportsnet.ca, Moomoo, ...)
        assert item["published_date"]  # RFC-822 pubDate kept as-is
        assert item["snippet"]  # description stripped of HTML tags
        assert item["sentiment_label"] in {"POSITIVE", "NEGATIVE", "NEUTRAL"}
        assert -1.0 <= item["sentiment_score"] <= 1.0
    # The real en-CA capture contains TSX coverage (Moomoo TD earnings,
    # Globe and Mail TD report) — at least one title must mention TD.
    assert any("TD" in item["title"] for item in result)


def test_get_news_escaped_entities_are_decoded(real_capture: str) -> None:
    """ElementTree must decode the HTML entities Google escapes in titles."""
    provider = _make_provider()
    with patch(
        "data.google_news_ca_provider.requests.get",
        return_value=_FakeResponse(status_code=200, text=real_capture),
    ):
        result = provider.get_news("TD.TO", limit=50)
    assert isinstance(result, list)
    assert not any("&amp;" in item["title"] or "&lt;" in item["title"] for item in result)


def test_get_news_http_error_is_explicit(real_capture: str) -> None:
    provider = _make_provider()
    with patch(
        "data.google_news_ca_provider.requests.get",
        return_value=_FakeResponse(status_code=429, text=""),
    ):
        result = provider.get_news("TD.TO")

    assert isinstance(result, dict)
    assert result.get("error") == "gnews_http_429"


def test_get_news_parse_error_on_non_xml() -> None:
    provider = _make_provider()
    with patch(
        "data.google_news_ca_provider.requests.get",
        return_value=_FakeResponse(status_code=200, text="<html>not rss"),
    ):
        result = provider.get_news("TD.TO")

    assert isinstance(result, dict)
    assert result.get("error", "").startswith("gnews_parse")


def test_get_news_no_items_is_explicit() -> None:
    provider = _make_provider()
    with patch(
        "data.google_news_ca_provider.requests.get",
        return_value=_FakeResponse(
            status_code=200, text="<?xml version='1.0'?><rss><channel></channel></rss>"
        ),
    ):
        result = provider.get_news("TD.TO")

    assert isinstance(result, dict)
    assert result.get("error") == "gnews_no_items"


def test_get_news_invalid_symbol() -> None:
    provider = _make_provider()
    assert provider.get_news("  ").get("error") == "invalid_symbol"
