"""Resilience utilities for pipeline nodes - circuit breaker, retry, timeout.

Usage:
    from core.pipeline.resilience import resilient_node, CircuitBreaker

    @resilient_node(max_retries=2, timeout_s=10.0)
    async def my_node(state, gateway=None):
        ...
"""

from __future__ import annotations

import asyncio
import functools
import logging
import time
from collections.abc import Callable
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


class CircuitBreaker:
    """Prevent cascading failures by breaking the circuit after threshold errors.

    States: CLOSED -> OPEN (after failures) -> HALF_OPEN -> CLOSED (after success)
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout_s: float = 30.0,
        half_open_max: int = 1,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout_s = recovery_timeout_s
        self.half_open_max = half_open_max
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._state = "CLOSED"
        self._half_open_attempts = 0

    @property
    def state(self) -> str:
        self._maybe_transition()
        return self._state

    def _maybe_transition(self):
        if self._state == "OPEN":
            if time.monotonic() - self._last_failure_time >= self.recovery_timeout_s:
                self._state = "HALF_OPEN"
                self._half_open_attempts = 0
                logger.info("CircuitBreaker(%s): OPEN -> HALF_OPEN", self.name)

    def success(self):
        if self._state == "HALF_OPEN":
            self._half_open_attempts += 1
            if self._half_open_attempts >= self.half_open_max:
                self._state = "CLOSED"
                self._failure_count = 0
                logger.info("CircuitBreaker(%s): HALF_OPEN -> CLOSED", self.name)

    def failure(self, error: Exception | None = None):
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        if self._failure_count >= self.failure_threshold:
            self._state = "OPEN"
            logger.warning(
                "CircuitBreaker(%s): -> OPEN after %d failures", self.name, self._failure_count
            )
        elif self._state == "HALF_OPEN":
            self._state = "OPEN"
            logger.warning("CircuitBreaker(%s): HALF_OPEN -> OPEN", self.name)

    def allow_request(self) -> bool:
        self._maybe_transition()
        return self._state != "OPEN"


def _resolve_fallback(
    fallback_value: Any, args: tuple, kwargs: dict, error: Exception | None
) -> Any:
    if callable(fallback_value):
        try:
            state = args[0] if args else {}
            return fallback_value(state, error)
        except Exception as exc:
            logger.error("resilient_node: fallback callable failed: %s", exc)
            return {"errors": [f"fallback_failed:{exc}"]}
    return fallback_value


def resilient_node(
    max_retries: int = 1,
    timeout_s: float = 30.0,
    fallback_value: Any = None,
    circuit_breaker: CircuitBreaker | None = None,
    reraise: bool = False,
):
    """Decorator for pipeline node functions - adds retry, timeout, fallback."""

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            node_name = func.__name__
            if circuit_breaker and not circuit_breaker.allow_request():
                logger.warning("resilient_node(%s): circuit OPEN", node_name)
                return _resolve_fallback(
                    fallback_value,
                    args,
                    kwargs,
                    RuntimeError(f"Circuit breaker OPEN for {node_name}"),
                )
            last_error = None
            for attempt in range(max_retries + 1):
                try:
                    result = await asyncio.wait_for(func(*args, **kwargs), timeout=timeout_s)
                    if circuit_breaker:
                        circuit_breaker.success()
                    return result
                except TimeoutError:
                    last_error = TimeoutError(f"{node_name} timed out after {timeout_s}s")
                    logger.warning("resilient_node(%s): timeout", node_name)
                except Exception as exc:
                    last_error = exc
                    logger.warning(
                        "resilient_node(%s): attempt %d/%d failed: %s",
                        node_name,
                        attempt + 1,
                        max_retries + 1,
                        exc,
                    )
            if circuit_breaker:
                circuit_breaker.failure(last_error)
            result = _resolve_fallback(fallback_value, args, kwargs, last_error)
            if reraise and last_error:
                raise last_error
            return result

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            node_name = func.__name__
            if circuit_breaker and not circuit_breaker.allow_request():
                return _resolve_fallback(
                    fallback_value,
                    args,
                    kwargs,
                    RuntimeError(f"Circuit breaker OPEN for {node_name}"),
                )
            last_error = None
            for attempt in range(max_retries + 1):
                try:
                    result = func(*args, **kwargs)
                    if circuit_breaker:
                        circuit_breaker.success()
                    return result
                except Exception as exc:
                    last_error = exc
                    logger.warning(
                        "resilient_node(%s): attempt %d/%d failed: %s",
                        node_name,
                        attempt + 1,
                        max_retries + 1,
                        exc,
                    )
            if circuit_breaker:
                circuit_breaker.failure(last_error)
            result = _resolve_fallback(fallback_value, args, kwargs, last_error)
            if reraise and last_error:
                raise last_error
            return result

        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore[return-value]
        return sync_wrapper  # type: ignore[return-value]

    return decorator


def safe_import(module_path: str, attr_name: str = "", fallback: Any = None):
    """Import an optional dependency without crashing."""
    try:
        mod = (
            __import__(module_path, fromlist=[attr_name]) if attr_name else __import__(module_path)
        )
        return getattr(mod, attr_name, fallback) if attr_name else mod
    except ImportError as exc:
        logger.debug("safe_import(%s, %s): %s", module_path, attr_name, exc)
        return fallback


def try_run(
    label: str,
    func: Callable[..., Any],
    *args,
    fallback: Any = None,
    log_level: str = "debug",
    **kwargs,
) -> tuple[Any, Exception | None]:
    """Run a function with standardized error handling. Never raises."""
    try:
        result = func(*args, **kwargs)
        return result, None
    except Exception as exc:
        log = getattr(logger, log_level, logger.debug)
        log("%s: failed - %s", label, exc)
        return fallback, exc


async def try_run_async(
    label: str,
    func: Callable[..., Any],
    *args,
    fallback: Any = None,
    log_level: str = "debug",
    **kwargs,
) -> tuple[Any, Exception | None]:
    """Async version of try_run."""
    try:
        result = await func(*args, **kwargs)
        return result, None
    except Exception as exc:
        log = getattr(logger, log_level, logger.debug)
        log("%s: failed - %s", label, exc)
        return fallback, exc
