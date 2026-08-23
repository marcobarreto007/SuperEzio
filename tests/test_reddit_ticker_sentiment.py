"""Tests for RedditTickerSentiment (anonymous Reddit RSS ticker sentiment).

The XML fixtures are REAL responses captured live on 2026-08-23 from
https://www.reddit.com/r/{sub}/search.rss (not fabricated): one feed with 3
matching posts (r/CanadianInvestor, q=RY.TO) and one feed with 0 entries
(r/Wealthsimple_Trade, q=RY.TO).

Unit tests never touch the network; the single live test is opt-in
(SUPEREZIO_REDDIT_LIVE=1) and skips on 429/403 rate limiting.
"""

from __future__ import annotations

import os
import socket
from pathlib import Path

import pytest

from data.reddit_provider import (
    BEAR_KEYWORDS,
    BULL_KEYWORDS,
    RedditTickerSentiment,
    _strip_html,
)

FIXTURES = Path(__file__).parent / "fixtures"
RSS_CI_RY = FIXTURES / "reddit_search_rss_CanadianInvestor_RY_TO_top_month.xml"
RSS_WST_RY = FIXTURES / "reddit_search_rss_Wealthsimple_Trade_RY_TO_top_month.xml"


def _fixture_fetch(self, *, subreddit, query, limit, sort, time_filter):
    """Offline stand-in for _fetch_subreddit backed by the real captured feeds."""
    del query, limit, sort, time_filter
    if subreddit == "Wealthsimple_Trade":
        return RedditTickerSentiment._parse_feed(RSS_WST_RY.read_bytes())
    return RedditTickerSentiment._parse_feed(RSS_CI_RY.read_bytes())


@pytest.fixture
def offline_provider(monkeypatch):
    monkeypatch.setattr(RedditTickerSentiment, "_fetch_subreddit", _fixture_fetch)
    return RedditTickerSentiment(delay_s=0.0, subreddits=["CanadianInvestor"])


# ── Real-fixture parsing ────────────────────────────────────────────────────


def test_parse_feed_extracts_real_entries() -> None:
    entries = RedditTickerSentiment._parse_feed(RSS_CI_RY.read_bytes())
    assert len(entries) == 3
    titles = [entry["title"] for entry in entries]
    assert "RY rally before earnings?" in titles
    assert all(entry["url"].startswith("https://www.reddit.com/") for entry in entries)
    assert all(entry["id"].startswith("t3_") for entry in entries)
    assert all(entry["published_utc"] for entry in entries)
    assert any("RY" in entry["content"] for entry in entries)  # real body text extracted


def test_empty_real_feed_parses_to_zero_entries() -> None:
    entries = RedditTickerSentiment._parse_feed(RSS_WST_RY.read_bytes())
    assert entries == []


# ── Signal from real captures, no network ───────────────────────────────────


def test_signal_mentions_with_and_without_suffix(offline_provider) -> None:
    signal = offline_provider.get_signal("RY.TO")
    assert signal["post_count"] == 3
    assert signal["qualified_count"] == 3
    # Reddit tokenizes "RY.TO" and matches bare "RY" posts (real behavior).
    assert signal["mention_with_suffix"] == 0
    assert signal["mention_without_suffix"] == 3
    assert signal["method"] == "reddit_rss_search"
    assert signal["reason"] == ""


def test_signal_keyword_polarity_deterministic(offline_provider) -> None:
    signal = offline_provider.get_signal("RY.TO")
    # Real fixture, date-sorted desc: bull ("rally"), bear ("sell my bank
    # stocks"), tie ("buy and sell") -> mean 0.0 -> NEUTRAL_SOCIAL.
    assert [post["sentiment_score"] for post in signal["top_posts"]] == [1, -1, 0]
    assert signal["sentiment_score"] == 0.0
    assert signal["signal_label"] == "NEUTRAL_SOCIAL"


def test_signal_rss_has_no_ups_or_comments(offline_provider) -> None:
    signal = offline_provider.get_signal("RY.TO")
    # RSS carries no score/num_comments fields: NO_DATA, never invented.
    assert signal["ups_total"] is None
    assert signal["comments_total"] is None
    assert all(post["score"] is None and post["comments"] is None for post in signal["top_posts"])


def test_signal_no_mentions_is_explicit_no_data(offline_provider) -> None:
    signal = offline_provider.get_signal("ZZZ.TO")
    assert signal["post_count"] == 0
    assert signal["signal_label"] == "NO_DATA"
    assert signal["reason"] == "no_mentions_found"


def test_signal_empty_real_feed_is_no_data(monkeypatch) -> None:
    monkeypatch.setattr(RedditTickerSentiment, "_fetch_subreddit", _fixture_fetch)
    provider = RedditTickerSentiment(delay_s=0.0, subreddits=["Wealthsimple_Trade"])
    signal = provider.get_signal("RY.TO")
    assert signal["post_count"] == 0
    assert signal["signal_label"] == "NO_DATA"
    assert signal["reason"] == "no_mentions_found"
    assert signal["provider_errors"] == []


def test_disabled_provider_returns_reddit_disabled(monkeypatch) -> None:
    monkeypatch.setenv("SUPEREZIO_REDDIT_ENABLED", "0")
    provider = RedditTickerSentiment(delay_s=0.0, subreddits=["CanadianInvestor"])
    signal = provider.get_signal("RY.TO")
    assert signal["signal_label"] == "NO_DATA"
    assert signal["reason"] == "reddit_disabled"


def test_rate_limited_fetch_raises_and_signal_reports_no_data(
    monkeypatch, offline_provider
) -> None:
    def boom(self, *, subreddit, query, limit, sort, time_filter):
        del self, subreddit, query, limit, sort, time_filter
        raise RuntimeError("rate_limited")

    monkeypatch.setattr(RedditTickerSentiment, "_fetch_subreddit", boom)
    signal = offline_provider.get_signal("RY.TO")
    assert signal["post_count"] == 0
    assert signal["signal_label"] == "NO_DATA"
    assert signal["reason"] == "rate_limited"
    assert "rate_limited" in signal["provider_errors"][0]


# ── Keyword sentiment primitives ────────────────────────────────────────────


def test_keyword_polarity_bull_bear_and_tie() -> None:
    assert RedditTickerSentiment._keyword_polarity("bullish rally breakout") == 1
    assert RedditTickerSentiment._keyword_polarity("bearish crash and dump") == -1
    assert RedditTickerSentiment._keyword_polarity("buy and sell at the same time") == 0
    assert RedditTickerSentiment._keyword_polarity("no sentiment words here") == 0
    assert RedditTickerSentiment._keyword_polarity("") == 0


def test_keyword_lists_are_non_empty() -> None:
    assert BULL_KEYWORDS and BEAR_KEYWORDS
    assert not set(BULL_KEYWORDS) & set(BEAR_KEYWORDS)


def test_strip_html_removes_tags() -> None:
    html = '<!-- SC_OFF --><div class="md"><p>RY is <strong>up</strong></p></div>'
    text = _strip_html(html)
    assert "RY" in text
    assert "<" not in text and ">" not in text


def test_ticker_variants() -> None:
    assert RedditTickerSentiment._ticker_variants("ry.to") == ("RY", "RY.TO")
    assert RedditTickerSentiment._ticker_variants("AAPL") == ("AAPL", "AAPL")
    assert RedditTickerSentiment._ticker_variants("shop.to") == ("SHOP", "SHOP.TO")


# ── Live test (opt-in; skips on rate limit, never asserts fabricated data) ──


def _no_network() -> bool:
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=2)
        return False
    except OSError:
        return True


@pytest.mark.skipif(
    os.getenv("SUPEREZIO_REDDIT_LIVE") != "1",
    reason="live Reddit test is opt-in: set SUPEREZIO_REDDIT_LIVE=1",
)
@pytest.mark.skipif(_no_network(), reason="No network connection")
def test_live_rss_search_skips_on_rate_limit() -> None:
    """One real anonymous call to the working endpoint (RSS search).

    old.reddit.com search.json is dead for anonymous access (302 -> /login
    since 2026), so the live probe targets the official search.rss endpoint.
    Skips on 429/403 instead of failing the suite.
    """
    provider = RedditTickerSentiment(delay_s=0.0, subreddits=["CanadianInvestor"])
    try:
        entries = provider._fetch_subreddit(
            subreddit="CanadianInvestor",
            query="RY.TO",
            limit=5,
            sort="new",
            time_filter="week",
        )
    except RuntimeError as exc:
        pytest.skip(f"reddit rate-limited/blocked: {exc}")
    assert isinstance(entries, list)  # real response parsed; may legitimately be empty
