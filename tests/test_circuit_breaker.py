"""Deterministic lifecycle tests for the shared circuit breaker."""

import pytest

from core import resilience
from core.resilience import CircuitBreaker, CircuitOpenError, CircuitState


def test_closed_opens_at_threshold(monkeypatch):
    now = 1000.0
    monkeypatch.setattr(resilience.time, "time", lambda: now)
    circuit = CircuitBreaker("test", failure_threshold=2, recovery_timeout=30)

    circuit.record_failure(TimeoutError("first"))
    assert circuit.state == CircuitState.CLOSED
    assert circuit.allow_request() is True

    circuit.record_failure(TimeoutError("second"))
    assert circuit.state == CircuitState.OPEN
    assert circuit.allow_request() is False
    assert circuit.health["state"] == "open"


def test_open_advances_to_half_open_after_recovery_timeout(monkeypatch):
    now = 1000.0
    monkeypatch.setattr(resilience.time, "time", lambda: now)
    circuit = CircuitBreaker("test", failure_threshold=1, recovery_timeout=30)
    circuit.record_failure(TimeoutError("down"))

    now = 1029.9
    assert circuit.allow_request() is False
    assert circuit.state == CircuitState.OPEN

    now = 1030.0
    assert circuit.allow_request() is True
    assert circuit.state == CircuitState.HALF_OPEN
    assert circuit.health["state"] == "half_open"


def test_half_open_success_closes_and_resets_failures(monkeypatch):
    now = 1000.0
    monkeypatch.setattr(resilience.time, "time", lambda: now)
    circuit = CircuitBreaker("test", failure_threshold=1, recovery_timeout=0)
    circuit.record_failure(TimeoutError("down"))
    assert circuit.allow_request() is True
    assert circuit.state == CircuitState.HALF_OPEN

    circuit.record_success()

    assert circuit.state == CircuitState.CLOSED
    assert circuit.failure_count == 0
    assert circuit.health["total_successes"] == 1


def test_half_open_failure_reopens(monkeypatch):
    now = 1000.0
    monkeypatch.setattr(resilience.time, "time", lambda: now)
    circuit = CircuitBreaker("test", failure_threshold=1, recovery_timeout=0)
    circuit.record_failure(TimeoutError("down"))
    assert circuit.allow_request() is True

    circuit.record_failure(TimeoutError("probe failed"))

    assert circuit.state == CircuitState.OPEN
    assert circuit.failure_count == 2
    assert circuit.health["total_failures"] == 2


def test_call_rejects_while_open(monkeypatch):
    now = 1000.0
    monkeypatch.setattr(resilience.time, "time", lambda: now)
    circuit = CircuitBreaker("test", failure_threshold=1, recovery_timeout=30)
    circuit.record_failure(TimeoutError("down"))

    with pytest.raises(CircuitOpenError, match="is OPEN"):
        circuit.call(lambda: "must not run")
