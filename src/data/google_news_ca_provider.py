"""
Google News RSS provider — Canadian-locale ticker news (keyless, scraping OK).

Google News RSS search is a plain, scraping-friendly endpoint (the operator
authorized scraping; this is the same free feed NewsScout already leans on):

    GET https://news.google.com/rss/search
        ?q="SYMBOL"&hl=en-CA&gl=CA&ceid=CA:en

The en-CA / gl=CA locale biases results to Canadian outlets (The Globe and
Mail, Toronto Star, Financial Post, MarketBeat CA), which is the TSX-news
gap in the hub: NewsAPI 429s and NewsScout's generic Google News feed is
hard-coded to hl=en-US with a "+stock+finance" suffix.

The ticker is quoted in the query to reduce token noise — live test
2026-08-23: bare q=TD.TO returns NFL "touchdown" headlines, q="TD.TO"
returns real TSX coverage (Moomoo TD earnings, Globe and Mail TD fraud
report). Common-word tickers (TD) can still show residual noise; that is a
known limit of the free feed, not a parse bug.

Parsing uses xml.etree (stdlib) — Google serves valid XML and the regex
parser in news_feed mis-handles escaped HTML entities in titles.
Every failure returns an explicit {"error": ...}.

Item schema matches NewsScout (title, snippet, source, url,
published_date, sentiment_score, sentiment_label) — sentiment is computed
by the shared news_feed._make_item helper.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any

import requests

from .news_feed import _make_item

_TAG_RE = re.compile(r"<[^>]+>")


def _strip_tags(text: str) -> str:
    return _TAG_RE.sub("", text or "").strip()


class GoogleNewsCAProvider:
    """Canadian-locale ticker news via Google News RSS search."""

    def __init__(self) -> None:
        self.base_url = "https://news.google.com/rss/search"
        self.timeout = 10
        self.headers = {"User-Agent": "Mozilla/5.0"}

    def get_news(
        self,
        symbol: str,
        *,
        limit: int = 5,
        **_: Any,
    ) -> list[dict[str, Any]] | dict[str, Any]:
        """Ticker news from the en-CA Google News RSS feed.

        Returns NewsScout-schema items (with sentiment fields), or
        {"error": ...} on any failure.
        """
        ticker = (symbol or "").strip().upper()
        if not ticker:
            return {"error": "invalid_symbol"}

        params = {"q": f'"{ticker}"', "hl": "en-CA", "gl": "CA", "ceid": "CA:en"}
        try:
            response = requests.get(
                self.base_url,
                params=params,
                headers=self.headers,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            return {"error": f"gnews_http: {exc}", "symbol": symbol}
        if response.status_code != 200:
            return {"error": f"gnews_http_{response.status_code}", "symbol": symbol}

        try:
            root = ET.fromstring(response.text)
            entries = root.findall(".//item")
        except ET.ParseError as exc:
            return {"error": f"gnews_parse: {exc}", "symbol": symbol}
        if not entries:
            return {"error": "gnews_no_items", "symbol": symbol}

        items: list[dict[str, Any]] = []
        for entry in entries[: max(1, limit)]:
            title = _strip_tags(entry.findtext("title") or "")
            if not title:
                continue
            description = _strip_tags(entry.findtext("description") or "")
            link = (entry.findtext("link") or "").strip()
            source_el = entry.find("source")
            source_name = (
                (source_el.text or "Google News").strip()
                if source_el is not None
                else "Google News"
            )
            item = _make_item(
                title=title,
                snippet=description,
                url=link,
                source=source_name,
                published_date=(entry.findtext("pubDate") or "").strip(),
            )
            item["provider"] = "google_news_ca"
            item["symbol"] = symbol
            items.append(item)

        if not items:
            return {"error": "gnews_no_items", "symbol": symbol}
        return items[: max(1, limit)]
