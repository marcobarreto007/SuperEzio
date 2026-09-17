"""Feeds de evento sem histórico recuperável — a Peça 0 só os grava crus."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FeedSpec:
    """Wire feed polled by Peça 0 and stored raw in ``raw/YYYY/MM/DD/<feed_id>.jsonl``.

    Some endpoints return syntactically valid RSS with zero ``<item>`` elements when
    the channel id is invalid or requires a paid subscription — see ``notes`` on
    individual feeds rather than treating an empty body as success.
    """

    feed_id: str
    url: str
    recoverable: bool = False
    notes: str | None = None
    poll_read_timeout_s: float | None = None


NON_RECOVERABLE_FEEDS: tuple[FeedSpec, ...] = (
    FeedSpec(
        "prnewswire",
        "https://www.prnewswire.com/rss/all-news-releases-list.rss",
    ),
    FeedSpec(
        "cnw",
        "https://www.newswire.ca/rss/news-releases-list.rss",
    ),
    FeedSpec(
        "businesswire_ma",
        "https://feed.businesswire.com/rss/home/?rss=merger-acquisition",
        notes=(
            "As of 2026-09-17 the endpoint returns RSS whose channel description is "
            "'RSS channel ID is not available' with zero <item> elements. No free "
            "public channel-id URL was confirmed; feed is retained until a valid id "
            "is configured."
        ),
    ),
    FeedSpec(
        "newsfile",
        "https://feeds.newsfilecorp.com/global/Last25Stories",
    ),
    FeedSpec(
        "globenewswire",
        "https://www.globenewswire.com/RssFeed/subjectcode/22-Earnings%20Releases%20And%20Operating%20Results/feedTitle/GlobeNewswire-Earnings",
    ),
    FeedSpec(
        "nasdaq_rssoutbound",
        "https://www.nasdaq.com/feed/rssoutbound",
        poll_read_timeout_s=20.0,
        notes=(
            "Nasdaq outbound RSS is slow; capped at poll_read_timeout_s so one feed "
            "cannot hold the whole ingest cycle for 60 s."
        ),
    ),
)

_BY_ID = {feed.feed_id: feed for feed in NON_RECOVERABLE_FEEDS}


def feed_by_id(feed_id: str) -> FeedSpec:
    try:
        return _BY_ID[feed_id]
    except KeyError as exc:
        raise KeyError(f"unknown heart feed: {feed_id}") from exc
