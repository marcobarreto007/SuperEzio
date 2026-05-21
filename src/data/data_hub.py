"""
SuperEzio Data Hub.

The hub is a routing layer, not a provider implementation. Providers know how
to fetch data from one source; the hub knows which provider to try for a given
capability and how to fall back when one source fails.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

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


def _make_quantum_walk() -> Any:
    from adapters.quantum.quantum_adapter import make_quantum_walk

    return make_quantum_walk()


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
                priority=20,
                required_key="TWELVE_DATA_API_KEY",
            )
        )

        self.register_provider(
            ProviderRoute(
                name="alpha_vantage",
                capabilities=(
                    "price",
                    "market_price",
                    "quote",
                    "candles",
                    "profile",
                    "treasury",
                ),
                factory=lambda: _make_alpha_vantage_provider(
                    self._get_key("ALPHA_VANTAGE_API_KEY")
                ),
                methods={
                    "price": "get_quote",
                    "market_price": "get_quote",
                    "quote": "get_quote",
                    "candles": "get_ohlcv",
                    "profile": "get_profile",
                    "treasury": "get_treasury_yield",
                },
                priority=10,
                required_key="ALPHA_VANTAGE_API_KEY",
            )
        )

        self.register_provider(
            ProviderRoute(
                name="news_scout",
                capabilities=("news", "sentiment"),
                factory=_make_news_scout,
                methods={"news": "get_news", "sentiment": "get_sentiment_summary"},
                priority=20,
                # NewsScout has free RSS/DDG fallbacks; NEWSAPI is optional.
                required_key=None,
            )
        )

        self.register_provider(
            ProviderRoute(
                name="reddit_pulse",
                capabilities=("reddit", "social_sentiment"),
                factory=_make_reddit_pulse,
                methods={"reddit": "get_signal", "social_sentiment": "get_signal"},
                priority=20,
                required_key=None,
            )
        )

        self.register_provider(
            ProviderRoute(
                name="quantum",
                capabilities=("quantum",),
                factory=_make_quantum_walk,
                methods={"quantum": "run_simulation"},
                priority=50,
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

        # ── NewsAPI (tested, working key) ────────────────────────────
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
                priority=5,  # Highest priority — real headlines, not scraped
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
        """
        attempts: list[dict[str, str]] = []
        for route in self.resolve(capability):
            provider = self.get_provider(route.name)
            if provider is None:
                attempts.append({"provider": route.name, "error": "provider_unavailable"})
                continue

            method_name = route.methods.get(capability)
            method = getattr(provider, method_name or "", None)
            if not callable(method):
                attempts.append({"provider": route.name, "error": "method_unavailable"})
                continue

            try:
                result = method(*args, **kwargs)
            except Exception as exc:
                attempts.append({"provider": route.name, "error": str(exc)})
                continue

            if self._is_usable_result(result):
                if isinstance(result, dict):
                    result.setdefault("provider", route.name)
                return result

            attempts.append(
                {
                    "provider": route.name,
                    "error": self._result_error(result) or "empty_result",
                }
            )

        return {"error": f"no_provider_result_for_{capability}", "attempts": attempts}

    @staticmethod
    def _is_usable_result(result: Any) -> bool:
        if result is None:
            return False
        if isinstance(result, dict):
            return "error" not in result
        if isinstance(result, list):
            return len(result) > 0
        return True

    @staticmethod
    def _result_error(result: Any) -> str:
        if isinstance(result, dict):
            return str(result.get("error") or "")
        return ""

    def get_price(self, symbol: str) -> Dict[str, Any]:
        """Route price lookup across configured market data providers."""
        return self.route("price", symbol)

    def get_quote(self, symbol: str) -> Dict[str, Any]:
        """Route quote lookup across configured quote providers."""
        return self.route("quote", symbol)

    def get_candles(self, symbol: str, timeframe: str = "6M") -> Dict[str, Any]:
        """Route OHLCV candles across configured providers."""
        return self.route("candles", symbol, timeframe=timeframe)

    def get_profile(self, symbol: str) -> Dict[str, Any]:
        """Route company profile across configured providers."""
        return self.route("profile", symbol)

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

    def run_quantum_simulation(self) -> Dict[str, Any]:
        return self.route("quantum")

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
