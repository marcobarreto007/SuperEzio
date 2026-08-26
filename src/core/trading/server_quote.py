"""Two-source server-side quote consensus for live-manual trade tickets."""

from __future__ import annotations

import concurrent.futures
import hashlib
import inspect
import json
import math
import os
from datetime import UTC, datetime
from statistics import median
from typing import Any

from tenacity import Retrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from core.resilience import get_circuit

_EXCHANGE_ALIASES = {
    "ASE": "AMEX",
    "NCM": "NASDAQ",
    "NGM": "NASDAQ",
    "NMS": "NASDAQ",
    "NYQ": "NYSE",
    "TOR": "TSX",
    "TSX VENTURE": "TSXV",
    "VAN": "TSXV",
}


class ServerQuoteError(RuntimeError):
    """Raised when a live quote cannot be independently verified."""


class TransientQuoteError(ServerQuoteError):
    """Network, timeout, rate-limit, or temporary provider failure."""


class PermanentQuoteError(ServerQuoteError):
    """Invalid symbol, authorization, or unusable provider payload."""


def _positive_float(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise PermanentQuoteError(f"{field} is not numeric") from exc
    if not math.isfinite(number) or number <= 0:
        raise PermanentQuoteError(f"{field} is not positive and finite")
    return number


def _positive_env_float(name: str, default: str) -> float:
    try:
        number = float(os.getenv(name, default))
    except ValueError as exc:
        raise ServerQuoteError(f"{name} must be numeric") from exc
    if not math.isfinite(number) or number <= 0:
        raise ServerQuoteError(f"{name} must be positive and finite")
    return number


def _parse_as_of(value: Any) -> datetime:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=UTC)
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except ValueError as exc:
        raise PermanentQuoteError("provider quote timestamp is missing or invalid") from exc
    if parsed.tzinfo is None:
        raise PermanentQuoteError("provider quote timestamp must include timezone")
    return parsed.astimezone(UTC)


def _normalize_exchange(value: Any) -> str:
    exchange = str(value or "").strip().upper()
    return _EXCHANGE_ALIASES.get(exchange, exchange)


def _provider_symbol(symbol: str, exchange: str) -> str:
    clean = symbol.strip().upper()
    if exchange == "TSX" and not clean.endswith(".TO"):
        return f"{clean}.TO"
    if exchange == "TSXV" and not clean.endswith(".V"):
        return f"{clean}.V"
    return clean


def _classify_provider_error(provider: str, error: Any) -> ServerQuoteError:
    text = str(error or "unknown_provider_error").lower()
    transient_markers = ("429", "timeout", "timed out", "connection", "tempor", "http_5")
    error_type = (
        TransientQuoteError
        if any(marker in text for marker in transient_markers)
        else PermanentQuoteError
    )
    return error_type(f"{provider}: {text[:200]}")


class ServerQuoteService:
    """Fetch provider-specific quotes and return fail-closed consensus evidence."""

    def __init__(
        self,
        data_hub: Any,
        *,
        providers: tuple[str, ...] = ("twelve_data", "finnhub", "yfinance"),
        circuit_namespace: str = "trusted_quote",
    ) -> None:
        self.data_hub = data_hub
        self.providers = providers
        self.circuit_namespace = circuit_namespace

    def _fetch_once(self, provider_name: str, symbol: str, exchange: str) -> dict[str, Any]:
        provider = self.data_hub.get_provider(provider_name)
        if provider is None:
            raise PermanentQuoteError(f"{provider_name}: provider_unavailable")
        method = getattr(provider, "get_price", None)
        if not callable(method):
            raise PermanentQuoteError(f"{provider_name}: get_price_unavailable")
        signature = inspect.signature(method)
        accepts_kwargs = any(
            parameter.kind is inspect.Parameter.VAR_KEYWORD
            for parameter in signature.parameters.values()
        )
        kwargs = {
            name: exchange
            for name in ("market", "exchange")
            if accepts_kwargs or name in signature.parameters
        }
        result = method(symbol, **kwargs)
        if not isinstance(result, dict):
            raise PermanentQuoteError(f"{provider_name}: non_object_result")
        if result.get("error"):
            raise _classify_provider_error(provider_name, result["error"])
        return result

    def _fetch_with_resilience(
        self, provider_name: str, symbol: str, exchange: str
    ) -> dict[str, Any]:
        circuit = get_circuit(
            f"{self.circuit_namespace}.{provider_name}",
            failure_threshold=3,
            recovery_timeout=30,
        )
        retrying = Retrying(
            stop=stop_after_attempt(2),
            wait=wait_exponential(multiplier=0.1, min=0.1, max=0.5),
            retry=retry_if_exception_type(TransientQuoteError),
            reraise=True,
        )
        for attempt in retrying:
            with attempt:
                return circuit.call(self._fetch_once, provider_name, symbol, exchange)
        raise TransientQuoteError(f"{provider_name}: retries exhausted")  # pragma: no cover

    def resolve(
        self,
        *,
        symbol: str,
        exchange: str,
        currency: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        current = (now or datetime.now(UTC)).astimezone(UTC)
        requested_exchange = _normalize_exchange(exchange)
        requested_currency = currency.strip().upper()
        lookup_symbol = _provider_symbol(symbol, requested_exchange)
        max_workers = max(1, min(len(self.providers), 3))
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
        futures = {
            executor.submit(
                self._fetch_with_resilience,
                provider_name,
                lookup_symbol,
                requested_exchange,
            ): provider_name
            for provider_name in self.providers
        }
        raw_results: list[tuple[str, dict[str, Any]]] = []
        errors: dict[str, str] = {}
        timeout = _positive_env_float("SUPEREZIO_TRUSTED_QUOTE_TOTAL_TIMEOUT_SEC", "15")
        try:
            for future in concurrent.futures.as_completed(futures, timeout=timeout):
                provider_name = futures[future]
                try:
                    raw_results.append((provider_name, future.result()))
                except Exception as exc:
                    errors[provider_name] = str(exc)[:240]
        except TimeoutError:
            for future, provider_name in futures.items():
                if not future.done():
                    future.cancel()
                    errors[provider_name] = "provider_timeout"
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

        max_age = _positive_env_float("SUPEREZIO_TRUSTED_QUOTE_MAX_AGE_SEC", "90")
        normalized: list[dict[str, Any]] = []
        for provider_name, result in raw_results:
            try:
                price = _positive_float(result.get("price"), "provider price")
                as_of = _parse_as_of(
                    result.get("as_of")
                    or result.get("last_update_at")
                    or result.get("market_timestamp")
                    or result.get("timestamp")
                )
                age_seconds = (current - as_of).total_seconds()
                if age_seconds < -5:
                    raise PermanentQuoteError("provider quote timestamp is in the future")
                if age_seconds > max_age:
                    raise PermanentQuoteError(
                        f"provider quote is stale ({age_seconds:.1f}s > {max_age:.1f}s)"
                    )
                provider_exchange = _normalize_exchange(result.get("exchange"))
                provider_currency = str(result.get("currency") or "").strip().upper()
                if provider_exchange and provider_exchange != requested_exchange:
                    raise PermanentQuoteError(
                        f"exchange mismatch {provider_exchange} != {requested_exchange}"
                    )
                if provider_currency and provider_currency != requested_currency:
                    raise PermanentQuoteError(
                        f"currency mismatch {provider_currency} != {requested_currency}"
                    )
                normalized.append(
                    {
                        "provider": provider_name,
                        "price": round(price, 6),
                        "as_of": as_of.isoformat(),
                        "age_seconds": round(max(0.0, age_seconds), 3),
                        "exchange": provider_exchange or None,
                        "currency": provider_currency or None,
                        "exchange_verified": provider_exchange == requested_exchange,
                        "currency_verified": provider_currency == requested_currency,
                        "server_acquired_at": current.isoformat(),
                    }
                )
            except ServerQuoteError as exc:
                errors[provider_name] = str(exc)

        minimum_sources = int(os.getenv("SUPEREZIO_TRUSTED_QUOTE_MIN_SOURCES", "2"))
        if minimum_sources < 2:
            raise ServerQuoteError("SUPEREZIO_TRUSTED_QUOTE_MIN_SOURCES cannot be below 2")
        unique_providers = {item["provider"] for item in normalized}
        if len(unique_providers) < minimum_sources:
            raise ServerQuoteError(
                f"insufficient independent quotes: {len(unique_providers)}/{minimum_sources}; {errors}"
            )
        if not any(item["exchange_verified"] for item in normalized):
            raise ServerQuoteError("no provider verified the requested exchange")
        if not any(item["currency_verified"] for item in normalized):
            raise ServerQuoteError("no provider verified the requested currency")

        prices = [float(item["price"]) for item in normalized]
        consensus_price = float(median(prices))
        divergence_pct = (max(prices) - min(prices)) / consensus_price * 100
        max_divergence = _positive_env_float("SUPEREZIO_TRUSTED_QUOTE_MAX_DIVERGENCE_PCT", "0.75")
        if divergence_pct > max_divergence:
            raise ServerQuoteError(
                f"provider divergence {divergence_pct:.4f}% exceeds {max_divergence:.4f}%"
            )
        conservative_as_of = min(_parse_as_of(item["as_of"]) for item in normalized)
        evidence = {
            "symbol": symbol.strip().upper(),
            "provider_symbol": lookup_symbol,
            "exchange": requested_exchange,
            "currency": requested_currency,
            "price": round(consensus_price, 6),
            "as_of": conservative_as_of.isoformat(),
            "server_acquired_at": current.isoformat(),
            "sources": sorted(normalized, key=lambda item: item["provider"]),
            "source_count": len(unique_providers),
            "divergence_pct": round(divergence_pct, 6),
            "max_divergence_pct": max_divergence,
            "trust": "SERVER_VERIFIED_CONSENSUS",
            "stale_fallback_used": False,
        }
        evidence["evidence_hash"] = hashlib.sha256(
            json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return evidence


def resolve_server_quote(
    payload: dict[str, Any],
    *,
    data_hub: Any,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Resolve a trusted quote from a validated TD draft request shape."""

    return ServerQuoteService(data_hub).resolve(
        symbol=str(payload.get("ticker") or ""),
        exchange=str(payload.get("exchange") or ""),
        currency=str(payload.get("currency") or ""),
        now=now,
    )
