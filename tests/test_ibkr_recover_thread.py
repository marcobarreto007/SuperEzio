"""POST /bob/ibkr/recover must run force_recovery_attempt off the asyncio loop.

Calling ib_insync connect on FastAPI's running loop raises:
  RuntimeError: Cannot run the event loop while another loop is running
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_server.main import app


class _FakeBroker:
    def __init__(self, result: dict[str, Any] | None = None):
        self._result = result or {
            "success": True,
            "error": None,
            "failures_reset": 0,
            "timestamp": "2026-09-11T00:00:00Z",
        }
        self.calls = 0

    def force_recovery_attempt(self) -> dict[str, Any]:
        self.calls += 1
        return self._result


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_bob_ibkr_recover_runs_recovery_off_event_loop(client, monkeypatch):
    service = _FakeBroker()
    monkeypatch.setattr("adapters.broker.ibkr_service.get_ibkr_service", lambda: service)

    to_thread_targets: list[Any] = []

    async def spy_to_thread(fn, /, *args, **kwargs):
        to_thread_targets.append(fn)
        return fn(*args, **kwargs)

    monkeypatch.setattr("agent_server.main.asyncio.to_thread", spy_to_thread)

    response = client.post("/bob/ibkr/recover")

    assert response.status_code == 200, response.text
    assert service.calls == 1
    assert to_thread_targets == [service.force_recovery_attempt]
    assert response.json()["success"] is True


def test_bob_ibkr_recover_returns_degraded_on_exception(client, monkeypatch):
    class _Boom:
        def force_recovery_attempt(self) -> dict[str, Any]:
            raise RuntimeError("Cannot run the event loop while another loop is running")

    monkeypatch.setattr("adapters.broker.ibkr_service.get_ibkr_service", lambda: _Boom())

    async def run_in_thread(fn, /, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr("agent_server.main.asyncio.to_thread", run_in_thread)

    response = client.post("/bob/ibkr/recover")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["success"] is False
    assert "event loop" in payload["error"]
