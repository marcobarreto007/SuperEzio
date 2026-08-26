"""
ApeWisdom retail sentiment tracker.

Provides Reddit/WSB retail sentiment data: mentions, ranking, and a
sentiment score (0-100) for trending stocks.  Uses the public ApeWisdom
API at https://apewisdom.io/api/v1.0/ with the FREE tier (no key
required).

Resilience guarantee: every public method returns a sensible value on
failure (empty list or dict) — never raises.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

try:
    import requests as _requests

    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False


class ApeWisdomProvider:
    """Retail sentiment data from ApeWisdom (Reddit/WSB)."""

    BASE_URL = "https://apewisdom.io/api/v1.0"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or "FREE"
        self._session: _requests.Session | None = None

    @property
    def session(self) -> _requests.Session:
        if self._session is None:
            s = _requests.Session()
            s.headers.update({"User-Agent": "SuperEzio/1.0 market-research"})
            self._session = s
        return self._session

    # ── public API ──────────────────────────────────────────────────────

    def get_trending_stocks(self, page: int = 1) -> list[dict[str, Any]]:
        """Return top trending stocks from Reddit/WSB.

        Each item::

            {"ticker": "GME", "mentions": 1523, "sentiment_score": 76,
             "rank": 1, "source": "apewisdom"}
        """
        if not _HAS_REQUESTS:
            return []

        try:
            resp = self.session.get(
                f"{self.BASE_URL}/filter/all-stocks",
                params={"page": page, "apikey": self.api_key},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            results = data if isinstance(data, list) else data.get("results", [])
            return [
                {
                    "ticker": item.get("ticker", item.get("symbol", "")),
                    "mentions": int(item.get("mentions", 0)),
                    "sentiment_score": int(
                        item.get("sentiment_score") or item.get("sentiment") or 50
                    ),
                    "rank": int(item.get("rank", 0)),
                    "source": "apewisdom",
                }
                for item in results
                if item.get("ticker") or item.get("symbol")
            ]
        except Exception as exc:  # noqa: BLE001 — catch amplo deliberado: garantia de resiliência do provider (nunca levanta; degrada para lista vazia com warning)
            logger.warning("[ApeWisdom] get_trending_stocks failed: %s", exc)
            return []

    def get_sentiment(self, ticker: str) -> dict[str, Any]:
        """Return retail sentiment for a single ticker.

        Looks up *ticker* in the trending list since ApeWisdom does not
        expose a per-ticker endpoint.
        """
        stocks = self.get_trending_stocks(page=1)
        target = ticker.strip().upper()

        for stock in stocks:
            if stock.get("ticker", "").upper() == target:
                return {
                    **stock,
                    "ticker": target,
                }

        return {
            "ticker": target,
            "mentions": 0,
            "sentiment_score": 50,
            "rank": 0,
            "source": "apewisdom",
            "note": "ticker_not_found_in_trending",
        }

    def get_retail_buzz(self) -> dict[str, Any]:
        """Return a summary of the overall retail market buzz."""
        stocks = self.get_trending_stocks(page=1)

        if not stocks:
            return {
                "buzz_score": 0,
                "top_stocks": [],
                "total_tracked": 0,
                "source": "apewisdom",
            }

        scores = [
            s["sentiment_score"]
            for s in stocks
            if isinstance(s.get("sentiment_score"), (int, float))
        ]
        buzz = sum(scores) / len(scores) if scores else 50

        return {
            "buzz_score": round(buzz, 1),
            "top_stocks": stocks[:10],
            "total_tracked": len(stocks),
            "source": "apewisdom",
        }
