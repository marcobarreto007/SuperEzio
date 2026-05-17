"""
Professional Data Collector — Provider Mesh with Intelligent Selection.

Replaces the sequential fallback with a parallel multi-provider
mesh. Every provider for a capability is queried simultaneously; results are
scored on freshness, completeness, and consistency; the best result wins.

Architecture:
  ProviderMesh       — registry of all providers with health tracking
  IntelligentSelector — picks providers by capability, exchange, and health
  DataQualityFilter   — validates, normalizes, and scores each result
  CacheLayer          — disk-based TTL cache to avoid redundant API calls
  CircuitBreaker      — disables failing providers for a cooldown period
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

_SUPPORTED_EXCHANGES = frozenset({"TSX", "TSXV", "NASDAQ", "NYSE", "NYSEARCA", "OTC"})

_CAPABILITY_PRICE = "price"
_CAPABILITY_QUOTE = "quote"
_CAPABILITY_FUNDAMENTALS = "fundamentals"
_CAPABILITY_NEWS = "news"
_CAPABILITY_SENTIMENT = "sentiment"
_CAPABILITY_SOCIAL = "social"
_CAPABILITY_MACRO = "macro"
_CAPABILITY_TECHNICALS = "technicals"

# How long to cache each data type (seconds)
_CACHE_TTL: dict[str, int] = {
    _CAPABILITY_PRICE: 300,  # 5 minutes
    _CAPABILITY_QUOTE: 300,
    _CAPABILITY_FUNDAMENTALS: 21600,  # 6 hours
    _CAPABILITY_NEWS: 3600,  # 1 hour
    _CAPABILITY_SENTIMENT: 1800,  # 30 minutes
    _CAPABILITY_SOCIAL: 1800,
    _CAPABILITY_MACRO: 86400,  # 24 hours
    _CAPABILITY_TECHNICALS: 3600,
}

# Circuit breaker: after N consecutive failures, disable for this long
_CB_FAILURE_THRESHOLD = 3
_CB_COOLDOWN_SEC = 300  # 5 minutes

# Expected fields per capability (for completeness scoring)
_EXPECTED_FIELDS: dict[str, frozenset] = {
    _CAPABILITY_PRICE: frozenset({"price", "symbol", "source", "timestamp"}),
    _CAPABILITY_QUOTE: frozenset({"price", "symbol", "change_pct", "volume", "source"}),
    _CAPABILITY_FUNDAMENTALS: frozenset({"name", "sector", "market_cap", "source"}),
    _CAPABILITY_NEWS: frozenset({"headline", "url", "source"}),
    _CAPABILITY_SENTIMENT: frozenset(
        {"sentiment_label", "sentiment_score", "source", "news_count", "top_headline"}
    ),
    _CAPABILITY_SOCIAL: frozenset({"signal_label", "sentiment_score", "source"}),
    _CAPABILITY_MACRO: frozenset({"source"}),
    _CAPABILITY_TECHNICALS: frozenset({"price", "rsi_14", "source"}),
}


# ── Helpers ──────────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_filename(ticker: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in ticker)


def _detect_exchange(ticker: str) -> str:
    """Detect exchange from ticker suffix/prefix."""
    t = ticker.upper().replace(" ", "")
    if t.endswith(".TO"):
        return "TSX"
    if t.endswith(".V"):
        return "TSXV"
    if t.endswith(".SA"):
        return "BVMF"
    if len(t) <= 5 and t.isalpha():
        return "NYSE"  # Most short alphabetic tickers are NYSE/NASDAQ
    return "NASDAQ"


def _is_penny(ticker: str, price: float | None = None) -> bool:
    """Heuristic penny stock detection."""
    t = ticker.upper()
    if t.endswith(".V"):
        return True  # TSX-V is almost all penny stocks
    if price is not None and price < 5.0:
        return True
    return False


# ── Circuit Breaker ──────────────────────────────────────────────────────────


@dataclass
class CircuitBreaker:
    """Tracks provider health, disables after consecutive failures."""

    failures: int = 0
    last_failure_time: float = 0.0
    disabled_until: float = 0.0

    def record_success(self) -> None:
        self.failures = 0
        self.disabled_until = 0.0

    def record_failure(self) -> None:
        self.failures += 1
        self.last_failure_time = time.monotonic()
        if self.failures >= _CB_FAILURE_THRESHOLD:
            self.disabled_until = time.monotonic() + _CB_COOLDOWN_SEC

    @property
    def is_open(self) -> bool:
        if self.disabled_until and time.monotonic() < self.disabled_until:
            return True
        if self.disabled_until and time.monotonic() >= self.disabled_until:
            self.disabled_until = 0.0
            self.failures = 0
        return False


# ── Cache Layer ──────────────────────────────────────────────────────────────


class CacheLayer:
    """TTL disk cache keyed by (ticker, capability, provider)."""

    def __init__(self, cache_dir: str | None = None) -> None:
        self._dir = Path(
            cache_dir
            or os.getenv("SUPEREZIO_CACHE_DIR", "")
            or Path(__file__).parent.parent.parent.parent
            / ".f51"
            / "cache"
            / "collector"
        )
        self._dir.mkdir(parents=True, exist_ok=True)

    def _key(self, ticker: str, capability: str, provider: str) -> str:
        raw = f"{ticker.upper()}:{capability}:{provider}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def get(self, ticker: str, capability: str, provider: str) -> dict | None:
        path = self._dir / f"{self._key(ticker, capability, provider)}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        ttl = _CACHE_TTL.get(capability, 300)
        age = time.time() - data.get("_cached_at", 0)
        if age > ttl:
            return None
        return data.get("payload")

    def set(self, ticker: str, capability: str, provider: str, payload: dict) -> None:
        path = self._dir / f"{self._key(ticker, capability, provider)}.json"
        try:
            path.write_text(
                json.dumps(
                    {"_cached_at": time.time(), "payload": payload},
                    ensure_ascii=False,
                    default=str,
                ),
                encoding="utf-8",
            )
        except OSError:
            pass


# ── Data Quality Filter ──────────────────────────────────────────────────────


class DataQualityFilter:
    """Validates, normalizes, and scores data from any provider."""

    @staticmethod
    def is_valid(result: dict | None) -> bool:
        if result is None:
            return False
        if not isinstance(result, dict):
            return False
        if "error" in result:
            return False
        # NO_DATA / empty results are technically valid but useless
        if (
            result.get("sentiment_label") == "NO_DATA"
            and result.get("news_count", 1) == 0
        ):
            return False
        if result.get("signal_label") == "NO_DATA":
            return False
        return True

    @staticmethod
    def score_freshness(timestamp: str | None) -> float:
        """Score based on how recent the data is (0-1)."""
        if not timestamp:
            return 0.3  # Unknown freshness = mediocre
        try:
            dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            age_sec = (datetime.now(timezone.utc) - dt).total_seconds()
        except (ValueError, TypeError):
            return 0.3
        if age_sec < 60:
            return 1.0
        if age_sec < 300:
            return 0.9
        if age_sec < 900:
            return 0.7
        if age_sec < 3600:
            return 0.4
        return 0.1

    @staticmethod
    def score_completeness(data: dict, capability: str) -> float:
        """Score based on how many expected fields are present (0-1)."""
        expected = _EXPECTED_FIELDS.get(capability, frozenset())
        if not expected:
            return 0.5
        present = sum(1 for f in expected if data.get(f) is not None)
        return present / len(expected) if expected else 0.5

    @staticmethod
    def score_confidence(data: dict) -> float:
        """Extract or infer confidence from the data itself."""
        explicit = data.get("confidence") or data.get("data_quality_score")
        if isinstance(explicit, (int, float)):
            return float(explicit)
        return 0.5

    def score(self, data: dict, capability: str) -> float:
        """Composite quality score 0-1."""
        if not self.is_valid(data):
            return 0.0
        freshness = self.score_freshness(
            data.get("timestamp") or data.get("collected_at")
        )
        completeness = self.score_completeness(data, capability)
        confidence = self.score_confidence(data)
        return 0.35 * freshness + 0.40 * completeness + 0.25 * confidence

    @staticmethod
    def normalize_price(data: dict, symbol: str) -> dict:
        """Normalize any provider's price output to unified schema."""
        price = data.get("price")
        if price is None:
            for key in (
                "05. price",
                "close",
                "last",
                "currentPrice",
                "regularMarketPrice",
            ):
                if data.get(key) is not None:
                    price = float(data[key])
                    break
        return {
            "symbol": symbol,
            "price": float(price) if price is not None else None,
            "change_pct": data.get("change_pct") or data.get("10. change percent"),
            "volume": data.get("volume") or data.get("06. volume"),
            "source": data.get("source", "unknown"),
            "timestamp": data.get("timestamp", _now_iso()),
            "provider": data.get("provider", data.get("source", "unknown")),
        }

    @staticmethod
    def normalize_quote(data: dict, symbol: str) -> dict:
        """Normalize quote output to unified schema."""
        return DataQualityFilter.normalize_price(data, symbol)


# ── Provider Mesh ────────────────────────────────────────────────────────────


@dataclass
class ProviderSpec:
    """Descriptor for one provider in the mesh."""

    name: str
    capabilities: tuple[str, ...]
    fetch: Callable[..., Any]  # async callable(ticker) -> dict
    priority: int = 100  # lower = preferred
    required_key: str | None = None
    exchanges: tuple[str, ...] = ()  # empty = all exchanges
    rate_limit_rps: float = 10.0  # max requests/second
    supports_penny: bool = True


class ProviderMesh:
    """Registry of all data providers with health tracking and selection."""

    def __init__(self) -> None:
        self._specs: dict[str, ProviderSpec] = {}
        self._breakers: dict[str, CircuitBreaker] = {}
        self._last_call: dict[str, float] = {}

    def register(self, spec: ProviderSpec) -> None:
        self._specs[spec.name] = spec
        if spec.name not in self._breakers:
            self._breakers[spec.name] = CircuitBreaker()

    def is_available(self, name: str) -> bool:
        spec = self._specs.get(name)
        if not spec:
            return False
        if self._breakers[name].is_open:
            return False
        if spec.required_key and not os.getenv(spec.required_key):
            return False
        return True

    def select(
        self,
        capability: str,
        ticker: str = "",
        limit: int = 3,
    ) -> list[ProviderSpec]:
        """Select best available providers for a capability.

        Sorted by priority. Providers with open circuit breakers or
        missing API keys are excluded. Exchange-aware filtering.
        """
        exchange = _detect_exchange(ticker) if ticker else ""
        candidates: list[tuple[int, ProviderSpec]] = []

        for spec in self._specs.values():
            if capability not in spec.capabilities:
                continue
            if not self.is_available(spec.name):
                continue
            if spec.exchanges and exchange and exchange not in spec.exchanges:
                # Provider explicitly lists exchanges and this ticker's exchange
                # isn't one of them — skip unless it has no exchange filter.
                continue
            candidates.append((spec.priority, spec))

        candidates.sort(key=lambda x: x[0])
        return [spec for _, spec in candidates[:limit]]

    def record_success(self, name: str) -> None:
        if name in self._breakers:
            self._breakers[name].record_success()

    def record_failure(self, name: str) -> None:
        if name in self._breakers:
            self._breakers[name].record_failure()

    def health_report(self) -> dict:
        return {
            name: {
                "available": self.is_available(name),
                "circuit_open": self._breakers[name].is_open,
                "failures": self._breakers[name].failures,
            }
            for name in self._specs
        }

    def _rate_limit_wait(self, name: str) -> None:
        """Simple rate limiter — not async, blocks briefly."""
        now = time.monotonic()
        spec = self._specs.get(name)
        if not spec or spec.rate_limit_rps <= 0:
            return
        last = self._last_call.get(name, 0)
        interval = 1.0 / spec.rate_limit_rps
        if now - last < interval:
            time.sleep(interval - (now - last))
        self._last_call[name] = time.monotonic()

    async def query_one(self, name: str, ticker: str, timeout: float = 10.0) -> dict:
        """Query a single provider, with rate limiting and error handling."""
        spec = self._specs.get(name)
        if not spec:
            return {"error": f"unknown_provider: {name}"}

        self._rate_limit_wait(name)
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(spec.fetch, ticker),
                timeout=timeout,
            )
            if isinstance(result, dict) and "error" not in result:
                self.record_success(name)
                result.setdefault("provider", name)
                result.setdefault("timestamp", _now_iso())
            else:
                self.record_failure(name)
            return (
                result if isinstance(result, dict) else {"error": "invalid_result_type"}
            )
        except asyncio.TimeoutError:
            self.record_failure(name)
            return {"error": f"{name}_timeout_{timeout}s"}
        except Exception as exc:
            self.record_failure(name)
            return {"error": f"{name}_error: {type(exc).__name__}: {exc}"}

    async def query_all(
        self,
        capability: str,
        ticker: str,
        timeout: float = 12.0,
        cache: CacheLayer | None = None,
    ) -> dict:
        """Query all selected providers in parallel, return best result.

        Strategy:
        1. Check cache for each selected provider
        2. If cache hit → use it, skip API call
        3. If cache miss → query in parallel
        4. Score all results
        5. Return highest scoring
        """
        specs = self.select(capability, ticker)
        if not specs:
            return {
                "error": f"no_provider_available_for_{capability}",
                "symbol": ticker,
            }

        quality = DataQualityFilter()
        best_result: dict | None = None
        best_score = -1.0
        all_results: list[dict] = []

        # Check cache first for each selected provider
        uncached: list[ProviderSpec] = []
        for spec in specs:
            if cache:
                cached = cache.get(ticker, capability, spec.name)
                if cached:
                    score = quality.score(cached, capability)
                    all_results.append({**cached, "_cached": True, "_score": score})
                    if score > best_score:
                        best_score = score
                        best_result = cached
                    continue
            uncached.append(spec)

        # Query uncached providers in parallel
        if uncached:
            tasks = [self.query_one(spec.name, ticker, timeout) for spec in uncached]
            live_results = await asyncio.gather(*tasks, return_exceptions=True)

            for spec, result in zip(uncached, live_results):
                if isinstance(result, Exception):
                    result = {
                        "error": f"{spec.name}: {type(result).__name__}: {result}"
                    }
                if not isinstance(result, dict):
                    result = {"error": f"{spec.name}: invalid_result"}

                all_results.append(result)

                if quality.is_valid(result):
                    normalized = result  # Keep as-is for non-price capabilities
                    if capability in (_CAPABILITY_PRICE, _CAPABILITY_QUOTE):
                        normalized = quality.normalize_price(result, ticker)
                    score = quality.score(normalized, capability)
                    normalized["_score"] = score
                    all_results.append(normalized)
                    if cache:
                        cache.set(ticker, capability, spec.name, normalized)
                    if score > best_score:
                        best_score = score
                        best_result = normalized

        if best_result is None:
            return {
                "error": f"all_providers_failed_for_{capability}",
                "symbol": ticker,
                "attempts": [
                    {
                        "provider": r.get("provider", "?"),
                        "error": r.get("error", "empty"),
                    }
                    for r in all_results
                ],
            }

        return {
            **best_result,
            "_mesh_results": len(all_results),
            "_mesh_score": best_score,
        }


# ── Professional Collector ───────────────────────────────────────────────────


class ProfessionalCollector:
    """Professional-grade data collector with intelligent provider selection.

    Usage:
        collector = ProfessionalCollector()
        data = await collector.collect("REE.V")
        # data["price"] → best price from mesh
        # data["fundamentals"] → best fundamentals from mesh
        # data["news"] → latest news
        # data["quality_report"] → per-section quality scores
    """

    def __init__(self, cache_dir: str | None = None) -> None:
        from core.config import load_env_once

        load_env_once()
        self.mesh = ProviderMesh()
        self.cache = CacheLayer(cache_dir)
        self._register_providers()

    def _register_providers(self) -> None:
        # ── Price providers ──────────────────────────────────────────────
        self.mesh.register(
            ProviderSpec(
                name="twelve_data",
                capabilities=(_CAPABILITY_PRICE, _CAPABILITY_QUOTE),
                fetch=self._fetch_twelve_data_price,
                priority=10,
                required_key="TWELVE_DATA_API_KEY",
                rate_limit_rps=0.13,  # 8/min
            )
        )
        self.mesh.register(
            ProviderSpec(
                name="alpha_vantage",
                capabilities=(_CAPABILITY_PRICE, _CAPABILITY_QUOTE),
                fetch=self._fetch_alpha_vantage_quote,
                priority=15,
                required_key="ALPHA_VANTAGE_API_KEY",
                rate_limit_rps=0.4,  # 25/day ≈ very slow
            )
        )
        self.mesh.register(
            ProviderSpec(
                name="hub_price",
                capabilities=(
                    _CAPABILITY_PRICE,
                    _CAPABILITY_QUOTE,
                    _CAPABILITY_TECHNICALS,
                ),
                fetch=self._fetch_hub_price,
                priority=30,
                rate_limit_rps=1.0,
                supports_penny=True,
            )
        )

        # ── Fundamentals ─────────────────────────────────────────────────
        self.mesh.register(
            ProviderSpec(
                name="hub_profile",
                capabilities=(_CAPABILITY_FUNDAMENTALS,),
                fetch=self._fetch_hub_profile,
                priority=20,
                rate_limit_rps=1.0,
                supports_penny=True,
            )
        )

        # ── News / Sentiment ─────────────────────────────────────────────
        self.mesh.register(
            ProviderSpec(
                name="newsapi",
                capabilities=(
                    _CAPABILITY_NEWS,
                    _CAPABILITY_SENTIMENT,
                    "market_sentiment",
                ),
                fetch=self._fetch_newsapi_sentiment,
                priority=5,  # Primary — real headlines via tested API key
                required_key="NEWSAPI_KEY",
                rate_limit_rps=0.014,  # 100 req/day free tier
            )
        )
        self.mesh.register(
            ProviderSpec(
                name="news_scout",
                capabilities=(_CAPABILITY_NEWS, _CAPABILITY_SENTIMENT),
                fetch=self._fetch_news_scout,
                priority=15,  # Fallback — RSS/DDG scrapers
                rate_limit_rps=2.0,
            )
        )

        # ── Social ───────────────────────────────────────────────────────
        self.mesh.register(
            ProviderSpec(
                name="reddit_pulse",
                capabilities=(_CAPABILITY_SOCIAL,),
                fetch=self._fetch_reddit_signal,
                priority=10,
                rate_limit_rps=1.0,
            )
        )

        # ── Quantitative / Math Verification ─────────────────────────────
        self.mesh.register(
            ProviderSpec(
                name="wolfram",
                capabilities=("quantitative", "math_verify"),
                fetch=self._fetch_wolfram_verify,
                priority=20,
                required_key="WOLFRAM_API_KEY",
                rate_limit_rps=0.05,  # 2000 calls/month
            )
        )

    # ── Provider fetch methods (synchronous, called via to_thread) ───────

    @staticmethod
    def _fetch_twelve_data_price(ticker: str) -> dict:
        try:
            from data.twelve_data import TwelveDataProvider

            api_key = os.getenv("TWELVE_DATA_API_KEY")
            if not api_key:
                return {"error": "TWELVE_DATA_API_KEY not set"}
            provider = TwelveDataProvider(api_key=api_key)
            result = provider.get_price(ticker)
            if "error" in result:
                return result
            return {
                "symbol": ticker,
                "price": float(result.get("price", 0)),
                "source": "twelve_data",
                "timestamp": _now_iso(),
            }
        except Exception as exc:
            return {"error": f"twelve_data: {exc}"}

    @staticmethod
    def _fetch_alpha_vantage_quote(ticker: str) -> dict:
        try:
            from data.alpha_vantage import AlphaVantageProvider

            api_key = os.getenv("ALPHA_VANTAGE_API_KEY")
            if not api_key:
                return {"error": "ALPHA_VANTAGE_API_KEY not set"}
            provider = AlphaVantageProvider(api_key=api_key)
            result = provider.get_quote(ticker)
            if "error" in result:
                return result
            return {
                "symbol": ticker,
                "price": float(result.get("price", 0)),
                "change_pct": result.get("change_pct"),
                "volume": result.get("volume"),
                "source": "alpha_vantage",
                "timestamp": _now_iso(),
            }
        except Exception as exc:
            return {"error": f"alpha_vantage: {exc}"}

    @staticmethod
    def _fetch_hub_price(ticker: str) -> dict:
        try:
            from data.data_hub import hub

            result = hub.get_price(ticker)
            if "error" in result:
                return result
            return {
                "symbol": ticker,
                "price": float(result.get("price", 0)),
                "change_pct": result.get("change_pct"),
                "volume": result.get("volume"),
                "source": result.get("provider", "datahub"),
                "timestamp": _now_iso(),
            }
        except Exception as exc:
            return {"error": f"hub_price: {exc}"}

    @staticmethod
    def _fetch_hub_profile(ticker: str) -> dict:
        try:
            from data.data_hub import hub

            result = hub.get_profile(ticker)
            if "error" in result:
                return result
            return {
                "symbol": ticker,
                "name": result.get("name"),
                "sector": result.get("sector"),
                "industry": result.get("industry"),
                "market_cap": result.get("market_cap"),
                "pe_ratio": result.get("pe_ratio"),
                "dividend_yield": result.get("dividend_yield"),
                "beta": result.get("beta"),
                "enterprise_to_ebitda": result.get("enterprise_to_ebitda"),
                "return_on_equity": result.get("return_on_equity"),
                "source": "datahub",
                "timestamp": _now_iso(),
            }
        except Exception as exc:
            return {"error": f"hub_profile: {exc}"}

    @staticmethod
    def _fetch_newsapi_sentiment(ticker: str) -> dict:
        try:
            from data.newsapi_provider import NewsAPIProvider

            provider = NewsAPIProvider()
            result = provider.get_sentiment_summary(ticker)
            if not isinstance(result, dict):
                return {"error": "newsapi_invalid_result"}
            return {**result, "timestamp": result.get("timestamp", _now_iso())}
        except Exception as exc:
            return {"error": f"newsapi: {exc}"}

    @staticmethod
    def _fetch_news_scout(ticker: str) -> dict:
        try:
            from data.news_feed import NewsScout

            scout = NewsScout()
            clean = (
                ticker.replace(".TO", "")
                .replace(".V", "")
                .replace(".to", "")
                .replace(".v", "")
            )
            result = scout.get_sentiment_summary(clean)
            if not isinstance(result, dict):
                return {"error": "news_scout_invalid_result"}
            return {
                **result,
                "source": result.get("source", "news_scout"),
                "timestamp": _now_iso(),
            }
        except Exception as exc:
            return {"error": f"news_scout: {exc}"}

    @staticmethod
    def _fetch_wolfram_verify(ticker: str) -> dict:
        """Verify quantitative outputs via Wolfram Alpha.

        The 'ticker' parameter is overloaded — for math_verify capability
        it's the expression to verify, not a stock symbol.
        """
        try:
            from data.wolfram_provider import WolframProvider

            provider = WolframProvider()
            result = provider.query(ticker)
            return (
                result
                if isinstance(result, dict)
                else {"error": "wolfram_invalid_result"}
            )
        except Exception as exc:
            return {"error": f"wolfram: {exc}"}

    @staticmethod
    def _fetch_reddit_signal(ticker: str) -> dict:
        try:
            from data.reddit_provider import RedditPulse

            pulse = RedditPulse()
            result = pulse.get_signal(ticker)
            if not isinstance(result, dict):
                return {"error": "reddit_pulse_invalid_result"}
            return {
                **result,
                "source": result.get("source", "reddit_pulse"),
                "timestamp": _now_iso(),
            }
        except Exception as exc:
            return {"error": f"reddit_pulse: {exc}"}

    # ── Main collection ──────────────────────────────────────────────────

    async def collect(
        self,
        ticker: str,
        *,
        include_price: bool = True,
        include_fundamentals: bool = True,
        include_news: bool = True,
        include_social: bool = True,
        include_macro: bool = True,
        include_technicals: bool = True,
        overall_timeout: float = 45.0,
    ) -> dict:
        """Collect all available data for a ticker using the provider mesh.

        All sections are queried in parallel. Each section independently
        selects the best provider result.
        """
        analysis_id = f"{_safe_filename(ticker)}-{uuid.uuid4().hex[:12]}"
        exchange = _detect_exchange(ticker)

        tasks: dict[str, asyncio.Task] = {}

        if include_price:
            tasks["price"] = asyncio.create_task(
                self.mesh.query_all(_CAPABILITY_PRICE, ticker, cache=self.cache)
            )
        if include_fundamentals:
            tasks["fundamentals"] = asyncio.create_task(
                self.mesh.query_all(_CAPABILITY_FUNDAMENTALS, ticker, cache=self.cache)
            )
        if include_news:
            tasks["sentiment"] = asyncio.create_task(
                self.mesh.query_all(_CAPABILITY_SENTIMENT, ticker, cache=self.cache)
            )
        if include_social:
            tasks["social"] = asyncio.create_task(
                self.mesh.query_all(_CAPABILITY_SOCIAL, ticker, cache=self.cache)
            )
        if include_macro:
            tasks["macro"] = asyncio.create_task(self._collect_macro(ticker))
        if include_technicals:
            tasks["technicals"] = asyncio.create_task(self._collect_technicals(ticker))

        try:
            gathered = await asyncio.wait_for(
                asyncio.gather(*tasks.values(), return_exceptions=True),
                timeout=overall_timeout,
            )
        except asyncio.TimeoutError:
            gathered = [{"error": f"collect_timeout_{overall_timeout}s"} for _ in tasks]

        results: dict[str, Any] = {}
        for key, result in zip(tasks.keys(), gathered):
            if isinstance(result, Exception):
                results[key] = {"error": f"{key}: {type(result).__name__}: {result}"}
            elif isinstance(result, dict):
                results[key] = result
            else:
                results[key] = {"error": f"{key}: invalid_result"}

        # Build quality report
        quality = DataQualityFilter()
        quality_report = {
            cap: {
                "score": quality.score(results.get(cap, {}), cap),
                "provider": results.get(cap, {}).get("provider", "?"),
            }
            for cap in ("price", "fundamentals", "sentiment", "social")
        }

        data = {
            "analysis_id": analysis_id,
            "ticker": ticker,
            "exchange": exchange,
            "collected_at": _now_iso(),
            "price": results.get("price", {}),
            "fundamentals": results.get("fundamentals", {}),
            "sentiment": results.get("sentiment", {}),
            "social": results.get("social", {}),
            "macro": results.get("macro", {}),
            "technicals": results.get("technicals", {}),
            "quality_report": quality_report,
            "mesh_health": self.mesh.health_report(),
            "data_quality": self._overall_quality(quality_report),
        }
        self._attach_evidence_ids(data)
        return data

    async def _collect_macro(self, ticker: str) -> dict:
        """Route macro data via DataHub (BoC/Fed)."""
        try:
            from data.data_hub import hub

            exchange = _detect_exchange(ticker)
            market = "CA" if exchange in ("TSX", "TSXV") else "US"
            result = await asyncio.to_thread(hub.get_macro, market)
            return (
                result
                if isinstance(result, dict)
                else {"error": "macro_invalid_result"}
            )
        except Exception as exc:
            return {"error": f"macro: {exc}"}

    async def _collect_technicals(self, ticker: str) -> dict:
        """Compute technicals from price history."""
        try:
            import yfinance as yf

            t = yf.Ticker(ticker)
            df = await asyncio.to_thread(t.history, period="6mo", interval="1d")
            if df.empty:
                return {"error": "no_history_for_technicals"}

            close = df["Close"]
            rsi = _compute_rsi(close, 14)
            macd, macd_signal = _compute_macd(close)
            ema20 = close.ewm(span=20).mean().iloc[-1]
            ema50 = close.ewm(span=50).mean().iloc[-1]
            bb_upper, bb_lower = _compute_bollinger(close, 20)

            return {
                "symbol": ticker,
                "price": float(close.iloc[-1]),
                "rsi_14": round(rsi, 1) if rsi is not None else None,
                "macd": round(macd, 4) if macd is not None else None,
                "macd_signal": round(macd_signal, 4)
                if macd_signal is not None
                else None,
                "ema_20": round(float(ema20), 2),
                "ema_50": round(float(ema50), 2),
                "bb_upper": round(float(bb_upper), 2) if bb_upper is not None else None,
                "bb_lower": round(float(bb_lower), 2) if bb_lower is not None else None,
                "volume": int(df["Volume"].iloc[-1]) if "Volume" in df else None,
                "source": "yfinance_technicals",
                "timestamp": _now_iso(),
            }
        except Exception as exc:
            return {"error": f"technicals: {exc}"}

    @staticmethod
    def _overall_quality(report: dict) -> str:
        scores = [v.get("score", 0) for v in report.values()]
        if not scores:
            return "unknown"
        avg = sum(scores) / len(scores)
        if avg >= 0.7:
            return "high"
        if avg >= 0.4:
            return "partial"
        return "degraded"

    @staticmethod
    def _attach_evidence_ids(data: dict) -> None:
        ticker = data.get("ticker", "UNKNOWN")
        date_part = data.get("collected_at", _now_iso())[:10]
        for section in (
            "price",
            "fundamentals",
            "technicals",
            "sentiment",
            "social",
            "macro",
        ):
            payload = data.get(section)
            if not isinstance(payload, dict):
                continue
            source = payload.get("source", payload.get("provider", section))
            payload.setdefault("evidence_id", f"{source}_{ticker}_{date_part}")
            payload.setdefault(
                "data_quality", "unavailable" if "error" in payload else "collected"
            )

    # ── Context formatting for CEO prompt ────────────────────────────────

    @staticmethod
    def format_context(data: dict) -> str:
        """Format collected data into CEO-readable text block."""
        ticker = data.get("ticker", "?")
        exchange = data.get("exchange", "?")
        quality = data.get("data_quality", "unknown")
        parts = [
            f"=== PROFESSIONAL COLLECTOR: {ticker} ({exchange}) ===",
            f"Quality: {quality} | Collected: {data.get('collected_at', '?')}",
            f"Analysis ID: {data.get('analysis_id', '?')}",
            "Rule: cite evidence_ids. If missing, state what is missing.",
            "",
        ]

        price = data.get("price", {})
        if isinstance(price, dict) and price.get("price") is not None:
            parts.append(
                f"[PRICE] {price.get('price')} "
                f"(source={price.get('source')}, "
                f"score={price.get('_mesh_score', '?')}, "
                f"evidence_id={price.get('evidence_id')})"
            )

        fundamentals = data.get("fundamentals", {})
        if isinstance(fundamentals, dict) and fundamentals.get("name"):
            parts.append(
                f"[PROFILE] {fundamentals.get('name')} | "
                f"Sector: {fundamentals.get('sector', '?')} | "
                f"MCap: {fundamentals.get('market_cap', '?')} | "
                f"P/E: {fundamentals.get('pe_ratio', '?')} | "
                f"Beta: {fundamentals.get('beta', '?')} "
                f"(evidence_id={fundamentals.get('evidence_id')})"
            )

        technicals = data.get("technicals", {})
        if isinstance(technicals, dict) and technicals.get("rsi_14") is not None:
            parts.append(
                f"[TECHS] RSI(14): {technicals.get('rsi_14')} | "
                f"MACD: {technicals.get('macd')} | "
                f"EMA20: {technicals.get('ema_20')} | "
                f"EMA50: {technicals.get('ema_50')} | "
                f"BB: [{technicals.get('bb_lower')}, {technicals.get('bb_upper')}] "
                f"(evidence_id={technicals.get('evidence_id')})"
            )

        sentiment = data.get("sentiment", {})
        if isinstance(sentiment, dict) and sentiment.get("sentiment_label"):
            parts.append(
                f"[SENTIMENT] {sentiment.get('sentiment_label')} "
                f"(score: {sentiment.get('sentiment_score')}) "
                f"(evidence_id={sentiment.get('evidence_id')})"
            )

        social = data.get("social", {})
        if (
            isinstance(social, dict)
            and social.get("signal_label")
            and social.get("signal_label") != "NO_DATA"
        ):
            parts.append(
                f"[SOCIAL] {social.get('signal_label')} "
                f"(score: {social.get('sentiment_score')}) "
                f"(evidence_id={social.get('evidence_id')})"
            )

        macro = data.get("macro", {})
        if isinstance(macro, dict) and "error" not in macro:
            parts.append(f"[MACRO] {macro}")

        quality_report = data.get("quality_report", {})
        if quality_report:
            q_parts = [
                f"  {k}: score={v.get('score', '?')} provider={v.get('provider', '?')}"
                for k, v in quality_report.items()
            ]
            parts.append("[QUALITY]\n" + "\n".join(q_parts))

        return "\n".join(parts)


# ── Technical indicator helpers ──────────────────────────────────────────────


def _compute_rsi(close, period: int = 14) -> float | None:
    if len(close) < period + 1:
        return None
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1 / period).mean().iloc[-1]
    avg_loss = loss.ewm(alpha=1 / period).mean().iloc[-1]
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return float(100.0 - 100.0 / (1.0 + rs))


def _compute_macd(close, fast: int = 12, slow: int = 26, signal: int = 9):
    if len(close) < slow + signal:
        return None, None
    ema_fast = close.ewm(span=fast).mean()
    ema_slow = close.ewm(span=slow).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal).mean()
    return float(macd_line.iloc[-1]), float(signal_line.iloc[-1])


def _compute_bollinger(close, period: int = 20, stddev: float = 2.0):
    if len(close) < period:
        return None, None
    sma = close.rolling(period).mean().iloc[-1]
    std = close.rolling(period).std().iloc[-1]
    return float(sma + stddev * std), float(sma - stddev * std)


# ── Module-level singleton ───────────────────────────────────────────────────

_professional_collector: ProfessionalCollector | None = None


def get_professional_collector(cache_dir: str | None = None) -> ProfessionalCollector:
    global _professional_collector
    if _professional_collector is None:
        _professional_collector = ProfessionalCollector(cache_dir=cache_dir)
    return _professional_collector
