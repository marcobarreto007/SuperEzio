"""
NewsAPI Provider — Real-time financial news with sentiment analysis.

Uses NewsAPI.org v2 for headlines with rich metadata (author, urlToImage,
publishedAt). Sentiment computed via TextBlob with keyword-lexicon fallback.

Rate limit: 100 requests/day (free tier), ~0.014 req/s sustained.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

try:
    import requests as _requests

    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False

try:
    from textblob import TextBlob as _TextBlob

    _HAS_TEXTBLOB = True
except ImportError:
    _HAS_TEXTBLOB = False

# ── Sentiment lexicon (backup when TextBlob unavailable) ────────────────────

_POS_WORDS = frozenset(
    {
        "surges",
        "rallies",
        "gains",
        "rises",
        "beats",
        "record",
        "growth",
        "profit",
        "upgrade",
        "buy",
        "bullish",
        "strong",
        "soars",
        "optimism",
        "dividend",
        "outperforms",
        "milestone",
        "opportunity",
        "positive",
        "breakthrough",
        "partnership",
        "expansion",
        "approval",
        "launch",
        "revenue",
        "earnings",
        "beat",
        "upside",
        "momentum",
        "recovery",
    }
)
_NEG_WORDS = frozenset(
    {
        "falls",
        "drops",
        "plunges",
        "misses",
        "loss",
        "cut",
        "sell",
        "bearish",
        "weak",
        "decline",
        "lawsuit",
        "fraud",
        "risk",
        "downgrade",
        "concern",
        "crisis",
        "crash",
        "layoffs",
        "warning",
        "debt",
        "recall",
        "probe",
        "bankruptcy",
        "delisting",
        "default",
        "restructuring",
        "write-down",
        "impairment",
        "sanction",
        "fine",
        "investigation",
        "suspension",
        "halt",
        "deficit",
        "insolvency",
    }
)


def _sentiment(text: str) -> tuple[float, str]:
    """Return (score -1..1, label POSITIVE/NEUTRAL/NEGATIVE)."""
    clean = re.sub(r"<[^>]+>|&#\d+;|&\w+;", "", text)
    if _HAS_TEXTBLOB:
        score = round(_TextBlob(clean).sentiment.polarity, 2)
    else:
        words = set(clean.lower().split())
        pos = len(words & _POS_WORDS)
        neg = len(words & _NEG_WORDS)
        total = pos + neg
        score = round((pos - neg) / total, 2) if total else 0.0
    label = "POSITIVE" if score > 0.1 else ("NEGATIVE" if score < -0.1 else "NEUTRAL")
    return score, label


class NewsAPIProvider:
    """Standalone NewsAPI v2 provider for financial news."""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.getenv("NEWSAPI_KEY")
        self._healthy = bool(self.api_key)

    @property
    def healthy(self) -> bool:
        return self._healthy

    def get_news(self, query: str, limit: int = 8) -> List[Dict[str, Any]]:
        """Fetch news articles for a query.

        Returns list of articles with sentiment score, source, URL, and
        publication date.
        """
        if not self.api_key or not _HAS_REQUESTS:
            return []

        try:
            params: dict[str, Any] = {
                "q": f"{query} stock OR finance OR market",
                "apiKey": self.api_key,
                "language": "en",
                "sortBy": "relevancy",
                "pageSize": min(limit, 20),
            }
            resp = _requests.get(
                "https://newsapi.org/v2/everything",
                params=params,
                timeout=10,
            )
            if resp.status_code != 200:
                error_msg = resp.json().get("message", resp.text) if resp.text else "unknown"
                logger.warning("[NewsAPI] HTTP %s: %s", resp.status_code, error_msg)
                return []

            data = resp.json()
            if data.get("status") != "ok":
                return []

            articles: list[dict] = []
            for art in data.get("articles", []):
                title = art.get("title") or ""
                desc = art.get("description") or ""
                content = art.get("content") or ""
                full_text = f"{title}. {desc}. {content}"

                score, label = _sentiment(full_text)
                articles.append(
                    {
                        "title": title,
                        "snippet": (desc or content)[:300],
                        "url": art.get("url", ""),
                        "source": art.get("source", {}).get("name", "NewsAPI"),
                        "published_at": art.get("publishedAt", ""),
                        "image_url": art.get("urlToImage"),
                        "sentiment_score": score,
                        "sentiment_label": label,
                    }
                )

            return articles

        except Exception as exc:
            logger.warning("[NewsAPI] fetch failed: %s", exc)
            return []

    def get_sentiment_summary(self, symbol: str) -> Dict[str, Any]:
        """Sentiment summary for a ticker symbol."""
        ticker_clean = re.sub(r"\.(TO|V|SA|to|v|sa)$", "", symbol)
        query = f"{ticker_clean}"
        news = self.get_news(query, limit=10)

        if not news:
            return {
                "symbol": symbol,
                "sentiment_score": 0.0,
                "sentiment_label": "NO_DATA",
                "news_count": 0,
                "top_headline": "",
                "source": "newsapi",
            }

        scores = [n["sentiment_score"] for n in news]
        avg_score = round(sum(scores) / len(scores), 2)

        if avg_score > 0.2:
            label = "BULLISH"
        elif avg_score < -0.2:
            label = "BEARISH"
        elif avg_score > 0.05:
            label = "SLIGHTLY_BULLISH"
        elif avg_score < -0.05:
            label = "SLIGHTLY_BEARISH"
        else:
            label = "NEUTRAL"

        return {
            "symbol": symbol,
            "sentiment_score": avg_score,
            "sentiment_label": label,
            "news_count": len(news),
            "top_headline": news[0].get("title", ""),
            "top_headline_url": news[0].get("url", ""),
            "top_headline_source": news[0].get("source", ""),
            "source": "newsapi",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def get_market_sentiment(self) -> Dict[str, Any]:
        """Broad market sentiment from top headlines."""
        news = self.get_news("market S&P500 NASDAQ TSX", limit=15)
        if not news:
            return {"sentiment_label": "NO_DATA", "source": "newsapi"}

        scores = [n["sentiment_score"] for n in news]
        avg = round(sum(scores) / len(scores), 2)

        pos_count = sum(1 for s in scores if s > 0.1)
        neg_count = sum(1 for s in scores if s < -0.1)

        return {
            "sentiment_score": avg,
            "sentiment_label": "BULLISH" if avg > 0.1 else ("BEARISH" if avg < -0.1 else "NEUTRAL"),
            "positive_articles": pos_count,
            "negative_articles": neg_count,
            "total_articles": len(news),
            "top_headlines": [n["title"] for n in news[:5]],
            "source": "newsapi",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
