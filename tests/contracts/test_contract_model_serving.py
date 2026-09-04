"""Contract tests for Model Gateway + Provider configuration."""

from __future__ import annotations

import pytest

# Import validation helpers — no deep imports at module level
ROOT = __import__("pathlib").Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _deepseek_contract_env(monkeypatch):
    monkeypatch.setenv("SUPEREZIO_DEEPSEEK_API_KEY", "sk-ds-test-only")
    for name in (
        "SUPEREZIO_DEEPSEEK_BASE_URL",
        "SUPEREZIO_DEEPSEEK_MODEL",
        "SUPEREZIO_DEEPSEEK_MAX_TOKENS",
        "SUPEREZIO_DEEPSEEK_TIMEOUT_SEC",
        "SUPEREZIO_EXPERT_MAX_TOKENS",
        "SUPEREZIO_EXPERT_TIMEOUT",
        "SUPEREZIO_ALLOW_CUSTOM_DEEPSEEK_BASE_URL",
        "SUPEREZIO_DAYTRADE_JUDGE_MODEL",
        "SUPEREZIO_DAYTRADE_AUDITOR_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)


# ---------------------------------------------------------------------------
# Provider construction
# ---------------------------------------------------------------------------


def test_model_provider_defaults():
    """ModelProvider must be constructable with mandatory fields."""
    from core.model_serving.providers import ModelProvider

    p = ModelProvider(
        name="test-provider",
        base_url="http://127.0.0.1:9999/v1",
        api_key="test-key",
        model="test-model",
    )
    assert p.name == "test-provider"
    assert p.base_url == "http://127.0.0.1:9999/v1"
    assert p.model == "test-model"
    assert p.backend in ("openai_compatible", "cloud")
    assert p.is_local is False
    assert p.priority == 0


def test_provider_is_local_flag():
    from core.model_serving.providers import ModelProvider

    local = ModelProvider(
        name="local-agent",
        base_url="http://127.0.0.1:8082/v1",
        api_key="no-key",
        model="agent-model",
        is_local=True,
    )
    assert local.is_local is True


def test_gateway_config_defaults():
    from core.model_serving.providers import GatewayConfig

    cfg = GatewayConfig()
    assert cfg.max_fallbacks == 2
    assert cfg.timeout_s == 300  # GatewayConfig default now 300s (was 120)
    assert cfg.retry_attempts == 2
    assert cfg.retry_delay_s == 1.0
    assert cfg.quality_threshold == 0.7


# ---------------------------------------------------------------------------
# build_default_providers
# ---------------------------------------------------------------------------


def test_build_default_providers_agent_present(monkeypatch):
    """Agent provider must appear in the default list."""
    monkeypatch.delenv("SUPEREZIO_PRIMARY_BASE_URL", raising=False)
    monkeypatch.delenv("SUPEREZIO_DEEPSEEK_BASE_URL", raising=False)
    monkeypatch.delenv("SUPEREZIO_AGENT_BASE_URL", raising=False)
    monkeypatch.delenv("SUPEREZIO_AGENT_MODEL", raising=False)
    monkeypatch.delenv("SUPEREZIO_AGENT_API_KEY", raising=False)

    from core.config.schema import UniversalConfig
    from core.model_serving.providers import (
        AGENT_MODEL_ID,
        AGENT_PROVIDER_NAME,
        build_default_providers,
    )

    cfg = UniversalConfig()
    providers, _gateway_config = build_default_providers(cfg)
    by_name = {p.name: p for p in providers}

    assert AGENT_PROVIDER_NAME in by_name
    agent = by_name[AGENT_PROVIDER_NAME]
    assert agent.is_local is False
    assert agent.model == AGENT_MODEL_ID
    assert "api.deepseek.com" in agent.base_url


def test_build_default_providers_primary_is_present(monkeypatch):
    """Primary provider must always be present in the default list."""
    monkeypatch.delenv("SUPEREZIO_PRIMARY_BASE_URL", raising=False)
    monkeypatch.delenv("SUPEREZIO_PRIMARY_MODEL", raising=False)
    monkeypatch.delenv("SUPEREZIO_DEEPSEEK_BASE_URL", raising=False)

    from core.config.schema import UniversalConfig
    from core.model_serving.providers import PRIMARY_PROVIDER_NAME, build_default_providers

    cfg = UniversalConfig()
    providers, _ = build_default_providers(cfg)
    by_name = {p.name: p for p in providers}

    assert PRIMARY_PROVIDER_NAME in by_name
    assert by_name[PRIMARY_PROVIDER_NAME].is_local is False
    assert by_name[PRIMARY_PROVIDER_NAME].model == "deepseek-v4-pro"


def test_experts_are_pinned_to_official_deepseek(monkeypatch):
    monkeypatch.delenv("SUPEREZIO_PRIMARY_BASE_URL", raising=False)

    from core.config.schema import UniversalConfig
    from core.model_serving.providers import (
        DAYTRADE_AUDITOR_PROVIDER_NAME,
        DAYTRADE_JUDGE_PROVIDER_NAME,
        DEEPSEEK_MODEL_ID,
        DEEPSEEK_OFFICIAL_BASE_URL,
        DEEPSEEK_PROVIDER_NAME,
        build_default_providers,
    )

    cfg = UniversalConfig()
    providers, _ = build_default_providers(cfg)
    by_name = {p.name: p for p in providers}
    for name in (
        DEEPSEEK_PROVIDER_NAME,
        DAYTRADE_JUDGE_PROVIDER_NAME,
        DAYTRADE_AUDITOR_PROVIDER_NAME,
    ):
        provider = by_name[name]
        assert provider.base_url == DEEPSEEK_OFFICIAL_BASE_URL
        assert provider.model == DEEPSEEK_MODEL_ID
        assert provider.api_key == "sk-ds-test-only"
        assert provider.is_local is False
        assert provider.max_tokens == 1800
        assert provider.timeout_s == 180


def test_missing_deepseek_key_fails_closed_without_echoing_secret(monkeypatch):
    monkeypatch.delenv("SUPEREZIO_DEEPSEEK_API_KEY", raising=False)

    from core.config.schema import UniversalConfig
    from core.model_serving.providers import build_default_providers

    with pytest.raises(RuntimeError, match="SUPEREZIO_DEEPSEEK_API_KEY is required") as exc:
        build_default_providers(UniversalConfig())
    assert "sk-" not in str(exc.value)


@pytest.mark.parametrize(
    "env_name",
    (
        "SUPEREZIO_DEEPSEEK_MODEL",
        "SUPEREZIO_DAYTRADE_JUDGE_MODEL",
        "SUPEREZIO_DAYTRADE_AUDITOR_MODEL",
    ),
)
def test_official_deepseek_rejects_local_or_retired_model_ids(monkeypatch, env_name):
    monkeypatch.setenv(env_name, "Qwen3.8-27B-UD-IQ2_XXS")

    from core.config.schema import UniversalConfig
    from core.model_serving.providers import build_default_providers

    with pytest.raises(RuntimeError, match="official DeepSeek models"):
        build_default_providers(UniversalConfig())


def test_model_provider_repr_hides_api_key():
    from core.model_serving.providers import ModelProvider

    provider = ModelProvider(
        name="deepseek", base_url="https://api.deepseek.com", api_key="secret-canary"
    )
    assert "secret-canary" not in repr(provider)
    assert "api_key" not in repr(provider)


@pytest.mark.parametrize(
    "url",
    (
        "http://api.deepseek.com",
        "http://127.0.0.1:8080/v1",
        "https://localhost/v1",
        "https://user:password@example.com/v1",
        "https://example.com:8443/v1",
    ),
)
def test_unsafe_deepseek_override_is_rejected_even_with_opt_in(monkeypatch, url):
    monkeypatch.setenv("SUPEREZIO_ALLOW_CUSTOM_DEEPSEEK_BASE_URL", "1")
    monkeypatch.setenv("SUPEREZIO_DEEPSEEK_BASE_URL", url)

    from core.config.schema import UniversalConfig
    from core.model_serving.providers import build_default_providers

    with pytest.raises(RuntimeError, match="DeepSeek endpoint"):
        build_default_providers(UniversalConfig())


def test_secure_custom_deepseek_host_requires_explicit_opt_in(monkeypatch):
    custom_url = "https://deepseek-proxy.example.com/v1"
    monkeypatch.setenv("SUPEREZIO_DEEPSEEK_BASE_URL", custom_url)

    from core.config.schema import UniversalConfig
    from core.model_serving.providers import build_default_providers

    with pytest.raises(RuntimeError, match="Custom SUPEREZIO_DEEPSEEK_BASE_URL is disabled"):
        build_default_providers(UniversalConfig())

    monkeypatch.setenv("SUPEREZIO_ALLOW_CUSTOM_DEEPSEEK_BASE_URL", "true")
    providers, _ = build_default_providers(UniversalConfig())
    assert next(p for p in providers if p.name == "deepseek").base_url == custom_url


def test_deepseek_limits_respect_specific_and_legacy_env(monkeypatch):
    from core.model_serving.providers import get_deepseek_max_tokens, get_deepseek_timeout_s

    monkeypatch.setenv("SUPEREZIO_EXPERT_MAX_TOKENS", "2000")
    monkeypatch.setenv("SUPEREZIO_EXPERT_TIMEOUT", "240")
    assert get_deepseek_max_tokens() == 2000
    assert get_deepseek_timeout_s() == 240

    monkeypatch.setenv("SUPEREZIO_DEEPSEEK_MAX_TOKENS", "1800")
    monkeypatch.setenv("SUPEREZIO_DEEPSEEK_TIMEOUT_SEC", "90")
    assert get_deepseek_max_tokens() == 1800
    assert get_deepseek_timeout_s() == 90

    monkeypatch.setenv("SUPEREZIO_DEEPSEEK_MAX_TOKENS", "9000")
    with pytest.raises(RuntimeError, match="between 128 and 8192"):
        get_deepseek_max_tokens()


# ---------------------------------------------------------------------------
# Gateway construction
# ---------------------------------------------------------------------------


def test_gateway_instantiation():
    from core.model_serving.gateway import ModelGateway
    from core.model_serving.providers import GatewayConfig, ModelProvider

    p1 = ModelProvider(name="p1", base_url="http://a/v1", api_key="k1", model="m1", priority=-100)
    p2 = ModelProvider(name="p2", base_url="http://b/v1", api_key="k2", model="m2", priority=-200)
    gw = ModelGateway(providers=[p1, p2], config=GatewayConfig())
    assert len(gw.providers) == 2
    # Sorted by priority (ascending)
    assert gw.providers[0].name == "p2"


def test_gateway_providers_for_request_agent_no_fallback(monkeypatch):
    """Agent provider must not return fallbacks when fallback is disabled."""
    monkeypatch.delenv("SUPEREZIO_PRIMARY_BASE_URL", raising=False)
    monkeypatch.delenv("SUPEREZIO_DEEPSEEK_BASE_URL", raising=False)

    from core.config.schema import UniversalConfig
    from core.model_serving.gateway import create_gateway_from_config
    from core.model_serving.providers import AGENT_PROVIDER_NAME

    cfg = UniversalConfig()
    gw = create_gateway_from_config(cfg)
    providers = gw._providers_for_request(AGENT_PROVIDER_NAME, allow_fallback=False)
    assert len(providers) == 1
    assert providers[0].name == AGENT_PROVIDER_NAME


def test_gateway_agent_never_has_cloud_fallback(monkeypatch):
    """Zero-cloud contract: even with a GLM key configured, no ceo_fallback_glm
    provider may exist, and the agent/CEO must resolve to itself alone."""
    monkeypatch.setenv("SUPEREZIO_GLM_CODE_PLAN_API_KEY", "test-key")
    monkeypatch.delenv("SUPEREZIO_PRIMARY_BASE_URL", raising=False)
    monkeypatch.delenv("SUPEREZIO_DEEPSEEK_BASE_URL", raising=False)

    from core.config.schema import UniversalConfig
    from core.model_serving.gateway import create_gateway_from_config
    from core.model_serving.providers import AGENT_PROVIDER_NAME

    cfg = UniversalConfig()
    gw = create_gateway_from_config(cfg)
    assert "ceo_fallback_glm" not in [p.name for p in gw.providers]
    providers = gw._providers_for_request(AGENT_PROVIDER_NAME)
    assert [p.name for p in providers] == [AGENT_PROVIDER_NAME]


def test_agent_timeout_invalid_value_fails_cleanly(monkeypatch):
    """T4: an invalid SUPEREZIO_AGENT_TIMEOUT_SEC must raise the bounded-parse
    RuntimeError (consistent with DeepSeek env parsing), not a raw
    ValueError from int() that crashes the provider build."""
    monkeypatch.setenv("SUPEREZIO_AGENT_TIMEOUT_SEC", "not-a-number")

    from core.config.schema import UniversalConfig
    from core.model_serving.providers import build_default_providers

    cfg = UniversalConfig()
    with pytest.raises(RuntimeError, match="SUPEREZIO_AGENT_TIMEOUT_SEC must be an integer"):
        build_default_providers(cfg)


def test_agent_timeout_env_below_floor_is_clamped(monkeypatch):
    """T4: a valid but small SUPEREZIO_AGENT_TIMEOUT_SEC is clamped to the
    LOCAL_TIMEOUT_S floor, preserving the previous behavior."""
    monkeypatch.setenv("SUPEREZIO_AGENT_TIMEOUT_SEC", "10")

    from core.config.schema import UniversalConfig
    from core.model_serving.providers import AGENT_PROVIDER_NAME, build_default_providers

    cfg = UniversalConfig()
    providers, _ = build_default_providers(cfg)
    agent = next(p for p in providers if p.name == AGENT_PROVIDER_NAME)
    assert agent.timeout_s >= 180


def test_gateway_max_attempts():
    from core.model_serving.gateway import ModelGateway
    from core.model_serving.providers import GatewayConfig, ModelProvider

    providers = [
        ModelProvider(name=f"p{i}", base_url=f"http://{i}/v1", api_key="k", model="m", priority=i)
        for i in range(5)
    ]
    cfg = GatewayConfig(max_fallbacks=2)
    gw = ModelGateway(providers=providers, config=cfg)
    assert gw._max_attempts(providers) == 3  # max_fallbacks + 1


def test_gateway_unload_all():
    """ModelGateway.unload_all() must not raise."""
    from core.model_serving.gateway import ModelGateway
    from core.model_serving.providers import ModelProvider

    p = ModelProvider(name="test", base_url="http://x/v1", api_key="k", model="m")
    gw = ModelGateway(providers=[p])
    gw.unload_all()  # must not raise


# ---------------------------------------------------------------------------
# Sanitizer
# ---------------------------------------------------------------------------


def test_private_channel_filter_plain_text():
    """PrivateChannelFilter passes plain text through after flush."""
    from core.model_serving.sanitizer import PrivateChannelFilter

    f = PrivateChannelFilter()
    # feed() may buffer short text (96-char lookback); flush releases it
    f.feed("Normal text here without any channel markers in the output stream buffer.")
    result = f.flush()
    assert "Normal text" in result


def test_strip_private_model_channels_empty():
    from core.model_serving.sanitizer import strip_private_model_channels

    assert strip_private_model_channels("") == ""


def test_strip_private_model_channels_plain():
    from core.model_serving.sanitizer import strip_private_model_channels

    text = "This is a normal financial analysis response."
    assert strip_private_model_channels(text) == text
