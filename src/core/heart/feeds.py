"""Feeds de evento sem histórico recuperável — a Peça 0 só os grava crus."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FeedSpec:
    feed_id: str
    url: str
    recoverable: bool = False


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
    ),
)

_BY_ID = {feed.feed_id: feed for feed in NON_RECOVERABLE_FEEDS}


def feed_by_id(feed_id: str) -> FeedSpec:
    try:
        return _BY_ID[feed_id]
    except KeyError as exc:
        raise KeyError(f"unknown heart feed: {feed_id}") from exc
