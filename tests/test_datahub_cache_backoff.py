"""Regression T1: DataHub short-TTL cache + rate-limit backoff.

Covers two resilience behaviors added to ``DataHub.route`` after the
2026-08-22 scan failure (24 candidates rejected as "price unavailable"):
  1. Successful price/quote/candles results are deduped per symbol for a
     short TTL (60s) so repeated calls inside one scan cycle do not hammer
     free-tier providers (TwelveData ~8 req/min, AlphaVantage ~25 req/day).
  2. Rate-limit responses ("429" / "credit limit" / "rate limit") count
     toward the provider circuit breaker, so an exhausted free tier backs
     off for 30s instead of being hit on every call.

No live API is touched — providers are test doubles.
"""

from __future__ import annotations

import uuid

from data.data_hub import DataHub, ProviderRoute


class _CountingPriceProvider:
    """Price provider that counts invocations per symbol."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.error: str | None = None

    def get_price(self, symbol: str) -> dict:
        self.calls.append(symbol)
        if self.error:
            return {"error": self.error}
        return {"price": 42.0, "symbol": symbol}

    def get_candles(self, symbol: str, timeframe: str = "6M") -> dict:
        self.calls.append(f"{symbol}:{timeframe}")
        return {"symbol": symbol, "timeframe": timeframe, "candles": [{"close": 42.0}]}


def _hub_with(provider) -> DataHub:
    hub = DataHub(register_defaults=False)
    hub.register_provider(
        ProviderRoute(
            name="counting_provider",
            capabilities=("price", "candles"),
            factory=lambda: provider,
            methods={"price": "get_price", "candles": "get_candles"},
            priority=1,
        )
    )
    return hub


def test_price_success_is_cached_per_symbol() -> None:
    provider = _CountingPriceProvider()
    hub = _hub_with(provider)

    first = hub.get_price("AAPL")
    second = hub.get_price("AAPL")

    assert first["price"] == 42.0
    assert second["price"] == 42.0
    assert provider.calls == ["AAPL"], "repeat call must be a cache hit"

    hub.get_price("MSFT")
    assert provider.calls == ["AAPL", "MSFT"], "distinct symbols stay distinct keys"


def test_candles_cache_key_includes_timeframe() -> None:
    provider = _CountingPriceProvider()
    hub = _hub_with(provider)

    hub.get_candles("AAPL", timeframe="6M")
    hub.get_candles("AAPL", timeframe="6M")
    hub.get_candles("AAPL", timeframe="1M")

    assert provider.calls == ["AAPL:6M", "AAPL:1M"], "timeframe is part of the cache key"


def test_failed_results_are_not_cached() -> None:
    provider = _CountingPriceProvider()
    provider.error = "boom"
    hub = _hub_with(provider)

    failed = hub.get_price("AAPL")
    assert "error" in failed

    provider.error = None
    ok = hub.get_price("AAPL")
    assert ok["price"] == 42.0
    assert provider.calls == ["AAPL", "AAPL"], "error result must not be cached"

    hub.get_price("AAPL")
    assert provider.calls == ["AAPL", "AAPL"], "success must be cached afterwards"


def test_cache_hit_returns_copy_not_shared_object() -> None:
    provider = _CountingPriceProvider()
    hub = _hub_with(provider)

    hub.get_price("AAPL")
    result = hub.get_price("AAPL")
    result["mutated"] = True

    again = hub.get_price("AAPL")
    assert "mutated" not in again, "cache entry must not be mutated by callers"


def test_cache_is_per_instance_not_global() -> None:
    provider_a = _CountingPriceProvider()
    provider_b = _CountingPriceProvider()

    hub_a = _hub_with(provider_a)
    hub_b = _hub_with(provider_b)

    hub_a.get_price("AAPL")
    result_b = hub_b.get_price("AAPL")

    assert provider_a.calls == ["AAPL"]
    assert provider_b.calls == ["AAPL"], "separate hub instances must not share cache"
    assert result_b["provider"] == "counting_provider"


def test_rate_limit_response_opens_circuit_and_falls_back() -> None:
    """Exhausted free tier: after `failure_threshold` hits, the provider is
    skipped (circuit_open) and the chain falls through to the fallback."""

    class _RateLimitedProvider:
        def __init__(self) -> None:
            self.calls = 0

        def get_price(self, symbol: str) -> dict:
            self.calls += 1
            return {"error": "API rate limit exceeded (credit limit reached)"}

    class _FallbackProvider:
        def get_price(self, symbol: str) -> dict:
            return {"price": 5.0, "symbol": symbol}

    rate_limited = _RateLimitedProvider()
    fallback = _FallbackProvider()
    # Unique names: the circuit registry is global with a 30s recovery
    # timeout, so a fast re-run must not collide with a stale OPEN circuit.
    suffix = uuid.uuid4().hex[:8]
    hub = DataHub(register_defaults=False)
    hub.register_provider(
        ProviderRoute(
            name=f"rate_limited_t1_{suffix}",
            capabilities=("price",),
            factory=lambda: rate_limited,
            methods={"price": "get_price"},
            priority=1,
        )
    )
    hub.register_provider(
        ProviderRoute(
            name=f"fallback_t1_{suffix}",
            capabilities=("price",),
            factory=lambda: fallback,
            methods={"price": "get_price"},
            priority=2,
        )
    )

    # Distinct symbols → distinct cache keys, so the circuit (not the cache)
    # is what absorbs the repeated hammering.
    results = [hub.get_price(symbol) for symbol in ("AAA", "BBB", "CCC", "DDD")]

    assert all(r["price"] == 5.0 for r in results), "fallback must win every call"
    assert rate_limited.calls == 3, (
        "rate-limited provider must back off after failure_threshold=3, "
        f"got {rate_limited.calls} calls"
    )

    fourth = results[3]
    assert "attempts" not in fourth, "successful fallback result has no attempts"

    # Prove the 4th call skipped the primary via the circuit, not the cache.
    probe = hub.route("price", "EEE")
    assert probe["price"] == 5.0
    assert rate_limited.calls == 3, "circuit must stay open (no more primary calls)"


def test_is_rate_limit_signal_matches_provider_error_messages() -> None:
    assert DataHub._is_rate_limit_signal("http_429")
    assert DataHub._is_rate_limit_signal("API rate limit exceeded")
    assert DataHub._is_rate_limit_signal("You have reached your credit limit")
    assert DataHub._is_rate_limit_signal("Too many requests, retry later")
    assert not DataHub._is_rate_limit_signal("no_quote")
    assert not DataHub._is_rate_limit_signal("empty_result")
    assert not DataHub._is_rate_limit_signal("")
