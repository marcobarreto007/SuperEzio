from __future__ import annotations

import json
import socket
from collections.abc import Iterator
from contextlib import contextmanager
from types import SimpleNamespace

from fastapi.testclient import TestClient

from agent_server.main import app


def _configure_official_deepseek(monkeypatch, *, api_key: str) -> None:
    monkeypatch.setenv("SUPEREZIO_DEEPSEEK_API_KEY", api_key)
    monkeypatch.setenv("SUPEREZIO_DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setenv("SUPEREZIO_DEEPSEEK_MODEL", "deepseek-v4-pro")
    monkeypatch.setenv("SUPEREZIO_DAYTRADE_JUDGE_MODEL", "deepseek-v4-pro")
    monkeypatch.setenv("SUPEREZIO_DAYTRADE_AUDITOR_MODEL", "deepseek-v4-pro")


@contextmanager
def _healthy_local_ceo(monkeypatch) -> Iterator[None]:
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    monkeypatch.setenv("SUPEREZIO_AGENT_BASE_URL", f"http://127.0.0.1:{port}/v1")
    try:
        yield
    finally:
        listener.close()


@contextmanager
def _gateway_provider(provider: SimpleNamespace) -> Iterator[None]:
    original_pipeline = getattr(app.state, "pipeline", None)
    app.state.pipeline = SimpleNamespace(gateway=SimpleNamespace(providers=[provider]))
    try:
        yield
    finally:
        app.state.pipeline = original_pipeline


def _deepseek_provider(*, api_key: str, is_local: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        name="deepseek",
        is_local=is_local,
        api_key=api_key,
        model="deepseek-v4-pro",
        base_url=("http://127.0.0.1:8080/v1" if is_local else "https://api.deepseek.com/v1"),
        priority=-300,
    )


def test_missing_deepseek_key_degrades_readiness_without_exposing_a_secret(monkeypatch) -> None:
    monkeypatch.delenv("SUPEREZIO_DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("SUPEREZIO_DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    monkeypatch.setenv("SUPEREZIO_DEEPSEEK_MODEL", "deepseek-v4-pro")
    monkeypatch.setenv("SUPEREZIO_DAYTRADE_JUDGE_MODEL", "deepseek-v4-pro")
    monkeypatch.setenv("SUPEREZIO_DAYTRADE_AUDITOR_MODEL", "deepseek-v4-pro")

    runtime_secret = "runtime-provider-secret-must-not-leak"
    with (
        _healthy_local_ceo(monkeypatch),
        _gateway_provider(_deepseek_provider(api_key=runtime_secret)),
    ):
        response = TestClient(app).get("/health/details")

    assert response.status_code == 503
    payload = response.json()
    assert payload["status"] == "degraded_experts_unconfigured"
    assert payload["checks"]["providers_summary"]["primary"]["topology"] == "local"
    experts = payload["checks"]["providers_summary"]["experts"]
    assert experts["provider"] == "deepseek"
    assert experts["topology"] == "external"
    assert experts["configured"] is False
    assert experts["status"] == "unconfigured_missing_api_key"
    serialized = json.dumps(payload).lower()
    assert runtime_secret not in serialized
    assert '"api_key"' not in serialized


def test_configured_external_deepseek_and_local_ceo_make_readiness_truthful(monkeypatch) -> None:
    secret_value = "sk-deepseek-health-test"
    _configure_official_deepseek(monkeypatch, api_key=secret_value)

    provider = _deepseek_provider(api_key=secret_value)
    with _healthy_local_ceo(monkeypatch), _gateway_provider(provider):
        response = TestClient(app).get("/health/details")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    primary = payload["checks"]["providers_summary"]["primary"]
    assert primary["topology"] == "local"
    assert primary["reachable"] is True
    experts = payload["checks"]["provider_deepseek"]
    assert experts["topology"] == "external"
    assert experts["runtime_topology"] == "external"
    assert experts["configured"] is True
    assert experts["status"] == "configured"
    assert secret_value not in response.text


def test_local_runtime_cannot_masquerade_as_external_deepseek(monkeypatch) -> None:
    _configure_official_deepseek(monkeypatch, api_key="sk-deepseek-health-test")

    provider = _deepseek_provider(api_key="sk-deepseek-health-test", is_local=True)
    with _healthy_local_ceo(monkeypatch), _gateway_provider(provider):
        response = TestClient(app).get("/health/details")

    assert response.status_code == 503
    experts = response.json()["checks"]["provider_deepseek"]
    assert experts["configured"] is False
    assert experts["runtime_topology"] == "local"
    assert experts["status"] == "misconfigured_runtime_topology"


def test_missing_expert_key_does_not_take_down_public_liveness(monkeypatch) -> None:
    from core import bob_consciousness

    class HealthyBody:
        organs: dict = {}

        @staticmethod
        def is_man_at_work() -> bool:
            return False

    monkeypatch.delenv("SUPEREZIO_DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(bob_consciousness, "get_bobs_body", lambda: HealthyBody())
    original_pipeline = getattr(app.state, "pipeline", None)
    app.state.pipeline = object()
    try:
        response = TestClient(app).get("/health")
    finally:
        app.state.pipeline = original_pipeline

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
