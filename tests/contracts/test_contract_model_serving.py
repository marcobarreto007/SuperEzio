"""Contract tests for Model Gateway + Provider configuration."""

from __future__ import annotations


# Import validation helpers — no deep imports at module level
ROOT = __import__("pathlib").Path(__file__).resolve().parents[2]


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
        build_default_providers,
        AGENT_PROVIDER_NAME,
        AGENT_MODEL_ID,
    )

    cfg = UniversalConfig()
    providers, gateway_config = build_default_providers(cfg)
    by_name = {p.name: p for p in providers}

    assert AGENT_PROVIDER_NAME in by_name
    agent = by_name[AGENT_PROVIDER_NAME]
    assert agent.is_local is True
    assert agent.model == AGENT_MODEL_ID
    assert "8080" in agent.base_url


def test_build_default_providers_primary_is_present(monkeypatch):
    """Primary provider must always be present in the default list."""
    monkeypatch.delenv("SUPEREZIO_PRIMARY_BASE_URL", raising=False)
    monkeypatch.delenv("SUPEREZIO_PRIMARY_MODEL", raising=False)
    monkeypatch.delenv("SUPEREZIO_DEEPSEEK_BASE_URL", raising=False)
    monkeypatch.delenv("SUPEREZIO_DEEPSEEK_API_KEY", raising=False)

    from core.config.schema import UniversalConfig
    from core.model_serving.providers import build_default_providers, PRIMARY_PROVIDER_NAME

    cfg = UniversalConfig()
    providers, _ = build_default_providers(cfg)
    by_name = {p.name: p for p in providers}

    assert PRIMARY_PROVIDER_NAME in by_name
    # Primary may be local or cloud depending on env vars — either is valid
    assert isinstance(by_name[PRIMARY_PROVIDER_NAME].is_local, bool)


def test_experts_provider_is_local_and_rejects_cloud_override(monkeypatch):
    """Zero-cloud contract: expert roles are served locally. A cloud
    SUPEREZIO_DEEPSEEK_BASE_URL override must be ignored; a local override
    must be honored (test stubs use local endpoints)."""
    monkeypatch.setenv("SUPEREZIO_DEEPSEEK_API_KEY", "sk-ds-test")
    monkeypatch.setenv("SUPEREZIO_DEEPSEEK_BASE_URL", "https://custom-deepseek.example.com")
    monkeypatch.setenv("SUPEREZIO_DEEPSEEK_MODEL", "deepseek-custom-model")
    monkeypatch.delenv("SUPEREZIO_PRIMARY_BASE_URL", raising=False)

    from core.config.schema import UniversalConfig
    from core.model_serving.providers import build_default_providers, DEEPSEEK_PROVIDER_NAME

    cfg = UniversalConfig()

    providers, _ = build_default_providers(cfg)
    by_name = {p.name: p for p in providers}
    assert DEEPSEEK_PROVIDER_NAME in by_name
    ds = by_name[DEEPSEEK_PROVIDER_NAME]
    assert ds.is_local is True
    assert "custom-deepseek.example.com" not in ds.base_url
    assert "api.deepseek.com" not in ds.base_url

    monkeypatch.setenv("SUPEREZIO_DEEPSEEK_BASE_URL", "http://127.0.0.1:9999/v1")
    providers, _ = build_default_providers(cfg)
    by_name = {p.name: p for p in providers}
    assert by_name[DEEPSEEK_PROVIDER_NAME].base_url == "http://127.0.0.1:9999/v1"


# ---------------------------------------------------------------------------
# Gateway construction
# ---------------------------------------------------------------------------


def test_gateway_instantiation():
    from core.model_serving.gateway import ModelGateway
    from core.model_serving.providers import ModelProvider, GatewayConfig

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


def test_gateway_max_attempts():
    from core.model_serving.gateway import ModelGateway
    from core.model_serving.providers import ModelProvider, GatewayConfig

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
