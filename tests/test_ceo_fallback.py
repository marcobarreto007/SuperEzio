"""Hybrid provider-boundary tests.

The CEO remains local-only. Experts use pinned DeepSeek providers, but they
must never become a fallback for the CEO or vice versa.
"""

import time

import pytest

from core.model_serving.gateway import ModelGateway
from core.model_serving.providers import build_providers


@pytest.fixture(autouse=True)
def _deepseek_contract_env(monkeypatch):
    monkeypatch.setenv("SUPEREZIO_DEEPSEEK_API_KEY", "test-key")
    monkeypatch.delenv("SUPEREZIO_DEEPSEEK_BASE_URL", raising=False)
    monkeypatch.delenv("SUPEREZIO_DEEPSEEK_MODEL", raising=False)
    monkeypatch.delenv("SUPEREZIO_ALLOW_CUSTOM_DEEPSEEK_BASE_URL", raising=False)


def test_default_build_has_local_ceo_and_pinned_deepseek_experts(monkeypatch) -> None:
    monkeypatch.setenv("SUPEREZIO_GLM_CODE_PLAN_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    for var in (
        "SUPEREZIO_AGENT_BASE_URL",
        "SUPEREZIO_AGENT_MODEL",
        "SUPEREZIO_PRIMARY_BASE_URL",
    ):
        monkeypatch.delenv(var, raising=False)

    from core.config import get_config
    from core.model_serving.providers import build_default_providers

    cfg = get_config()
    for var in (
        "SUPEREZIO_AGENT_MODEL",
        "SUPEREZIO_PRIMARY_MODEL",
        "SUPEREZIO_DEEPSEEK_BASE_URL",
        "SUPEREZIO_DEEPSEEK_MODEL",
        "SUPEREZIO_ALLOW_CUSTOM_DEEPSEEK_BASE_URL",
        "SUPEREZIO_DAYTRADE_JUDGE_MODEL",
        "SUPEREZIO_DAYTRADE_AUDITOR_MODEL",
    ):
        monkeypatch.delenv(var, raising=False)
    providers, _ = build_default_providers(cfg)
    assert providers, "default provider build must not be empty"
    by_name = {p.name: p for p in providers}
    for name in ("agent", "local_orchestrator"):
        assert by_name[name].is_local is True
        assert "127.0.0.1" in by_name[name].base_url
        assert by_name[name].model == "Qwen3.8-27B-Q4_K_M"
    for name in ("deepseek", "daytrade_judge", "daytrade_auditor"):
        assert by_name[name].is_local is False
        assert by_name[name].base_url == "https://api.deepseek.com"
        assert by_name[name].model == "deepseek-v4-pro"
    names = list(by_name)
    assert "ceo_fallback_glm" not in names
    assert "gemini" not in names


def test_agent_ceo_never_cascades_when_local_fails(monkeypatch) -> None:
    """An agent/CEO request must resolve to the agent alone — even with the
    agent in cooldown, nothing non-local may take its place."""
    for var in ("SUPEREZIO_AGENT_BASE_URL", "SUPEREZIO_PRIMARY_BASE_URL"):
        monkeypatch.delenv(var, raising=False)

    providers, gw_config = build_providers()
    gateway = ModelGateway(providers, gw_config)

    # Simulate local provider failure by putting it in cooldown.
    gateway._provider_cooldown_until["agent"] = time.monotonic() + 1000

    providers_to_try = gateway._providers_for_request(
        preferred_provider="agent", allow_fallback=True
    )
    assert [p.name for p in providers_to_try] == ["agent"]


def test_stale_cloud_env_override_is_ignored(monkeypatch) -> None:
    """A leftover .env entry pointing at api.deepseek.com must not route the
    CEO to the cloud (the exact regression found on 2026-08-17)."""
    monkeypatch.setenv("SUPEREZIO_AGENT_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setenv("SUPEREZIO_AGENT_MODEL", "deepseek-v4-pro")

    providers, _ = build_providers()
    agent = next(p for p in providers if p.name == "agent")
    assert "api.deepseek.com" not in agent.base_url
    assert agent.is_local is True


def test_docker_service_hostname_requires_explicit_docker_profile(monkeypatch) -> None:
    """bob-ceo is local only inside the isolated compose network."""
    monkeypatch.setenv("SUPEREZIO_AGENT_BASE_URL", "http://bob-ceo:8080/v1")
    monkeypatch.delenv("SUPEREZIO_RUNTIME_PROFILE", raising=False)

    providers, _ = build_providers()
    agent = next(p for p in providers if p.name == "agent")
    assert agent.base_url == "http://127.0.0.1:8080/v1"

    monkeypatch.setenv("SUPEREZIO_RUNTIME_PROFILE", "docker")
    providers, _ = build_providers()
    agent = next(p for p in providers if p.name == "agent")
    assert agent.base_url == "http://bob-ceo:8080/v1"


def test_docker_profile_does_not_allow_other_hosts_or_ports(monkeypatch) -> None:
    monkeypatch.setenv("SUPEREZIO_RUNTIME_PROFILE", "docker")
    for unsafe_url in (
        "https://bob-ceo:8080/v1",
        "http://bob-ceo:8082/v1",
        "http://api.deepseek.com/v1",
        "http://localhost.example.com:8080/v1",
    ):
        monkeypatch.setenv("SUPEREZIO_AGENT_BASE_URL", unsafe_url)
        providers, _ = build_providers()
        agent = next(p for p in providers if p.name == "agent")
        assert agent.base_url == "http://127.0.0.1:8080/v1"


if __name__ == "__main__":
    raise SystemExit("Run via pytest: python -m pytest tests/test_ceo_fallback.py -q")
