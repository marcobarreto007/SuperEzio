from __future__ import annotations

import math
import os
import re
from typing import Any
from urllib.parse import urlparse

import requests

try:
    from textblob import TextBlob
except ImportError:  # pragma: no cover - dependency is present in runtime requirements
    TextBlob = None


DEFAULT_SUBREDDITS = (
    "investing",
    "stocks",
    "SecurityAnalysis",
    "ValueInvesting",
    "CanadianInvestor",
    "Bogleheads",
    "StockMarket",
)

SUBREDDIT_WEIGHTS = {
    "securityanalysis": 1.35,
    "valueinvesting": 1.25,
    "investing": 1.15,
    "bogleheads": 1.10,
    "canadianinvestor": 1.05,
    "stocks": 1.00,
    "stockmarket": 0.90,
    "wallstreetbets": 0.45,
}

HYPE_PATTERNS = (
    r"\b100x\b",
    r"\b1000x\b",
    r"\bmoon\b",
    r"\bto the moon\b",
    r"\byolo\b",
    r"\bsqueeze\b",
    r"\bshort squeeze\b",
    r"\bpump\b",
    r"\bguaranteed\b",
    r"\bsure profit\b",
    r"\bfree money\b",
    r"\binsider leak\b",
    r"\bcan't lose\b",
)

# Keywords to detect whale activity, pumps, dumps, and large order discussions.
# Combined with ticker symbol in Phase 2 search expansion.
WHALE_KEYWORDS = (
    "whale",
    "pump",
    "dump",
    "rocket",
    "moon",
    "bag",
    "yolo",
    "calls",
    "puts",
    "DD",
)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _parse_subreddits(value: str | None) -> list[str]:
    if not value:
        return list(DEFAULT_SUBREDDITS)
    return [item.strip().strip("/").removeprefix("r/") for item in value.split(",") if item.strip()]


def _clean_query(ticker: str) -> str:
    value = ticker.upper().strip()
    base = re.sub(r"\.(SA|TO|V|NE|CN)$", "", value)
    if base != value:
        return f'"{value}"'
    return value


def _match_terms(query: str) -> list[str]:
    return [
        term.lower() for term in re.findall(r"[A-Za-z0-9.]{2,12}", query) if term.lower() != "or"
    ]


class RedditPulse:
    """
    Low-volume Reddit signal provider.

    Uses Pushshift.io (primary) -> old.reddit.com (fallback) -> ApeWisdom (last resort).
    This module treats Reddit as social evidence, never as verified financial fact.
    """

    def __init__(
        self,
        subreddits: list[str] | None = None,
        timeout_s: float | None = None,
        min_score: int | None = None,
        min_comments: int | None = None,
        min_upvote_ratio: float | None = None,
    ) -> None:
        self.enabled = os.getenv("SUPEREZIO_REDDIT_ENABLED", "1").lower() not in {
            "0",
            "false",
            "no",
        }
        self.subreddits = subreddits or _parse_subreddits(os.getenv("SUPEREZIO_REDDIT_SUBREDDITS"))
        self.timeout_s = (
            timeout_s if timeout_s is not None else _env_float("SUPEREZIO_REDDIT_TIMEOUT_S", 6.0)
        )
        self.min_score = (
            min_score if min_score is not None else _env_int("SUPEREZIO_REDDIT_MIN_SCORE", 5)
        )
        self.min_comments = (
            min_comments
            if min_comments is not None
            else _env_int("SUPEREZIO_REDDIT_MIN_COMMENTS", 2)
        )
        self.min_upvote_ratio = (
            min_upvote_ratio
            if min_upvote_ratio is not None
            else _env_float("SUPEREZIO_REDDIT_MIN_UPVOTE_RATIO", 0.65)
        )
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": os.getenv(
                    "SUPEREZIO_REDDIT_USER_AGENT",
                    "SuperEzio/4.0 market-research",
                )
            }
        )
        # Tracks source failures across subreddits for ApeWisdom fallback
        self._source_errors: list[str] = []

    def get_signal(
        self,
        ticker: str,
        *,
        limit: int = 8,
        per_subreddit: int = 8,
        sort: str = "top",
        time_filter: str = "month",
    ) -> dict[str, Any]:
        if not self.enabled:
            return {
                "symbol": ticker,
                "signal_label": "NO_DATA",
                "post_count": 0,
                "qualified_count": 0,
                "reason": "reddit_disabled",
            }

        query = _clean_query(ticker)
        posts: list[dict[str, Any]] = []
        errors: list[str] = []
        self._source_errors = []

        for subreddit in self.subreddits:
            try:
                posts.extend(
                    self._fetch_subreddit(
                        subreddit=subreddit,
                        query=query,
                        limit=per_subreddit,
                        sort=sort,
                        time_filter=time_filter,
                    )
                )
            except Exception as exc:
                errors.append(f"r/{subreddit}: {exc}")

        qualified = self._dedupe_and_rank(posts)
        top_posts = qualified[:limit]
        avg_sentiment = self._average_sentiment(top_posts)

        # If all Reddit sources failed, fallback to ApeWisdom.
        # _source_errors is populated by _cascade_fetch when Pushshift AND
        # old.reddit both fail for a subreddit.
        if not top_posts and (errors or self._source_errors):
            return self._apewisdom_fallback(ticker, query, errors + self._source_errors)

        return {
            "symbol": ticker,
            "query": query,
            "signal_label": self._sentiment_label(avg_sentiment, top_posts),
            "sentiment_score": round(avg_sentiment, 3),
            "post_count": len(posts),
            "qualified_count": len(top_posts),
            "subreddits": self.subreddits,
            "method": "reddit_public_json_top_quality",
            "quality_rules": (
                f"score>={self.min_score}, comments>={self.min_comments}, "
                f"upvote_ratio>={self.min_upvote_ratio}, subreddit_weight, hype_penalty"
            ),
            "top_posts": top_posts,
            "top_headline": top_posts[0]["title"] if top_posts else "",
            "provider_errors": errors,
        }

    def _fetch_subreddit(
        self,
        *,
        subreddit: str,
        query: str,
        limit: int,
        sort: str,
        time_filter: str,
    ) -> list[dict[str, Any]]:
        """Fetch posts for *query* from *subreddit* using up to 2 search phases.

        Phase 1 — Direct ticker search (existing behavior).
        Phase 2 — Whale/pump/dump keyword expansion (new) to surface posts
                  discussing whale activity, pumps, and large orders that
                  the basic ticker search might miss.

        Never raises. Returns ``[]`` on total failure.
        """
        safe_subreddit = re.sub(r"[^A-Za-z0-9_]", "", subreddit)
        if not safe_subreddit:
            return []

        match_terms = _match_terms(query)
        all_posts: list[dict[str, Any]] = []

        # ── Phase 1: Direct ticker search ────────────────────────────────
        ticker_posts = self._cascade_fetch(
            subreddit=safe_subreddit,
            query=query,
            limit=limit,
            sort=sort,
            time_filter=time_filter,
            match_terms=match_terms,
        )
        all_posts.extend(ticker_posts)

        # ── Phase 2: Whale keyword expansion ─────────────────────────────
        # Searches for posts mentioning whale/pump/dump terms, then filters
        # for those that also mention the ticker.  This catches discussions
        # about whale activity, pumps, and large orders.
        base_ticker = query.strip('"')
        if base_ticker:
            kw_query = f"{query} {' '.join(WHALE_KEYWORDS)}"
            kw_match_terms = list(set(match_terms + [kw.lower() for kw in WHALE_KEYWORDS]))
            kw_limit = max(1, limit // 2) if ticker_posts else limit
            kw_posts = self._cascade_fetch(
                subreddit=safe_subreddit,
                query=kw_query,
                limit=kw_limit,
                sort=sort,
                time_filter=time_filter,
                match_terms=kw_match_terms,
            )
            # Strict post-filter: post must mention the ticker AND at least
            # one whale keyword to qualify.
            ticker_lower = base_ticker.lower()
            for post in kw_posts:
                title_lower = post.get("title", "").lower()
                snippet_lower = post.get("snippet", "").lower()
                if ticker_lower not in title_lower and ticker_lower not in snippet_lower:
                    continue
                has_whale = any(
                    kw.lower() in title_lower or kw.lower() in snippet_lower
                    for kw in WHALE_KEYWORDS
                )
                if has_whale:
                    all_posts.append(post)

        return all_posts

    def _cascade_fetch(
        self,
        *,
        subreddit: str,
        query: str,
        limit: int,
        sort: str,
        time_filter: str,
        match_terms: list[str],
    ) -> list[dict[str, Any]]:
        """Try Pushshift.io first, then old.reddit.com as fallback.

        Never raises. Records failures in ``self._source_errors`` so that
        ``get_signal()`` can decide whether to fall back to ApeWisdom.
        Returns ``[]`` when every source fails.
        """
        last_error: str | None = None

        # Try 1: Pushshift.io — free historical archive, no OAuth required
        try:
            result = self._fetch_via_pushshift(
                subreddit=subreddit,
                query=query,
                limit=limit,
                match_terms=match_terms,
            )
            if result:
                return result
        except Exception as exc:
            last_error = f"r/{subreddit} pushshift: {exc}"

        # Try 2: old.reddit.com — public JSON with User-Agent header
        try:
            result = self._fetch_via_old_reddit(
                subreddit=subreddit,
                query=query,
                limit=limit,
                sort=sort,
                time_filter=time_filter,
                match_terms=match_terms,
            )
            if result:
                return result
        except Exception as exc:
            last_error = f"r/{subreddit} old_reddit: {exc}"

        # Both sources failed or returned empty
        if last_error:
            self._source_errors.append(last_error)
        return []

    def _fetch_via_pushshift(
        self,
        *,
        subreddit: str,
        query: str,
        limit: int,
        match_terms: list[str],
    ) -> list[dict[str, Any]]:
        """Fetch posts via Pushshift.io API (free, no OAuth, historical archive)."""
        url = "https://api.pushshift.io/reddit/search/submission/"
        params = {
            "subreddit": subreddit,
            "q": query,
            "size": max(1, min(limit, 25)),
            "sort": "desc",
            "sort_type": "score",
        }
        response = self.session.get(url, params=params, timeout=self.timeout_s)
        response.raise_for_status()
        payload = response.json()

        posts = []
        for item in payload.get("data", []):
            # Normalise Pushshift's permalink to path-only for _normalize_post
            permalink = item.get("permalink") or ""
            if permalink.startswith("http"):
                parsed = urlparse(permalink)
                item["permalink"] = parsed.path
            post = self._normalize_post(item, subreddit, match_terms=match_terms)
            if post:
                posts.append(post)
        return posts

    def _fetch_via_old_reddit(
        self,
        *,
        subreddit: str,
        query: str,
        limit: int,
        sort: str,
        time_filter: str,
        match_terms: list[str],
    ) -> list[dict[str, Any]]:
        """Fetch posts via old.reddit.com public JSON (needs User-Agent header)."""
        safe_sort = sort if sort in {"relevance", "hot", "top", "new", "comments"} else "top"
        url = f"https://old.reddit.com/r/{subreddit}/search.json"
        params: dict[str, str | int] = {
            "q": query,
            "restrict_sr": 1,
            "sort": safe_sort,
            "t": time_filter,
            "limit": max(1, min(limit, 25)),
            "raw_json": 1,
        }
        response = self.session.get(url, params=params, timeout=self.timeout_s)
        if response.status_code == 429:
            raise RuntimeError("rate_limited")
        response.raise_for_status()
        payload = response.json()

        posts = []
        for child in payload.get("data", {}).get("children", []):
            item = child.get("data", {})
            post = self._normalize_post(item, subreddit, match_terms=match_terms)
            if post:
                posts.append(post)
        return posts

    def _apewisdom_fallback(
        self,
        ticker: str,
        query: str,
        errors: list[str],
    ) -> dict[str, Any]:
        """Fallback to ApeWisdom when all Reddit sources are blocked."""
        try:
            from .apewisdom_provider import ApeWisdomProvider

            ape = ApeWisdomProvider()
            ape_result = ape.get_sentiment(ticker)
            mentions = ape_result.get("mentions", 0)
            if mentions > 0:
                raw_score = ape_result.get("sentiment_score", 50)
                # Normalise ApeWisdom 0-100 score to -1..1 range
                sentiment_score = (raw_score - 50) / 50.0
                return {
                    "symbol": ticker,
                    "query": query,
                    "signal_label": (
                        "BULLISH_SOCIAL"
                        if sentiment_score > 0.2
                        else "BEARISH_SOCIAL"
                        if sentiment_score < -0.2
                        else "NEUTRAL_SOCIAL"
                    ),
                    "sentiment_score": round(sentiment_score, 3),
                    "post_count": mentions,
                    "qualified_count": 1,
                    "subreddits": self.subreddits,
                    "method": "apewisdom_fallback",
                    "quality_rules": "fallback: reddit_api_blocked",
                    "top_posts": [],
                    "top_headline": f"ApeWisdom fallback: {mentions} mentions for {ape_result.get('ticker', ticker)}",
                    "provider_errors": errors,
                    "fallback_source": "apewisdom",
                }
        except Exception as exc:
            errors.append(f"apewisdom_fallback: {exc}")

        # ApeWisdom also failed — return empty signal
        return {
            "symbol": ticker,
            "query": query,
            "signal_label": "NO_DATA",
            "post_count": 0,
            "qualified_count": 0,
            "subreddits": self.subreddits,
            "method": "all_sources_failed",
            "quality_rules": "all_reddit_and_fallback_sources_failed",
            "top_posts": [],
            "top_headline": "",
            "provider_errors": errors,
        }

    def _normalize_post(
        self,
        item: dict[str, Any],
        subreddit: str,
        match_terms: list[str] | None = None,
    ) -> dict[str, Any] | None:
        title = str(item.get("title") or "").strip()
        if not title:
            return None
        if item.get("over_18") or item.get("removed_by_category"):
            return None

        selftext = str(item.get("selftext") or "")
        if selftext.strip().lower() in {"[removed]", "[deleted]"}:
            selftext = ""

        terms = match_terms or []
        haystack = f"{title} {selftext} {item.get('url', '')}".lower()
        matched_terms = [term for term in terms if term in haystack]
        if terms and not matched_terms:
            return None
        title_hit = any(term in title.lower() for term in matched_terms)
        body_hit = any(term in selftext.lower() for term in matched_terms)
        relevance_bonus = (1.5 if title_hit else 0.0) + (0.5 if body_hit else 0.0)

        score = int(item.get("score") or 0)
        comments = int(item.get("num_comments") or 0)
        upvote_ratio = float(item.get("upvote_ratio") or 0)
        hype_flags = self._hype_flags(f"{title} {selftext[:300]}")
        quality_score = (
            self._quality_score(
                subreddit=subreddit,
                score=score,
                comments=comments,
                upvote_ratio=upvote_ratio,
                hype_count=len(hype_flags),
            )
            + relevance_bonus
        )

        if score < self.min_score or comments < self.min_comments:
            return None
        if upvote_ratio and upvote_ratio < self.min_upvote_ratio:
            return None

        permalink = item.get("permalink") or ""
        return {
            "id": item.get("id"),
            "subreddit": subreddit,
            "title": title[:240],
            "snippet": selftext.strip().replace("\n", " ")[:220],
            "score": score,
            "comments": comments,
            "upvote_ratio": round(upvote_ratio, 3),
            "created_utc": item.get("created_utc"),
            "url": (f"https://www.reddit.com{permalink}" if permalink else item.get("url")),
            "quality_score": round(quality_score, 3),
            "sentiment_score": round(self._sentiment(f"{title}. {selftext[:500]}"), 3),
            "hype_flags": hype_flags,
            "matched_terms": matched_terms,
            "is_self": bool(item.get("is_self")),
        }

    def _quality_score(
        self,
        *,
        subreddit: str,
        score: int,
        comments: int,
        upvote_ratio: float,
        hype_count: int,
    ) -> float:
        subreddit_weight = SUBREDDIT_WEIGHTS.get(subreddit.lower(), 0.85)
        engagement = math.log10(max(score, 1) + 1) * 2.0
        discussion = min(comments, 300) / 75.0
        consensus = max(upvote_ratio, 0.50) * 2.0
        hype_penalty = hype_count * 1.25
        return max(0.0, (engagement + discussion + consensus) * subreddit_weight - hype_penalty)

    def _dedupe_and_rank(self, posts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[str] = set()
        ranked = []
        for post in sorted(posts, key=lambda item: item["quality_score"], reverse=True):
            key = str(post.get("url") or post.get("id") or post.get("title", "")).lower()
            if key in seen:
                continue
            seen.add(key)
            ranked.append(post)
        return ranked

    def _hype_flags(self, text: str) -> list[str]:
        lowered = text.lower()
        return [pattern.strip(r"\b") for pattern in HYPE_PATTERNS if re.search(pattern, lowered)]

    def _sentiment(self, text: str) -> float:
        if not TextBlob:
            return 0.0
        return float(TextBlob(text).sentiment.polarity)

    def _average_sentiment(self, posts: list[dict[str, Any]]) -> float:
        if not posts:
            return 0.0
        total_weight = sum(max(post["quality_score"], 0.1) for post in posts)
        weighted = sum(post["sentiment_score"] * max(post["quality_score"], 0.1) for post in posts)
        return weighted / total_weight if total_weight else 0.0

    @staticmethod
    def _sentiment_label(score: float, posts: list[dict[str, Any]]) -> str:
        if not posts:
            return "NO_DATA"
        if score > 0.15:
            return "BULLISH_SOCIAL"
        if score < -0.15:
            return "BEARISH_SOCIAL"
        return "NEUTRAL_SOCIAL"
