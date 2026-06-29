"""Circuit breaker and resilience patterns for external service calls.

Provides:
- Retry with exponential backoff for transient failures
- Circuit breaker states (CLOSED → OPEN → HALF_OPEN → CLOSED)
- Graceful degradation fallbacks (price cache, order queuing)
- Business metrics for circuit state

Usage:
    from core.resilience import with_retry, CircuitBreaker

    @with_retry(service="datahub")
    def fetch_price(ticker: str) -> float: ...

    cb = CircuitBreaker("datahub", failure_threshold=3, recovery_timeout=30)
    price = cb.call(fetch_price, "AAPL")
"""

from __future__ import annotations

import logging as _stdlib_logging
import time
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
from typing import Any, Callable, TypeVar

from core.config.logging_config import get_logger
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_log,
    after_log,
)

logger = get_logger(__name__)

F = TypeVar("F", bound=Callable[..., Any])

# ═══════════════════════════════════════════════════════════════
# Error Classification
# ═══════════════════════════════════════════════════════════════


class TransientError(Exception):
    """Error that may succeed on retry (network timeout, connection refused)."""


class PermanentError(Exception):
    """Error that will NOT succeed on retry (invalid input, auth failure)."""


def classify_error(exc: Exception) -> type[Exception]:
    """Classify an exception as transient or permanent."""
    exc_str = str(exc).lower()
    exc_type = type(exc).__name__.lower()

    permanent_patterns = [
        "validation",
        "invalid",
        "not found",
        "unauthorized",
        "forbidden",
        "auth",
        "permission",
        "keyerror",
        "attributeerror",
        "typeerror",
        "valueerror",
    ]
    for pattern in permanent_patterns:
        if pattern in exc_str or pattern in exc_type:
            return PermanentError

    transient_patterns = [
        "timeout",
        "connection",
        "refused",
        "unreachable",
        "temporarily",
        "busy",
        "overloaded",
        "rate limit",
        "too many",
        "service unavailable",
        "503",
        "502",
        "504",
    ]
    for pattern in transient_patterns:
        if pattern in exc_str or pattern in exc_type:
            return TransientError

    if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
        return TransientError

    return TransientError  # Default: safer to retry


# ═══════════════════════════════════════════════════════════════
# Retry Decorator
# ═══════════════════════════════════════════════════════════════


def with_retry(
    max_attempts: int = 3,
    min_wait: float = 0.5,
    max_wait: float = 10.0,
    service: str = "unknown",
):
    """Decorator: retry on transient errors with exponential backoff."""

    def decorator(func: F) -> F:
        @retry(
            stop=stop_after_attempt(max_attempts),
            wait=wait_exponential(multiplier=1, min=min_wait, max=max_wait),
            retry=retry_if_exception_type(TransientError),
            before=before_log(logger, _stdlib_logging.DEBUG),
            after=after_log(logger, _stdlib_logging.DEBUG),
        )
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return func(*args, **kwargs)
            except PermanentError:
                raise
            except Exception as exc:
                error_class = classify_error(exc)
                if error_class is TransientError:
                    logger.warning(
                        "transient_error_retrying",
                        service=service,
                        func=func.__name__,
                        error=str(exc)[:200],
                    )
                    raise TransientError(str(exc)) from exc
                else:
                    logger.error(
                        "permanent_error_not_retrying",
                        service=service,
                        func=func.__name__,
                        error=str(exc)[:200],
                    )
                    raise PermanentError(str(exc)) from exc

        return wrapper  # type: ignore[return-value]

    return decorator


# ═══════════════════════════════════════════════════════════════
# Circuit Breaker
# ═══════════════════════════════════════════════════════════════


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(Exception):
    """Raised when a circuit is OPEN and rejecting calls."""


@dataclass
class CircuitBreaker:
    """Circuit breaker with CLOSED → OPEN → HALF_OPEN → CLOSED lifecycle."""

    name: str
    failure_threshold: int = 3
    recovery_timeout: float = 30.0

    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    last_failure_time: float = 0.0
    last_success_time: float = 0.0
    total_failures: int = 0
    total_successes: int = 0

    def call(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Call a function through the circuit breaker."""
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                logger.info("circuit_half_open", circuit=self.name)
            else:
                raise CircuitOpenError(
                    f"Circuit {self.name} is OPEN. "
                    f"Retry in {self.recovery_timeout - (time.time() - self.last_failure_time):.0f}s"
                )

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as exc:
            self._on_failure(exc)
            raise

    def _on_success(self) -> None:
        self.failure_count = 0
        self.last_success_time = time.time()
        self.total_successes += 1
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.CLOSED
            logger.info("circuit_closed", circuit=self.name)

    def _on_failure(self, exc: Exception) -> None:
        self.failure_count += 1
        self.total_failures += 1
        self.last_failure_time = time.time()
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
            logger.warning("circuit_reopened", circuit=self.name, error=str(exc)[:200])
        elif self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            logger.error(
                "circuit_opened",
                circuit=self.name,
                failures=self.failure_count,
                error=str(exc)[:200],
            )

    @property
    def is_open(self) -> bool:
        return self.state == CircuitState.OPEN

    @property
    def health(self) -> dict[str, Any]:
        return {
            "circuit": self.name,
            "state": self.state.value,
            "failures": self.failure_count,
            "total_failures": self.total_failures,
            "total_successes": self.total_successes,
            "last_failure": self.last_failure_time,
            "last_success": self.last_success_time,
        }


# ═══════════════════════════════════════════════════════════════
# Global Registry
# ═══════════════════════════════════════════════════════════════

_circuits: dict[str, CircuitBreaker] = {}


def get_circuit(name: str, **kwargs: Any) -> CircuitBreaker:
    """Get or create a named circuit breaker."""
    if name not in _circuits:
        _circuits[name] = CircuitBreaker(name=name, **kwargs)
    return _circuits[name]


def get_all_circuits_health() -> list[dict[str, Any]]:
    """Get health status of all circuit breakers."""
    return [cb.health for cb in _circuits.values()]


# ═══════════════════════════════════════════════════════════════
# Price Cache Fallback (graceful degradation)
# ═══════════════════════════════════════════════════════════════

_price_cache: dict[str, tuple[float, float]] = {}
_CACHE_TTL = 300  # 5 minutes


def cache_price(ticker: str, price: float) -> None:
    """Cache a price for graceful degradation when DataHub is down."""
    _price_cache[ticker.upper()] = (price, time.time())


def get_cached_price(ticker: str) -> tuple[float, bool]:
    """Get cached price. Returns (price, is_stale)."""
    entry = _price_cache.get(ticker.upper())
    if entry is None:
        return 0.0, True
    price, ts = entry
    is_stale = (time.time() - ts) > _CACHE_TTL
    return price, is_stale
