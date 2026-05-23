"""Circuit breaker per provider — prevents cascading failures during enrichment.

Contract: docs/architecture/SCANNER_MRI_CONTRACT.md §4.3
"""

from __future__ import annotations

import time
from enum import Enum


class CircuitBreakerOpenError(Exception):
    """Raised per-item when a circuit breaker is open."""

    def __init__(self, provider: str) -> None:
        super().__init__(f"Circuit breaker open for provider: {provider}")
        self.provider = provider


class CircuitState(str, Enum):
    CLOSED = "closed"  # normal operation — calls pass through
    OPEN = "open"  # breaker tripped — calls are skipped
    HALF_OPEN = "half_open"  # testing if provider has recovered


class CircuitBreaker:
    """Per-provider circuit breaker.

    Closed → (failure_threshold consecutive failures) → Open
    Open   → (half_open_cooldown_ms elapsed)          → Half-Open
    Half-Open → (success_threshold consecutive OK)    → Closed
    Half-Open → (any failure)                         → Open
    """

    def __init__(
        self,
        provider: str,
        *,
        failure_threshold: int = 5,
        success_threshold: int = 2,
        half_open_cooldown_ms: int = 10_000,
    ) -> None:
        self.provider = provider
        self.failure_threshold = failure_threshold
        self.success_threshold = success_threshold
        self.half_open_cooldown_ms = half_open_cooldown_ms

        self.state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._consecutive_successes = 0
        self._last_failure_time: float | None = None
        self._total_failures = 0
        self._total_successes = 0

    # ── public ────────────────────────────────────────────────────────────

    def allow(self) -> bool:
        """Should a call be allowed right now?"""
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.HALF_OPEN:
            return True
        if self.state == CircuitState.OPEN:
            if self._cooldown_elapsed():
                self.state = CircuitState.HALF_OPEN
                self._consecutive_successes = 0
                return True
            return False
        return False

    def success(self) -> None:
        """Report a successful call."""
        self._total_successes += 1
        if self.state == CircuitState.HALF_OPEN:
            self._consecutive_successes += 1
            if self._consecutive_successes >= self.success_threshold:
                self.state = CircuitState.CLOSED
                self._consecutive_failures = 0
        else:
            self._consecutive_failures = 0

    def failure(self) -> None:
        """Report a failed call."""
        self._total_failures += 1
        self._last_failure_time = time.monotonic()
        self._consecutive_failures += 1
        self._consecutive_successes = 0

        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
        elif (
            self.state == CircuitState.CLOSED
            and self._consecutive_failures >= self.failure_threshold
        ):
            self.state = CircuitState.OPEN

    # ── queries ───────────────────────────────────────────────────────────

    def _cooldown_elapsed(self) -> bool:
        if self._last_failure_time is None:
            return True
        return (time.monotonic() - self._last_failure_time) * 1000 >= self.half_open_cooldown_ms

    def snapshot(self) -> dict:
        return {
            "provider": self.provider,
            "state": self.state.value,
            "consecutive_failures": self._consecutive_failures,
            "consecutive_successes": self._consecutive_successes,
            "total_failures": self._total_failures,
            "total_successes": self._total_successes,
        }
