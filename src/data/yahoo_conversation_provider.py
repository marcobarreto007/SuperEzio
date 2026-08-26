"""
Yahoo Finance conversation API provider — keyless ticker news + sentiment.

Uses the only Yahoo endpoint that still answers without crumb/cookie
authentication since 2026-08 (v7 /quote and v10 /quoteSummary now return
HTTP 401 "Invalid Crumb"): the v1 "conversation" search endpoint.

    GET https://query1.finance.yahoo.com/v1/finance/search
        ?q=<BASE_TICKER>&newsCount=N&quotesCount=0

The endpoint returns both matching quotes and news rows. Each news row
carries a ``relatedTickers`` field; only rows whose related tickers include
the requested base ticker are kept. Without this filter a TD.TO query
returns generic headlines (observed live 2026-08-23: "Target admits...",
"Giroud scores..." — news padded by Yahoo, unrelated to the ticker). With
the base-ticker query (TD, not TD.TO) the same endpoint returns relevant
TD Bank press releases from CNW Group, Business Wire and Zacks.

Covers TSX/TSXV (.TO/.V) — Yahoo indexes Canadian tickers, so this fills
the .TO news/sentiment gap in the hub (NewsAPI 429s; Finnhub key invalid).

No API key, no quota. Risk: undocumented endpoint; Yahoo may gate it
without notice (as it did v7/v10). Every failure returns an explicit
{"error": ...} so the DataHub falls through to the next route.

Item schema matches NewsScout (title, snippet, source, url,
published_date, sentiment_score, sentiment_label) — sentiment is computed
by the shared news_feed._make_item helper.
"""

from __future__ import annotations

import datetime
from typing import Any

import requests

from .news_feed import _make_item

_SENTIMENT_LABELS = ("BULLISH", "BEARISH", "NEUTRAL")


class YahooConversationProvider:
    """Ticker news + sentiment from the Yahoo Finance v1 search endpoint."""

    def __init__(self) -> None:
        self.base_url = "https://query1.finance.yahoo.com/v1/finance/search"
        self.timeout = 10
        self.headers = {"User-Agent": "Mozilla/5.0"}

    @staticmethod
    def _base_ticker(symbol: str) -> str:
        """Strip exchange suffix for the Yahoo query: TD.TO -> TD, BRK.B -> BRK."""
        raw = (symbol or "").strip().upper()
        if not raw:
            return ""
        return raw.split(".")[0]

    @classmethod
    def _related_matches(cls, related: Any, symbol: str, base: str) -> bool:
        """True when a news row's relatedTickers mention the requested ticker."""
        if not isinstance(related, list):
            return False
        candidates = {base, symbol.upper(), base + ".TO", base + ".V", base.replace(".", "-")}
        return any(str(r).upper() in candidates for r in related)

    def get_news(
        self,
        symbol: str,
        *,
        limit: int = 5,
        **_: Any,
    ) -> list[dict[str, Any]] | dict[str, Any]:
        """Relevant ticker news via the Yahoo v1 search endpoint.

        Returns NewsScout-schema items (with sentiment fields) filtered by
        Yahoo's relatedTickers, or {"error": ...} on any failure.
        """
        base = self._base_ticker(symbol)
        if not base:
            return {"error": "invalid_symbol"}

        try:
            response = requests.get(
                self.base_url,
                params={"q": base, "newsCount": max(1, limit), "quotesCount": 0},
                headers=self.headers,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            return {"error": f"yahoo_http: {exc}", "symbol": symbol}
        if response.status_code != 200:
            return {"error": f"yahoo_http_{response.status_code}", "symbol": symbol}

        data = response.json() or {}
        rows = data.get("news") or []
        if not isinstance(rows, list) or not rows:
            return {"error": "yahoo_no_news", "symbol": symbol}

        items: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            title = row.get("title") or ""
            if not title.strip():
                continue
            if not self._related_matches(row.get("relatedTickers"), symbol, base):
                continue
            published_ts = row.get("providerPublishTime")
            published = ""
            if isinstance(published_ts, (int, float)) and published_ts:
                published = datetime.datetime.fromtimestamp(
                    float(published_ts), tz=datetime.UTC
                ).isoformat()
            item = _make_item(
                title=title,
                snippet=title,
                url=row.get("link") or "",
                source=row.get("publisher") or "Yahoo Finance",
                published_date=published,
            )
            item["provider"] = "yahoo_conversation"
            item["symbol"] = symbol
            items.append(item)

        if not items:
            return {"error": "yahoo_no_relevant_news", "symbol": symbol}
        return items[: max(1, limit)]

    def get_sentiment_summary(self, symbol: str, *, limit: int = 10) -> dict[str, Any]:
        """News-driven sentiment for a ticker (same contract as NewsScout).

        Returns {symbol, sentiment_score, sentiment_label, news_count,
        top_headline, provider} or a NO_DATA payload when no news is found.
        """
        news = self.get_news(symbol, limit=limit)
        if isinstance(news, dict) or not news:
            return {
                "symbol": symbol,
                "sentiment_score": 0,
                "sentiment_label": "NO_DATA",
                "news_count": 0,
                "top_headline": "",
                "provider": "yahoo_conversation",
            }
        avg = round(sum(float(n.get("sentiment_score") or 0.0) for n in news) / len(news), 2)
        label = "BULLISH" if avg > 0.15 else ("BEARISH" if avg < -0.15 else "NEUTRAL")
        return {
            "symbol": symbol,
            "sentiment_score": avg,
            "sentiment_label": label,
            "news_count": len(news),
            "top_headline": news[0]["title"],
            "provider": "yahoo_conversation",
        }
