"""
SuperEzio Data Hub.

The hub is a routing layer, not a provider implementation. Providers know how
to fetch data from one source; the hub knows which provider to try for a given
capability and how to fall back when one source fails.
"""

from __future__ import annotations

import inspect
import json
import logging
import math
import os
import subprocess
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from core.resilience import get_circuit, CircuitOpenError

ProviderFactory = Callable[[], Any]
logger = logging.getLogger(__name__)


def _make_twelve_data_provider(api_key: str | None) -> Any:
    from .twelve_data import TwelveDataProvider

    return TwelveDataProvider(api_key=api_key)


def _make_alpha_vantage_provider(api_key: str | None) -> Any:
    from .alpha_vantage import AlphaVantageProvider

    return AlphaVantageProvider(api_key=api_key)


def _make_news_scout() -> Any:
    from .news_feed import NewsScout

    return NewsScout()


def _make_reddit_pulse() -> Any:
    from .reddit_provider import RedditPulse

    return RedditPulse()


def _make_boc_provider() -> Any:
    from .boc_provider import get_macro_summary_ca

    return type("BocProvider", (), {"get_macro_summary": staticmethod(get_macro_summary_ca)})()


def _make_fed_provider() -> Any:
    from .fed_provider import get_macro_summary_us

    return type("FedProvider", (), {"get_macro_summary": staticmethod(get_macro_summary_us)})()


def _make_newsapi_provider() -> Any:
    from .newsapi_provider import NewsAPIProvider

    return NewsAPIProvider()


def _make_wolfram_provider() -> Any:
    from .wolfram_provider import WolframProvider

    return WolframProvider()


def _make_finnhub_provider(api_key: str | None) -> Any:
    from .finnhub_provider import FinnhubProvider

    return FinnhubProvider(api_key=api_key)


def _make_yfinance_provider() -> Any:
    from .yfinance_provider import YFinanceProvider

    return YFinanceProvider()


# Stooq provider removed 2026-07-20 — API offline (HTTP 404 on all endpoints)


def _make_akshare_provider() -> Any:
    from .akshare_provider import AKShareProvider

    return AKShareProvider()


def _make_alphasmo_provider() -> Any:
    from .alphasmo_provider import AlphaSMOProvider

    return AlphaSMOProvider()


def _make_apewisdom_provider() -> Any:
    from .apewisdom_provider import ApeWisdomProvider

    return ApeWisdomProvider()


def _make_form4api_provider(api_key: str | None) -> Any:
    from .form4api_provider import Form4APIProvider

    return Form4APIProvider(api_key=api_key)


def _make_social_whale_provider() -> Any:
    from .social_whale_provider import SocialWhaleProvider

    return SocialWhaleProvider()


@dataclass(frozen=True)
class ProviderRoute:
    """Metadata needed to route one capability to one provider."""

    name: str
    capabilities: tuple[str, ...]
    factory: ProviderFactory
    methods: Dict[str, str]
    priority: int = 100
    required_key: str | None = None
    enabled: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


class DataHub:
    """
    Capability-based router for data providers.

    Public compatibility surface kept:
      - get_provider(name)
      - list_active()
      - check_health()
      - search_web()/extract_web()
    """

    def __init__(self, *, register_defaults: bool = True) -> None:
        try:
            from core.config.secrets import load_local_env

            load_local_env()
        except ImportError:
            pass

        self._key_names = [
            "TWELVE_DATA_API_KEY",
            "ALPHA_VANTAGE_API_KEY",
            "HUGGINGFACE_API_KEY",
            "WOLFRAM_API_KEY",
            "NEWSAPI_KEY",
            "COINGECKO_API_KEY",
            "THE_ODDS_API_KEY",
            "MARKET_DATA_API_KEY",
            "MARKET_DATA_API_KEY_2",
            "OPENAI_API_KEY",
            "TAVILY_API_KEY",
            "BRAVE_SEARCH_API_KEY",
            "FINNHUB_API_KEY",
            "FORM4API_KEY",
        ]

        self.tavily_search_path = os.getenv("SUPEREZIO_TAVILY_SEARCH_PATH") or ""
        self.tavily_extract_path = os.getenv("SUPEREZIO_TAVILY_EXTRACT_PATH") or ""

        self.routes: Dict[str, ProviderRoute] = {}
        self.providers: Dict[str, Any] = {}
        if register_defaults:
            self._register_default_routes()

    def _get_key(self, name: str) -> str | None:
        """Lê chave do ambiente no momento da consulta (lazy, suporta dotenv)."""
        return os.getenv(name)

    def _keys(self) -> dict[str, str | None]:
        """Snapshot atual de todas as chaves."""
        return {name: os.getenv(name) for name in self._key_names}

    def _register_default_routes(self) -> None:
        # Market data — price chain (cross-provider tested 2026-07-20):
        #   1) Twelve Data  (fast 0.69s, accurate, key exists)     [US stocks OK]
        #  30) YFinance     (fast 0.47s, free, always available)   [PRIMARY fallback]
        #   3) Alpha Vantage (price OK, volume 200%+ WRONG!)       [BDR coverage]
        # AKShare REMOVED from price (downloads 893 stocks, 3+ min!)
        # Stooq REMOVED 2026-07-20: API offline (HTTP 404)
        # Finnhub: key invalid (b444a4ae), registered for quote/news only
        #
        # Quote / profile / fundamentals / news — Finnhub primary at priority 1
        #
        # Sentiment chain:
        #   1) ApeWisdom   (retail Reddit/WSB — most relevant for Mangala)
        #   2) NewsAPI     (traditional news)
        #   3) RedditPulse (social signals)
        #
        # Insider / smart-money chain:
        #   1) AlphaSMO  (smart-money convergence, keyless)
        #   2) Form4API  (SEC Form 4 cluster detection, free tier)
        self.register_provider(
            ProviderRoute(
                name="finnhub",
                capabilities=(
                    "quote",
                    "profile",
                    "fundamentals",
                    "short_term_catalyst",
                    "candles",
                    "news",
                ),
                factory=lambda: _make_finnhub_provider(self._get_key("FINNHUB_API_KEY")),
                methods={
                    "quote": "get_quote",
                    "profile": "get_profile",
                    "fundamentals": "get_fundamentals",
                    "short_term_catalyst": "get_short_term_catalyst",
                    "candles": "get_candles",
                    "news": "get_news",
                },
                priority=1,
                required_key="FINNHUB_API_KEY",
                metadata={"role": "primary_market_data"},
            )
        )

        self.register_provider(
            ProviderRoute(
                name="twelve_data",
                capabilities=("price", "market_price", "candles"),
                factory=lambda: _make_twelve_data_provider(self._get_key("TWELVE_DATA_API_KEY")),
                methods={
                    "price": "get_price",
                    "market_price": "get_price",
                    "candles": "get_candles",
                },
                priority=1,
                required_key="TWELVE_DATA_API_KEY",
                metadata={"role": "primary_market_data"},
            )
        )

        self.register_provider(
            ProviderRoute(
                name="yfinance",
                capabilities=("price", "market_price", "candles", "profile"),
                factory=_make_yfinance_provider,
                methods={
                    "price": "get_price",
                    "market_price": "get_price",
                    "candles": "get_candles",
                    "profile": "get_profile",
                },
                priority=30,
                required_key=None,
                metadata={"role": "last_resort_market_data"},
            )
        )

        self.register_provider(
            ProviderRoute(
                name="alpha_vantage",
                capabilities=("price", "market_price", "treasury"),
                factory=lambda: _make_alpha_vantage_provider(
                    self._get_key("ALPHA_VANTAGE_API_KEY")
                ),
                methods={
                    "price": "get_quote",
                    "market_price": "get_quote",
                    "treasury": "get_treasury_yield",
                },
                priority=3,
                required_key="ALPHA_VANTAGE_API_KEY",
                metadata={"role": "price_and_treasury"},
            )
        )

        # Stooq REMOVED — API offline (HTTP 404 on all endpoints, 2026-07-20)

        # ── AKShare (free US stock OHLCV, keyless) ────────────────────────
        self.register_provider(
            ProviderRoute(
                name="akshare",
                capabilities=("candles", "profile"),  # price removed: downloads 893 stocks (3+ min!)
                factory=_make_akshare_provider,
                methods={
                    "candles": "get_candles",
                    "profile": "get_profile",
                },
                priority=2,
                required_key=None,
                metadata={"role": "secondary_market_data"},
            )
        )

        # ── AlphaSMO (free insider + smart-money, keyless) ────────────────
        self.register_provider(
            ProviderRoute(
                name="alphasmo",
                capabilities=("insider_trades", "smart_money"),
                factory=_make_alphasmo_provider,
                methods={
                    "insider_trades": "get_insider_trades",
                    "smart_money": "get_smart_money_convergence",
                },
                priority=1,
                required_key=None,
                metadata={"role": "primary_insider_smart_money"},
            )
        )

        # ── ApeWisdom (retail sentiment, Reddit/WSB trending) ─────────
        self.register_provider(
            ProviderRoute(
                name="apewisdom",
                capabilities=("sentiment", "retail_sentiment", "trending"),
                factory=_make_apewisdom_provider,
                methods={
                    "sentiment": "get_sentiment",
                    "retail_sentiment": "get_retail_buzz",
                    "trending": "get_trending_stocks",
                },
                priority=1,
                required_key=None,
                metadata={"role": "primary_sentiment"},
            )
        )

        # ── SocialWhale (whale signals, pump detection, social sentiment) ─
        self.register_provider(
            ProviderRoute(
                name="social_whale",
                capabilities=(
                    "whale_signals",
                    "pump_detection",
                    "social_sentiment",
                    "unusual_options_flow",
                ),
                factory=_make_social_whale_provider,
                methods={
                    "whale_signals": "get_whale_signals",
                    "pump_detection": "get_pump_detection",
                    "social_sentiment": "get_social_sentiment",
                    "unusual_options_flow": "get_unusual_options_flow",
                },
                priority=1,
                required_key=None,
                metadata={"role": "social_whale_intelligence"},
            )
        )

        # ── Form4API (SEC insider trades — free tier) ────────────────
        self.register_provider(
            ProviderRoute(
                name="form4api",
                capabilities=("insider_trades",),
                factory=lambda: _make_form4api_provider(self._get_key("FORM4API_KEY")),
                methods={
                    "insider_trades": "get_insider_trades",
                },
                priority=2,
                required_key=None,  # FREE_TIER default works out of the box
                metadata={"role": "secondary_insider_trading", "free_tier_req_day": 500},
            )
        )

        self.register_provider(
            ProviderRoute(
                name="news_scout",
                capabilities=("news",),
                factory=_make_news_scout,
                methods={"news": "get_news", "sentiment": "get_sentiment_summary"},
                priority=22,
                required_key=None,
            )
        )

        self.register_provider(
            ProviderRoute(
                name="reddit_pulse",
                capabilities=("sentiment", "reddit", "social_sentiment"),
                factory=_make_reddit_pulse,
                methods={
                    "sentiment": "get_signal",
                    "reddit": "get_signal",
                    "social_sentiment": "get_signal",
                },
                priority=3,
                required_key=None,
                metadata={"role": "social_sentiment"},
            )
        )

        self.register_provider(
            ProviderRoute(
                name="boc_macro",
                capabilities=("macro", "macro_ca"),
                factory=_make_boc_provider,
                methods={"macro": "get_macro_summary", "macro_ca": "get_macro_summary"},
                priority=20,
                required_key=None,
            )
        )

        self.register_provider(
            ProviderRoute(
                name="fed_macro",
                capabilities=("macro", "macro_us"),
                factory=_make_fed_provider,
                methods={"macro": "get_macro_summary", "macro_us": "get_macro_summary"},
                priority=30,
                required_key=None,
            )
        )

        # News: Finnhub company-news first (see finnhub route), then NewsAPI, then RSS scouts.
        self.register_provider(
            ProviderRoute(
                name="newsapi",
                capabilities=("news", "sentiment", "market_sentiment"),
                factory=_make_newsapi_provider,
                methods={
                    "news": "get_news",
                    "sentiment": "get_sentiment_summary",
                    "market_sentiment": "get_market_sentiment",
                },
                priority=2,
                required_key="NEWSAPI_KEY",
            )
        )

        # ── Wolfram Alpha (tested, working key) ──────────────────────
        self.register_provider(
            ProviderRoute(
                name="wolfram",
                capabilities=("quantitative", "math_verify"),
                factory=_make_wolfram_provider,
                methods={
                    "quantitative": "query",
                    "math_verify": "query",
                },
                priority=30,
                required_key="WOLFRAM_API_KEY",
            )
        )

    def get_news_sentiment(self, symbol: str) -> Dict[str, Any]:
        """Get sentiment summary via NewsAPI (primary) or NewsScout (fallback)."""
        result = self.route("sentiment", symbol)
        if "error" not in result:
            return result
        # Fallback: NewsScout sentiment
        return self.get_sentiment_summary(symbol)

    def get_market_sentiment(self) -> Dict[str, Any]:
        """Get broad market sentiment from headlines."""
        return self.route("market_sentiment")

    def run_math_verify(self, expression: str) -> Dict[str, Any]:
        """Verify a mathematical expression via Wolfram Alpha."""
        return self.route("math_verify", expression)

    def register_provider(self, route: ProviderRoute) -> None:
        """Register a provider route without instantiating the provider."""
        self.routes[route.name] = route

    def _is_configured(self, route: ProviderRoute) -> bool:
        if not route.enabled:
            return False
        if route.required_key:
            return bool(self._get_key(route.required_key))
        return True

    def get_provider(self, name: str) -> Optional[Any]:
        """Return a lazy provider instance by name."""
        if name in self.providers:
            return self.providers[name]

        route = self.routes.get(name)
        if not route or not self._is_configured(route):
            return None

        try:
            provider = route.factory()
        except Exception as exc:
            logger.warning("[DATA_HUB] provider factory failed for %s: %s", route.name, exc)
            return None

        self.providers[name] = provider
        return provider

    def list_active(self) -> list[str]:
        """List active provider routes, not raw environment keys."""
        return [
            route.name
            for route in sorted(self.routes.values(), key=lambda item: item.priority)
            if self._is_configured(route)
        ]

    def list_routes(self, capability: str | None = None) -> list[dict[str, Any]]:
        """Return route metadata for diagnostics and UI/debugger surfaces."""
        routes = sorted(self.routes.values(), key=lambda item: item.priority)
        if capability:
            routes = [route for route in routes if capability in route.capabilities]
        return [
            {
                "name": route.name,
                "capabilities": list(route.capabilities),
                "priority": route.priority,
                "configured": self._is_configured(route),
                "required_key": route.required_key,
                "loaded": route.name in self.providers,
                **route.metadata,
            }
            for route in routes
        ]

    def check_health(self) -> Dict[str, Any]:
        """Report configured providers and raw key availability."""
        return {
            "providers": {
                route.name: self._is_configured(route)
                for route in sorted(self.routes.values(), key=lambda item: item.priority)
            },
            "keys": {name: bool(self._get_key(name)) for name in self._key_names},
        }

    def resolve(self, capability: str) -> list[ProviderRoute]:
        """Return configured routes that can satisfy a capability."""
        return [
            route
            for route in sorted(self.routes.values(), key=lambda item: item.priority)
            if capability in route.capabilities and self._is_configured(route)
        ]

    def route(self, capability: str, *args: Any, **kwargs: Any) -> Any:
        """
        Try providers for a capability in priority order.

        A dict containing an ``error`` key or an empty list is considered an
        unusable result and triggers the next fallback.

        Logs which provider was selected and why.
        """
        attempts: list[dict[str, str]] = []
        for route in self.resolve(capability):
            provider = self.get_provider(route.name)
            if provider is None:
                attempts.append({"provider": route.name, "error": "provider_unavailable"})
                logger.info("[DATA_HUB] %s: %s skipped — unavailable", capability, route.name)
                continue

            # ── Circuit breaker gate ──
            _cb = get_circuit(f"data.{route.name}", failure_threshold=3, recovery_timeout=30)
            if _cb.is_open:
                logger.warning(
                    "CIRCUIT_OPEN: %s after %d failures, falling back",
                    route.name,
                    _cb.failure_count,
                )
                attempts.append({"provider": route.name, "error": "circuit_open"})
                continue

            method_name = route.methods.get(capability)
            method = getattr(provider, method_name or "", None)
            if not callable(method):
                attempts.append({"provider": route.name, "error": "method_unavailable"})
                logger.info(
                    "[DATA_HUB] %s: %s skipped — method %s not found",
                    capability,
                    route.name,
                    method_name,
                )
                continue

            try:
                call_kwargs = self._kwargs_for_method(method, kwargs)
                import concurrent.futures as _cf
                with _cf.ThreadPoolExecutor(max_workers=1) as _executor:
                    _ft = _executor.submit(method, *args, **call_kwargs)
                    result = _ft.result(timeout=30)
            except _cf.TimeoutError:
                _cb._on_failure(TimeoutError(f"{route.name} timed out after 30s"))
                attempts.append({"provider": route.name, "error": "timeout_30s"})
                logger.warning("[DATA_HUB] %s: %s timeout (30s)", capability, route.name)
                continue
            except Exception as exc:
                _cb._on_failure(exc)
                attempts.append({"provider": route.name, "error": str(exc)})
                logger.warning("[DATA_HUB] %s: %s raised — %s", capability, route.name, exc)
                continue

            if self._is_usable_result(result, capability):
                if isinstance(result, dict):
                    result.setdefault("provider", route.name)
                logger.info("[DATA_HUB] %s: %s succeeded", capability, route.name)
                _cb._on_success()
                return result

            error = self._result_error(result) or "empty_result"
            attempts.append({"provider": route.name, "error": error})
            logger.info(
                "[DATA_HUB] %s: %s returned unusable result — %s",
                capability,
                route.name,
                error,
            )

        logger.warning("[DATA_HUB] %s: all providers exhausted — %s", capability, attempts)
        return {"error": f"no_provider_result_for_{capability}", "attempts": attempts}

    @staticmethod
    def _kwargs_for_method(method: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
        """Drop kwargs that the provider method does not accept (e.g. market=)."""
        if not kwargs:
            return {}
        try:
            sig = inspect.signature(method)
        except (TypeError, ValueError):
            return dict(kwargs)
        if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
            return dict(kwargs)
        allowed = set(sig.parameters.keys())
        return {k: v for k, v in kwargs.items() if k in allowed}

    @staticmethod
    def _is_usable_result(result: Any, capability: str | None = None) -> bool:
        """Validate that a provider returned data usable for the requested capability."""
        if result is None:
            return False
        if isinstance(result, dict):
            if "error" in result or not result:
                return False
            if capability in {"price", "market_price", "quote"}:
                return DataHub._positive_number(result.get("price"))
            if capability == "candles":
                candles = result.get("candles")
                return isinstance(candles, list) and any(
                    isinstance(candle, dict) and DataHub._positive_number(candle.get("close"))
                    for candle in candles
                )
            if capability == "profile":
                return bool(str(result.get("name") or "").strip())
            if capability == "fundamentals":
                metadata = {"symbol", "requested_symbol", "source", "provider"}
                return any(
                    key not in metadata and value is not None for key, value in result.items()
                )
            if capability == "treasury":
                return bool(result.get("data")) or DataHub._finite_number(result.get("yield"))
            return DataHub._has_meaningful_value(result)
        if isinstance(result, list):
            if capability == "news":
                return any(
                    isinstance(item, dict)
                    and bool(str(item.get("title") or item.get("headline") or "").strip())
                    for item in result
                )
            return any(DataHub._has_meaningful_value(item) for item in result)
        return DataHub._has_meaningful_value(result)

    @staticmethod
    def _finite_number(value: Any) -> bool:
        try:
            return math.isfinite(float(value))
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _positive_number(value: Any) -> bool:
        return DataHub._finite_number(value) and float(value) > 0

    @staticmethod
    def _has_meaningful_value(value: Any) -> bool:
        if value is None or value == "":
            return False
        if isinstance(value, dict):
            ignored = {"provider", "source", "symbol", "requested_symbol", "note"}
            return any(
                key not in ignored and DataHub._has_meaningful_value(item)
                for key, item in value.items()
            )
        if isinstance(value, (list, tuple, set)):
            return any(DataHub._has_meaningful_value(item) for item in value)
        return True

    @staticmethod
    def _result_error(result: Any) -> str:
        if isinstance(result, dict):
            return str(result.get("error") or "")
        return ""

    def get_price(self, symbol: str, **kwargs: Any) -> Dict[str, Any]:
        """Route price lookup across configured market data providers."""
        return self.route("price", symbol, **kwargs)

    def get_quote(self, symbol: str) -> Dict[str, Any]:
        """Route quote lookup across configured quote providers."""
        return self.route("quote", symbol)

    def get_candles(self, symbol: str, timeframe: str = "6M") -> Dict[str, Any]:
        """Route OHLCV candles across configured providers."""
        return self.route("candles", symbol, timeframe=timeframe)

    def get_profile(self, symbol: str) -> Dict[str, Any]:
        """Route company profile across configured providers."""
        return self.route("profile", symbol)

    def get_fundamentals(self, symbol: str) -> Dict[str, Any]:
        """Route fundamentals (P/E, Beta, EPS, margins, ROE) across configured providers."""
        return self.route("fundamentals", symbol)

    def get_treasury_yield(self, maturity: str = "10year") -> Dict[str, Any]:
        """Route treasury yield lookup."""
        return self.route("treasury", maturity)

    def get_news(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        result = self.route("news", query, limit=limit)
        return result if isinstance(result, list) else [result]

    def get_sentiment_summary(self, symbol: str) -> Dict[str, Any]:
        return self.route("sentiment", symbol)

    def get_reddit_signal(self, ticker: str) -> Dict[str, Any]:
        """Route Reddit social signal through reddit_pulse."""
        return self.route("reddit", ticker)

    def get_insider_trades(self, ticker: str) -> Dict[str, Any]:
        """Route insider-trades lookup (Form4API primary, AlphaSMO fallback)."""
        return self.route("insider_trades", ticker)

    def get_smart_money_convergence(
        self, limit: int = 20, min_confidence: int = 60, days: int = 90
    ) -> Dict[str, Any]:
        """Route smart-money convergence signal through AlphaSMO."""
        return self.route(
            "smart_money",
            limit=limit,
            min_confidence=min_confidence,
            days=days,
        )

    def run_quantum_simulation(self) -> Dict[str, Any]:
        """Compatibility tombstone for a removed no-input random simulation."""
        return {
            "status": "removed",
            "reason": "no_input_quantum_walk_was_not_a_market_model",
            "replacement": "MathHub.return_bootstrap_requires_observed_returns",
        }

    def get_macro(self, market: str = "US") -> Dict[str, Any]:
        """Route macro data by market (CA → BoC, US → Fed)."""
        cap = f"macro_{market.lower()}"
        result = self.route(cap)
        if "error" not in result:
            return result
        # Fallback: try generic macro capability
        return self.route("macro")

    def search_web(
        self,
        query: str,
        deep: bool = False,
        topic: str = "general",
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """Route web search through Tavily, then DuckDuckGo fallback."""
        if self._get_key("TAVILY_API_KEY") and self.tavily_search_path:
            try:
                cmd = ["node", self.tavily_search_path, query]
                if deep:
                    cmd.append("--deep")
                if topic == "news":
                    cmd.extend(["--topic", "news"])

                env = os.environ.copy()
                env["TAVILY_API_KEY"] = self._get_key("TAVILY_API_KEY") or ""
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    env=env,
                    check=True,
                    timeout=20,
                )
                parsed = json.loads(result.stdout)
                if isinstance(parsed, list) and parsed:
                    return parsed
            except Exception as exc:
                logger.warning("[DATA_HUB] Tavily search failed: %s", exc)
                pass

        return self.search_ddg(query, limit=limit)

    def search_ddg(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Free DuckDuckGo text search fallback."""
        try:
            from ddgs import DDGS

            with DDGS() as ddgs:
                return [
                    {
                        "title": item.get("title"),
                        "url": item.get("href"),
                        "content": item.get("body"),
                        "source": "duckduckgo",
                    }
                    for item in ddgs.text(query, max_results=limit)
                ]
        except Exception as exc:
            return [{"error": f"DDG Search failed: {exc}"}]

    def extract_web(self, url: str) -> Dict[str, Any]:
        """Extract page content through Tavily when configured."""
        if not self._get_key("TAVILY_API_KEY") or not self.tavily_extract_path:
            return {"error": "TAVILY not configured (missing API key or script path)"}

        cmd = ["node", self.tavily_extract_path, url]
        try:
            env = os.environ.copy()
            env["TAVILY_API_KEY"] = self._get_key("TAVILY_API_KEY") or ""
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                env=env,
                check=True,
                timeout=20,
            )
            parsed = json.loads(result.stdout)
            return parsed if isinstance(parsed, dict) else {"content": parsed}
        except Exception as exc:
            return {"error": str(exc)}


hub = DataHub()


if __name__ == "__main__":
    print("SuperEzio Data Hub iniciado.")
    print(f"Rotas ativas: {hub.list_active()}")
