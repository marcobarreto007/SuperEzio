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


def test_default_build_has_deepseek_ceo_and_pinned_experts(monkeypatch) -> None:
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
    for name in ("agent", "local_orchestrator", "deepseek", "daytrade_judge", "daytrade_auditor"):
        assert by_name[name].is_local is False
        assert by_name[name].base_url == "https://api.deepseek.com"
        assert by_name[name].model == "deepseek-v4-pro"
    names = list(by_name)
    assert "ceo_fallback_glm" not in names
    assert "gemini" not in names


def test_agent_ceo_never_cascades(monkeypatch) -> None:
    """An agent/CEO request must resolve to the agent alone."""
    for var in ("SUPEREZIO_AGENT_BASE_URL", "SUPEREZIO_PRIMARY_BASE_URL"):
        monkeypatch.delenv(var, raising=False)

    providers, gw_config = build_providers()
    gateway = ModelGateway(providers, gw_config)

    # Simulate provider cooldown
    gateway._provider_cooldown_until["agent"] = time.monotonic() + 1000

    providers_to_try = gateway._providers_for_request(
        preferred_provider="agent", allow_fallback=True
    )
    assert [p.name for p in providers_to_try] == ["agent"]


def test_custom_agent_env_override(monkeypatch) -> None:
    """SUPEREZIO_AGENT_BASE_URL correctly overrides the agent endpoint."""
    monkeypatch.setenv("SUPEREZIO_AGENT_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setenv("SUPEREZIO_AGENT_MODEL", "deepseek-v4-pro")

    providers, _ = build_providers()
    agent = next(p for p in providers if p.name == "agent")
    assert agent.base_url == "https://api.deepseek.com"
    assert agent.model == "deepseek-v4-pro"
    assert agent.is_local is False


if __name__ == "__main__":
    raise SystemExit("Run via pytest: python -m pytest tests/test_ceo_fallback.py -q")
