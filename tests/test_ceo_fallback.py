"""Hybrid provider-boundary tests.

The CEO remains local-only. Experts use pinned DeepSeek providers, but they
must never become a fallback for the CEO or vice versa.
"""

import time

import pytest

from core.model_serving.gateway import ModelGateway
from core.model_serving.providers import (
    GLM_CODING_PLAN_BASE_URL,
    _normalize_zai_base_url,
    build_providers,
)


@pytest.fixture(autouse=True)
def _deepseek_contract_env(monkeypatch):
    monkeypatch.setenv("SUPEREZIO_DEEPSEEK_API_KEY", "test-key")
    for var in (
        "SUPEREZIO_DEEPSEEK_BASE_URL",
        "SUPEREZIO_DEEPSEEK_MODEL",
        "SUPEREZIO_ALLOW_CUSTOM_DEEPSEEK_BASE_URL",
        "SUPEREZIO_AGENT_BASE_URL",
        "SUPEREZIO_PRIMARY_BASE_URL",
        "SUPEREZIO_AGENT_MODEL",
        "SUPEREZIO_PRIMARY_MODEL",
        "SUPEREZIO_GLM_CODING_PLAN_API_KEY",
        "SUPEREZIO_AGENT_API_KEY",
        "SUPEREZIO_PRIMARY_API_KEY",
    ):
        monkeypatch.delenv(var, raising=False)


def test_default_build_has_deepseek_ceo_and_pinned_experts(monkeypatch) -> None:
    monkeypatch.setenv("SUPEREZIO_GLM_CODE_PLAN_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("SUPEREZIO_AGENT_MODEL", "deepseek-v4-pro")
    monkeypatch.setenv("SUPEREZIO_PRIMARY_MODEL", "deepseek-v4-pro")
    monkeypatch.setenv("SUPEREZIO_AGENT_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setenv("SUPEREZIO_PRIMARY_BASE_URL", "https://api.deepseek.com")

    from core.config import get_config
    from core.model_serving.providers import build_default_providers

    cfg = get_config()
    for var in (
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


def test_normalize_zai_general_paas_to_coding_plan() -> None:
    assert (
        _normalize_zai_base_url("https://api.z.ai/api/paas/v4") == GLM_CODING_PLAN_BASE_URL
    )
    assert (
        _normalize_zai_base_url("https://api.z.ai/api/paas/v4/chat/completions")
        == GLM_CODING_PLAN_BASE_URL
    )
    assert _normalize_zai_base_url("https://api.deepseek.com") == "https://api.deepseek.com"


def test_glm53_coding_plan_rewrites_general_paas_url(monkeypatch) -> None:
    """Coding Plan keys must not hit /api/paas/v4."""
    monkeypatch.setenv("SUPEREZIO_AGENT_MODEL", "glm-5.3")
    monkeypatch.setenv("SUPEREZIO_PRIMARY_MODEL", "glm-5.3")
    monkeypatch.setenv("SUPEREZIO_GLM_CODING_PLAN_API_KEY", "test-coding-plan-key")
    monkeypatch.setenv("SUPEREZIO_AGENT_BASE_URL", "https://api.z.ai/api/paas/v4")
    monkeypatch.setenv("SUPEREZIO_PRIMARY_BASE_URL", "https://api.z.ai/api/paas/v4")

    providers, _ = build_providers()
    by_name = {p.name: p for p in providers}
    assert by_name["agent"].base_url == "https://api.z.ai/api/coding/paas/v4"
    assert by_name["agent"].model == "glm-5.3"
    assert by_name["agent"].is_local is False
    assert by_name["local_orchestrator"].base_url == "https://api.z.ai/api/coding/paas/v4"
    assert by_name["deepseek"].base_url == "https://api.deepseek.com"
    assert by_name["deepseek"].model == "deepseek-v4-pro"


def test_glm53_missing_coding_plan_key_fails_closed(monkeypatch) -> None:
    monkeypatch.setenv("SUPEREZIO_AGENT_MODEL", "glm-5.3")
    monkeypatch.delenv("SUPEREZIO_GLM_CODING_PLAN_API_KEY", raising=False)
    monkeypatch.delenv("SUPEREZIO_AGENT_API_KEY", raising=False)
    monkeypatch.delenv("SUPEREZIO_PRIMARY_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="GLM_CODING_PLAN_API_KEY"):
        build_providers()


def test_custom_agent_env_override(monkeypatch) -> None:
    """SUPEREZIO_AGENT_BASE_URL correctly overrides the agent endpoint."""
    monkeypatch.setenv("SUPEREZIO_AGENT_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setenv("SUPEREZIO_AGENT_MODEL", "deepseek-v4-pro")

    providers, _ = build_providers()
    agent = next(p for p in providers if p.name == "agent")
    assert agent.base_url == "https://api.deepseek.com"
    assert agent.model == "deepseek-v4-pro"
    assert agent.is_local is False


def test_is_insufficient_credit_error_detection() -> None:
    from core.model_serving.gateway import is_insufficient_credit_error

    class _MockHttpError(Exception):
        def __init__(self, status_code, message="", code=None):
            super().__init__(message)
            self.status_code = status_code
            self.code = code

    # HTTP 402 Payment Required
    assert is_insufficient_credit_error(_MockHttpError(402, "Payment Required")) is True

    # Z.ai / BigModel error codes
    assert is_insufficient_credit_error(_MockHttpError(400, "Error", code=1301)) is True
    assert is_insufficient_credit_error(_MockHttpError(403, "Error", code="1302")) is True

    # Keywords in error string
    assert is_insufficient_credit_error(Exception("Account is in arrears, please recharge")) is True
    assert is_insufficient_credit_error(Exception("insufficient_quota: You exceeded your quota")) is True
    assert is_insufficient_credit_error(Exception("Model out of credit")) is True
    assert is_insufficient_credit_error(Exception("Balance is insufficient for request")) is True

    # Non-credit errors
    assert is_insufficient_credit_error(None) is False
    assert is_insufficient_credit_error(Exception("Connection timed out")) is False
    assert is_insufficient_credit_error(_MockHttpError(500, "Internal Server Error")) is False
    assert is_insufficient_credit_error(_MockHttpError(401, "Invalid API key")) is False


def test_glm_routes_to_deepseek_fallback_when_allowed(monkeypatch) -> None:
    monkeypatch.setenv("SUPEREZIO_AGENT_MODEL", "glm-5.3")
    monkeypatch.setenv("SUPEREZIO_PRIMARY_MODEL", "glm-5.3")
    monkeypatch.setenv("SUPEREZIO_GLM_CODING_PLAN_API_KEY", "test-coding-plan-key")
    monkeypatch.setenv("SUPEREZIO_AGENT_BASE_URL", "https://api.z.ai/api/coding/paas/v4")

    providers, gw_config = build_providers()
    gateway = ModelGateway(providers, gw_config)

    # 1. Fallback allowed: returns GLM agent + DeepSeek
    providers_to_try = gateway._providers_for_request(
        preferred_provider="agent", allow_fallback=True
    )
    names = [p.name for p in providers_to_try]
    assert names == ["agent", "deepseek"]

    # 2. Fallback disabled: returns GLM agent alone
    providers_no_fallback = gateway._providers_for_request(
        preferred_provider="agent", allow_fallback=False
    )
    assert [p.name for p in providers_no_fallback] == ["agent"]

    # 3. Agent in cooldown (e.g. after credit exhaustion): routes directly to DeepSeek
    gateway._provider_cooldown_until["agent"] = time.monotonic() + 1000
    providers_cooldown = gateway._providers_for_request(
        preferred_provider="agent", allow_fallback=True
    )
    assert [p.name for p in providers_cooldown] == ["deepseek"]


def test_glm_out_of_credit_falls_back_to_deepseek_generate(monkeypatch) -> None:
    monkeypatch.setenv("SUPEREZIO_AGENT_MODEL", "glm-5.3")
    monkeypatch.setenv("SUPEREZIO_PRIMARY_MODEL", "glm-5.3")
    monkeypatch.setenv("SUPEREZIO_GLM_CODING_PLAN_API_KEY", "test-coding-plan-key")
    monkeypatch.setenv("SUPEREZIO_AGENT_BASE_URL", "https://api.z.ai/api/coding/paas/v4")

    providers, gw_config = build_providers()
    gateway = ModelGateway(providers, gw_config)

    async def fake_generate_api(provider, *args, **kwargs):
        if provider.name == "agent":
            # Simulate Z.ai out of credit / arrears error
            raise RuntimeError("Z.ai API error 1301: Account is in arrears / out of credit")
        if provider.name == "deepseek":
            return "DeepSeek fallback answer"
        return "other"

    monkeypatch.setattr(gateway, "generate_api", fake_generate_api)

    result = gateway.generate(prompt="Analyze TD.TO", preferred_provider="agent")
    assert result == "DeepSeek fallback answer"
    assert gateway.last_provider_used == "deepseek"
    # Verify GLM agent was put into cooldown
    assert "agent" in gateway._provider_cooldown_until


@pytest.mark.asyncio
async def test_glm_out_of_credit_falls_back_to_deepseek_stream_async(monkeypatch) -> None:
    monkeypatch.setenv("SUPEREZIO_AGENT_MODEL", "glm-5.3")
    monkeypatch.setenv("SUPEREZIO_PRIMARY_MODEL", "glm-5.3")
    monkeypatch.setenv("SUPEREZIO_GLM_CODING_PLAN_API_KEY", "test-coding-plan-key")
    monkeypatch.setenv("SUPEREZIO_AGENT_BASE_URL", "https://api.z.ai/api/coding/paas/v4")

    providers, gw_config = build_providers()
    gateway = ModelGateway(providers, gw_config)

    async def fake_stream_generate_api(provider, *args, **kwargs):
        if provider.name == "agent":
            class _Http402(Exception):
                status_code = 402
            raise _Http402("Payment Required: insufficient balance")
        if provider.name == "deepseek":
            yield "Deep"
            yield "Seek"

    monkeypatch.setattr(gateway, "stream_generate_api", fake_stream_generate_api)

    chunks = []
    async for chunk in gateway.stream_generate_async(prompt="Hi", preferred_provider="agent"):
        chunks.append(chunk)

    assert "".join(chunks) == "DeepSeek"
    assert "agent" in gateway._provider_cooldown_until


if __name__ == "__main__":
    raise SystemExit("Run via pytest: python -m pytest tests/test_ceo_fallback.py -q")

