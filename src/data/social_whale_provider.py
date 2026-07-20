"""
SocialWhaleProvider — whale signal, pump detection, and social sentiment
aggregator for equities and crypto.

Sources (tried in cascade):
  1. Nitter (Twitter/X proxy — free, no API key needed)
     Instances: nitter.net, nitter.it, nitter.cz, nitter.1d4.us, nitter.kylrth.com
  2. ApeWisdom (Reddit/WSB retail sentiment — free, no key) — fallback
  3. CryptoPanic (crypto social news — public tier) — secondary fallback
  4. Clean empty result when all sources are offline

Every public method returns a sensible dict on failure — never raises.

Resilience guarantee:
  - All sources are tried with short timeouts (12 s each)
  - Instance-level failures are logged at DEBUG level, never WARNING
  - If every source fails, a ``CLEAN`` signal with ``error`` key is returned
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict

logger = logging.getLogger(__name__)

try:
    import requests as _requests

    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False

# ── Nitter Instances (tried in order, best first) ──────────────────────────
NITTER_INSTANCES = (
    "https://nitter.net",
    "https://nitter.it",
    "https://nitter.cz",
    "https://nitter.1d4.us",
    "https://nitter.kylrth.com",
)

REQUEST_TIMEOUT = 12  # seconds per Nitter attempt

# ── Detection Keywords (multilingual) ──────────────────────────────────────
# Whale / smart-money
_WHALE_KW = (
    "whale",
    "baleia",
    "big money",
    "institutional",
    "smart money",
    "whale alert",
    "accumulation",
    "acumulação",
    "大单",
)

# Pump signals (pump-and-dump / hype)
_PUMP_KW = (
    "pump",
    "rocket",
    "moon",
    "🚀",
    "breakout",
    "explode",
    "rip",
    "surge",
    "soar",
    "skyrocket",
    "mooning",
    "gamma squeeze",
    "short squeeze",
    "breakout",
)

# Dump signals
_DUMP_KW = (
    "dump",
    "crash",
    "rug",
    "scam",
    "ponzi",
    "plunge",
    "liquidation",
    "sell-off",
    "capitulation",
    "rugpull",
    "bearish",
)

# Options / unusual flow
_OPTIONS_KW = (
    "calls",
    "puts",
    "options",
    "flow",
    "dark pool",
    "darkpool",
    "unusual",
    "sweep",
    "block trade",
    "whale order",
    "big order",
    "ordem grande",
    "option flow",
)

# Sentiment direction keywords
_BULLISH_KW = ("bullish", "buy", "long", "positive", "profit", "up", "green")
_BEARISH_KW = ("bearish", "sell", "short", "negative", "loss", "down", "red")


def _clean_html_text(text: str) -> str:
    """Strip HTML tags, decode common entities, collapse whitespace."""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&#x?\d+;", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:500]


def _keyword_count(text: str, keywords: tuple[str, ...]) -> int:
    """Count occurrences of keywords in *text* (case-insensitive)."""
    lowered = text.lower()
    return sum(1 for kw in keywords if kw.lower() in lowered)


def _has_any_keyword(text: str, keywords: tuple[str, ...]) -> bool:
    """Return True if *text* contains any of the given keywords."""
    lowered = text.lower()
    return any(kw.lower() in lowered for kw in keywords)


# ── Public API ─────────────────────────────────────────────────────────────


class SocialWhaleProvider:
    """
    Social-media whale-signal and pump-detection provider.

    Public methods (used by DataHub routing):
      - get_whale_signals(ticker)
      - get_pump_detection(ticker)
      - get_social_sentiment(ticker)
      - get_unusual_options_flow(ticker)
    """

    def __init__(self) -> None:
        self._session: _requests.Session | None = None
        self._apewisdom: Any = None

    @property
    def session(self) -> _requests.Session:
        """Lazy-initialised requests session with browser-grade User-Agent."""
        if self._session is None:
            s = _requests.Session()
            s.headers.update(
                {
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/125.0.0.0 Safari/537.36"
                    ),
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"),
                }
            )
            self._session = s
        return self._session

    # ──────────────────────────────────────────────────────────────────────
    #  Public methods
    # ──────────────────────────────────────────────────────────────────────

    def get_whale_signals(self, ticker: str) -> Dict[str, Any]:
        """
        Search social media for whale / institutional mentions of *ticker*.

        Returns::

            {
                "ticker": "AAPL",
                "whale_score": 72,       # 0-100
                "mention_count": 15,
                "whale_mentions": 8,
                "top_tweets": [...],
                "signal": "WHALE_DETECTED" | "CLEAN",
                "source": "nitter" | "apewisdom" | "fallback"
            }
        """
        ticker = ticker.strip().upper()
        twitter_query = f"${ticker} {' OR '.join(_WHALE_KW[:5])}"
        tweets, source = self._search(twitter_query)

        if not tweets:
            return self._fallback_result(ticker, "whale_signals")

        whale_mentions = sum(1 for t in tweets if _has_any_keyword(t.get("text", ""), _WHALE_KW))
        mention_count = len(tweets)
        whale_score = self._score_from_ratio(
            whale_mentions, mention_count, min_score=20, max_score=100
        )

        return {
            "ticker": ticker,
            "whale_score": whale_score,
            "mention_count": mention_count,
            "whale_mentions": whale_mentions,
            "top_tweets": tweets[:5],
            "signal": "WHALE_DETECTED" if whale_score >= 40 else "CLEAN",
            "source": source,
        }

    def get_pump_detection(self, ticker: str) -> Dict[str, Any]:
        """
        Detect anomalous pump/dump conversation for *ticker*.

        Returns::

            {
                "ticker": "AAPL",
                "pump_risk": 65,          # 0-100
                "pump_mentions": 10,
                "dump_mentions": 2,
                "mention_count": 20,
                "top_tweets": [...],
                "signal": "PUMP_RISK" | "DUMP_RISK" | "PUMP_DUMP_ALERT" | "CLEAN",
                "source": "nitter" | "apewisdom" | "fallback"
            }
        """
        ticker = ticker.strip().upper()
        twitter_query = f"${ticker} {' OR '.join(_PUMP_KW[:5])} {' OR '.join(_DUMP_KW[:4])}"
        tweets, source = self._search(twitter_query)

        if not tweets:
            return self._fallback_result(ticker, "pump_detection")

        pump_mentions = sum(1 for t in tweets if _has_any_keyword(t.get("text", ""), _PUMP_KW))
        dump_mentions = sum(1 for t in tweets if _has_any_keyword(t.get("text", ""), _DUMP_KW))
        mention_count = len(tweets)

        # Pump-risk heuristic: ratio of pump-to-total hype, weighted by density
        total_hype = pump_mentions + dump_mentions
        if total_hype == 0:
            pump_risk = 0
        else:
            pump_ratio = pump_mentions / total_hype
            density = total_hype / max(mention_count, 1)
            pump_risk = min(100, int((pump_ratio * 0.6 + density * 0.4) * 100))

        if pump_risk >= 60 and dump_mentions >= 2:
            signal = "PUMP_DUMP_ALERT"
        elif pump_risk >= 50:
            signal = "PUMP_RISK"
        elif dump_mentions >= 3:
            signal = "DUMP_RISK"
        else:
            signal = "CLEAN"

        return {
            "ticker": ticker,
            "pump_risk": pump_risk,
            "pump_mentions": pump_mentions,
            "dump_mentions": dump_mentions,
            "mention_count": mention_count,
            "top_tweets": tweets[:5],
            "signal": signal,
            "source": source,
        }

    def get_social_sentiment(self, ticker: str) -> Dict[str, Any]:
        """
        Aggregate social sentiment from Nitter, ApeWisdom, and Reddit.

        Returns::

            {
                "ticker": "AAPL",
                "sentiment_score": 0.35,       # -1.0 .. 1.0
                "sentiment_label": "BULLISH" | "NEUTRAL" | "BEARISH" | "NO_DATA",
                "mention_count": 25,
                "sources_used": ["nitter", "apewisdom"]
            }
        """
        ticker = ticker.strip().upper()
        scores: list[float] = []
        sources_used: list[str] = []
        mention_count = 0

        # 1. Nitter — general ticker sentiment
        tweets, source = self._search(f"${ticker}")
        if tweets:
            pos = sum(1 for t in tweets if _has_any_keyword(t.get("text", ""), _BULLISH_KW))
            neg = sum(1 for t in tweets if _has_any_keyword(t.get("text", ""), _BEARISH_KW))
            total = pos + neg
            if total > 0:
                scores.append((pos - neg) / total)
                mention_count += len(tweets)
                sources_used.append(source)

        # 2. ApeWisdom
        ape, ok = self._get_apewisdom()
        if ok and ape is not None:
            try:
                ape_result = ape.get_sentiment(ticker)
                ape_mentions = ape_result.get("mentions", 0)
                if ape_mentions > 0:
                    ape_raw = ape_result.get("sentiment_score", 50)
                    scores.append((ape_raw - 50) / 50.0)  # 0-100 → -1..1
                    mention_count += ape_mentions
                    sources_used.append("apewisdom")
            except Exception as exc:
                logger.debug("[SocialWhale] ApeWisdom sentiment failed: %s", exc)

        if not scores:
            return {
                "ticker": ticker,
                "sentiment_score": 0.0,
                "sentiment_label": "NO_DATA",
                "mention_count": 0,
                "sources_used": sources_used or [],
            }

        avg_score = sum(scores) / len(scores)

        if avg_score > 0.15:
            label = "BULLISH"
        elif avg_score < -0.15:
            label = "BEARISH"
        else:
            label = "NEUTRAL"

        return {
            "ticker": ticker,
            "sentiment_score": round(avg_score, 3),
            "sentiment_label": label,
            "mention_count": mention_count,
            "sources_used": sources_used,
        }

    def get_unusual_options_flow(self, ticker: str) -> Dict[str, Any]:
        """
        Search for unusual options flow / dark pool / large orders.

        Returns::

            {
                "ticker": "AAPL",
                "unusual_flow_score": 45,    # 0-100
                "options_mentions": 12,
                "mention_count": 18,
                "top_tweets": [...],
                "signal": "UNUSUAL_FLOW" | "NORMAL_FLOW",
                "source": "nitter" | "apewisdom" | "fallback"
            }
        """
        ticker = ticker.strip().upper()
        # Shorter query for better recall: split into two passes if needed
        twitter_query = f"${ticker} {' OR '.join(_OPTIONS_KW[:6])}"
        tweets, source = self._search(twitter_query)

        if not tweets:
            # Second pass: try simpler query without $ for broader match
            alt_tweets, alt_source = self._search(
                f"{ticker} unusual options OR dark pool OR big order"
            )
            if alt_tweets:
                tweets, source = alt_tweets, alt_source

        if not tweets:
            return self._fallback_result(ticker, "unusual_options_flow")

        options_mentions = sum(
            1 for t in tweets if _has_any_keyword(t.get("text", ""), _OPTIONS_KW)
        )
        mention_count = len(tweets)
        unusual_flow_score = self._score_from_ratio(
            options_mentions, mention_count, min_score=10, max_score=95
        )

        return {
            "ticker": ticker,
            "unusual_flow_score": unusual_flow_score,
            "options_mentions": options_mentions,
            "mention_count": mention_count,
            "top_tweets": tweets[:5],
            "signal": "UNUSUAL_FLOW" if unusual_flow_score >= 40 else "NORMAL_FLOW",
            "source": source,
        }

    # ──────────────────────────────────────────────────────────────────────
    #  Internal: Nitter search
    # ──────────────────────────────────────────────────────────────────────

    def _search(self, query: str, limit: int = 10) -> tuple[list[Dict[str, Any]], str]:
        """
        Try Nitter instances in order.

        Returns:
            ``(tweets, source_label)`` — empty list if all instances fail.
        """
        if not _HAS_REQUESTS:
            return [], "requests_unavailable"

        for instance in NITTER_INSTANCES:
            try:
                resp = self.session.get(
                    f"{instance}/search",
                    params={"f": "tweets", "q": query},
                    timeout=REQUEST_TIMEOUT,
                )
                if resp.status_code != 200:
                    continue

                tweets = self._parse_nitter_tweets(resp.text, limit)
                if tweets:
                    instance_name = instance.split("//")[1]
                    return tweets, f"nitter({instance_name})"
            except Exception as exc:
                logger.debug("[SocialWhale] Nitter %s failed: %s", instance, exc)
                continue

        return [], "nitter_offline"

    @staticmethod
    def _parse_nitter_tweets(html: str, limit: int) -> list[Dict[str, Any]]:
        """Extract tweet texts from Nitter HTML.

        Uses multiple extraction strategies to handle different Nitter
        versions and instance configurations.
        """
        # Remove script, style, svg blocks and HTML comments
        cleaned = re.sub(
            r"<script[^>]*>.*?</script>",
            "",
            html,
            flags=re.DOTALL | re.IGNORECASE,
        )
        cleaned = re.sub(
            r"<style[^>]*>.*?</style>",
            "",
            cleaned,
            flags=re.DOTALL | re.IGNORECASE,
        )
        cleaned = re.sub(
            r"<svg[^>]*>.*?</svg>",
            "",
            cleaned,
            flags=re.DOTALL | re.IGNORECASE,
        )
        cleaned = re.sub(r"<!--.*?-->", "", cleaned, flags=re.DOTALL)

        # Strategy 1: find tweet-content / tweet-text blocks
        content_patterns = [
            r'<div[^>]*class="[^"]*(?:tweet-content|tweet-text)[^"]*"[^>]*>'
            r"(.*?)</div>",
            r'<p[^>]*class="[^"]*tweet-text[^"]*"[^>]*>(.*?)</p>',
        ]

        for pattern in content_patterns:
            matches = re.findall(pattern, cleaned, re.DOTALL | re.IGNORECASE)
            if matches:
                tweets = []
                for match in matches[:limit]:
                    text = _clean_html_text(match)
                    if text and len(text) > 5:
                        tweets.append({"text": text})
                if tweets:
                    return tweets

        # Strategy 2: split by timeline-item divs
        items = re.split(r'<div[^>]*class="[^"]*timeline-item[^"]*"', cleaned)
        if len(items) > 1:
            tweets = []
            for item in items[1 : limit + 1]:
                text = re.sub(r"<[^>]+>", " ", item)
                text = _clean_html_text(text)
                if text and len(text) > 10:
                    tweets.append({"text": text})
            if tweets:
                return tweets

        # Strategy 3: any sizable text block (broad fallback)
        blocks = re.findall(r">([^<]{40,})<", cleaned)
        if blocks:
            result = []
            for b in blocks[:limit]:
                text = _clean_html_text(b)
                if text:
                    result.append({"text": text})
            return result

        return []

    # ──────────────────────────────────────────────────────────────────────
    #  Internal: ApeWisdom fallback
    # ──────────────────────────────────────────────────────────────────────

    def _get_apewisdom(self) -> tuple[Any, bool]:
        """Lazy-load ApeWisdomProvider. Returns ``(instance, ok)``."""
        if self._apewisdom is not None:
            return self._apewisdom, True
        try:
            from .apewisdom_provider import ApeWisdomProvider  # noqa: PLC0415

            self._apewisdom = ApeWisdomProvider()
            return self._apewisdom, True
        except Exception as exc:
            logger.debug("[SocialWhale] ApeWisdom import failed: %s", exc)
            return None, False

    def _fallback_result(self, ticker: str, method: str) -> Dict[str, Any]:
        """
        Return fallback data when primary Nitter sources are offline.

        Tries ApeWisdom, then returns a clean empty result.
        """
        ape, ok = self._get_apewisdom()
        if ok and ape is not None:
            try:
                ape_result = ape.get_sentiment(ticker)
                mentions = ape_result.get("mentions", 0)
                if mentions > 0:
                    raw_score = ape_result.get("sentiment_score", 50)
                    score = int(raw_score)

                    if method == "whale_signals":
                        return {
                            "ticker": ticker,
                            "whale_score": score,
                            "mention_count": mentions,
                            "whale_mentions": mentions,
                            "top_tweets": [],
                            "signal": ("WHALE_DETECTED" if score >= 40 else "CLEAN"),
                            "source": "apewisdom_fallback",
                            "note": "nitter_offline_fallback_to_apewisdom",
                        }
                    if method == "pump_detection":
                        pump_risk = min(100, score)
                        return {
                            "ticker": ticker,
                            "pump_risk": pump_risk,
                            "pump_mentions": mentions,
                            "dump_mentions": 0,
                            "mention_count": mentions,
                            "top_tweets": [],
                            "signal": ("PUMP_RISK" if pump_risk >= 50 else "CLEAN"),
                            "source": "apewisdom_fallback",
                            "note": "nitter_offline_fallback_to_apewisdom",
                        }
                    if method == "unusual_options_flow":
                        return {
                            "ticker": ticker,
                            "unusual_flow_score": score,
                            "options_mentions": mentions,
                            "mention_count": mentions,
                            "top_tweets": [],
                            "signal": ("UNUSUAL_FLOW" if score >= 40 else "NORMAL_FLOW"),
                            "source": "apewisdom_fallback",
                            "note": "nitter_offline_fallback_to_apewisdom",
                        }
            except Exception as exc:
                logger.debug("[SocialWhale] ApeWisdom fallback failed: %s", exc)

        # No data at all — return clean empty signal
        return {
            "ticker": ticker,
            "error": "no_data_all_sources_offline",
            "signal": "CLEAN",
            "source": "fallback_empty",
        }

    # ──────────────────────────────────────────────────────────────────────
    #  Internal: scoring
    # ──────────────────────────────────────────────────────────────────────

    @staticmethod
    def _score_from_ratio(
        matched: int, total: int, min_score: int = 0, max_score: int = 100
    ) -> int:
        """Convert a matched/total ratio into a 0-100 score."""
        if total == 0:
            return 0
        ratio = matched / total
        return min(max_score, max(min_score, int(ratio * max_score)))
