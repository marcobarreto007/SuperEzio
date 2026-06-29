"""Smoke tests — ModelGateway routing, fallback, aliases (deterministico)."""

import pytest
from core.model_serving.gateway import ModelGateway
from core.model_serving.providers import (
    ModelProvider,
    GatewayConfig,
    PRIMARY_PROVIDER_NAME,
    AGENT_PROVIDER_NAME,
    DEEPSEEK_PROVIDER_NAME,
)


def _provider(name, priority=0, base_url="http://x/api", backend="cloud"):
    return ModelProvider(
        name=name, base_url=base_url, priority=priority, api_key="", backend=backend
    )


def _gateway(*providers, max_fallbacks=2):
    return ModelGateway(
        providers=list(providers),
        config=GatewayConfig(max_fallbacks=max_fallbacks),
    )


class TestIsA2A:
    def test_backend_a2a(self):
        p = _provider("remote", backend="a2a")
        assert ModelGateway._is_a2a_provider(p) is True

    def test_url_ends_with_task_submit(self):
        p = _provider("remote", base_url="http://host/task/submit")
        assert ModelGateway._is_a2a_provider(p) is True

    def test_normal_cloud(self):
        p = _provider("cloud", base_url="https://api.openai.com/v1")
        assert ModelGateway._is_a2a_provider(p) is False

    def test_local_provider(self):
        p = _provider("agent", backend="openai_compatible", base_url="http://127.0.0.1:8082/v1")
        assert ModelGateway._is_a2a_provider(p) is False


class TestMaxAttempts:
    def test_empty(self):
        gw = _gateway()
        assert gw._max_attempts([]) == 0

    def test_no_fallbacks(self):
        gw = _gateway(max_fallbacks=0)
        p = [_provider("a")]
        assert gw._max_attempts(p) == 1

    def test_two_fallbacks(self):
        gw = _gateway(max_fallbacks=2)
        p = [_provider("a"), _provider("b"), _provider("c"), _provider("d")]
        assert gw._max_attempts(p) == 3  # 1 primary + 2 fallbacks

    def test_more_fallbacks_than_providers(self):
        gw = _gateway(max_fallbacks=5)
        p = [_provider("a"), _provider("b")]
        assert gw._max_attempts(p) == 2


class TestProvidersForRequest:
    def test_preferred_found(self):
        gw = _gateway(
            _provider(AGENT_PROVIDER_NAME, priority=-670),
            _provider("deepseek", priority=-300),
        )
        result = gw._providers_for_request(AGENT_PROVIDER_NAME)
        assert result[0].name == AGENT_PROVIDER_NAME
        # Agent is local-only — no fallback chain for agent-routed requests
        assert len(result) == 1

    def test_preferred_not_found(self):
        gw = _gateway(_provider("deepseek"))
        result = gw._providers_for_request("nonexistent")
        assert len(result) == 1
        assert result[0].name == "deepseek"

    def test_no_fallback(self):
        gw = _gateway(
            _provider("agent", priority=-670),
            _provider("deepseek", priority=-300),
        )
        result = gw._providers_for_request("agent", allow_fallback=False)
        assert len(result) == 1
        assert result[0].name == "agent"

    def test_no_preference_returns_all(self):
        gw = _gateway(_provider("a"), _provider("b"), _provider("c"))
        result = gw._providers_for_request(None)
        assert len(result) == 3

    def test_openai_alias(self):
        gw = _gateway(
            _provider("agent", priority=-670),
            _provider(DEEPSEEK_PROVIDER_NAME, priority=-300),
        )
        result = gw._providers_for_request("openai")
        assert result[0].name == DEEPSEEK_PROVIDER_NAME

    def test_bob_alias(self):
        gw = _gateway(
            _provider(AGENT_PROVIDER_NAME, priority=-670),
            _provider("deepseek", priority=-300),
        )
        result = gw._providers_for_request("bob")
        assert result[0].name == AGENT_PROVIDER_NAME

    def test_respects_priority_order_in_fallback(self):
        gw = _gateway(
            _provider("deepseek", priority=-300),
            _provider("agent", priority=-670),
            _provider("grok", priority=-500),
        )
        result = gw._providers_for_request("deepseek")
        assert result[0].name == "deepseek"
        # After pref, rest follow priority order (CEO excluded from fallback — local-only)
        names_after = [p.name for p in result[1:]]
        assert "agent" not in names_after, "Agent is local-only, should never be a fallback"
        assert names_after == ["grok"]


class TestPrimaryProvider:
    def test_finds_primary(self):
        gw = _gateway(
            _provider("other", priority=0),
            _provider(PRIMARY_PROVIDER_NAME, priority=-400),
        )
        p = gw._primary_provider()
        assert p.name == PRIMARY_PROVIDER_NAME

    def test_no_primary_falls_back_to_first(self):
        gw = _gateway(
            _provider("a", priority=-300),
            _provider("b", priority=-200),
        )
        p = gw._primary_provider()
        assert p.name == "a"

    def test_empty_raises(self):
        gw = _gateway()
        with pytest.raises(RuntimeError, match="No model provider"):
            gw._primary_provider()


class TestAddProvider:
    def test_inserts_and_sorts(self):
        gw = _gateway(
            _provider("b", priority=0),
            _provider("a", priority=-100),
        )
        gw.add_provider(_provider("c", priority=-50))
        names = [p.name for p in gw.providers]
        # Sorted by priority: a(-100), c(-50), b(0)
        assert names.index("a") < names.index("c") < names.index("b")

    def test_same_priority_stable(self):
        gw = _gateway(_provider("a", priority=0))
        gw.add_provider(_provider("b", priority=0))
        assert len(gw.providers) == 2


class TestApplyDeepseekOptions:
    def test_non_deepseek_skipped(self):
        p = _provider("agent", base_url="http://127.0.0.1:8082/v1")
        p.model = "bob-core-local"
        kwargs = {"temperature": 0.5}
        ModelGateway._apply_deepseek_options(p, kwargs)
        assert "extra_body" not in kwargs

    def test_deepseek_adds_thinking_disabled(self, monkeypatch):
        monkeypatch.setenv("SUPEREZIO_DEEPSEEK_THINKING", "disabled")
        p = _provider(DEEPSEEK_PROVIDER_NAME, base_url="https://api.deepseek.com")
        p.model = "deepseek-v4-pro"
        kwargs = {"temperature": 0.5}
        ModelGateway._apply_deepseek_options(p, kwargs)
        assert kwargs["extra_body"] == {"thinking": {"type": "disabled"}}

    def test_deepseek_adds_thinking_enabled(self, monkeypatch):
        monkeypatch.setenv("SUPEREZIO_DEEPSEEK_THINKING", "enabled")
        p = _provider(DEEPSEEK_PROVIDER_NAME, base_url="https://api.deepseek.com")
        p.model = "deepseek-v4-pro"
        kwargs = {"temperature": 0.5}
        ModelGateway._apply_deepseek_options(p, kwargs)
        assert kwargs["extra_body"] == {"thinking": {"type": "enabled"}}
        assert "temperature" not in kwargs  # removed when thinking enabled
        assert "reasoning_effort" in kwargs

    def test_local_orchestrator_gets_deepseek_options_when_configured_for_deepseek(
        self, monkeypatch
    ):
        monkeypatch.setenv("SUPEREZIO_DEEPSEEK_THINKING", "disabled")
        p = _provider(PRIMARY_PROVIDER_NAME, base_url="https://api.deepseek.com")
        p.model = "deepseek-v4-pro"
        kwargs = {}
        ModelGateway._apply_deepseek_options(p, kwargs)
        assert "extra_body" in kwargs

    def test_unknown_provider_uses_default_order(self):
        gw = _gateway(
            _provider(PRIMARY_PROVIDER_NAME, priority=-400),
            _provider(DEEPSEEK_PROVIDER_NAME, priority=-300),
        )
        result = gw._providers_for_request("unknown_provider")
        assert result[0].name == PRIMARY_PROVIDER_NAME

    def test_non_deepseek_model_skipped(self):
        p = _provider(DEEPSEEK_PROVIDER_NAME, base_url="https://api.deepseek.com")
        p.model = "bob-core-local"  # not deepseek-v4-*
        kwargs = {}
        ModelGateway._apply_deepseek_options(p, kwargs)
        assert "extra_body" not in kwargs


class TestGatewayInit:
    def test_empty_init(self):
        gw = ModelGateway()
        assert gw.providers == []
        assert gw.config.max_fallbacks == 2

    def test_providers_sorted_by_priority(self):
        gw = _gateway(
            _provider("c", priority=100),
            _provider("a", priority=-500),
            _provider("b", priority=0),
        )
        priorities = [p.priority for p in gw.providers]
        assert priorities == sorted(priorities)

    def test_config_passed(self):
        cfg = GatewayConfig(max_fallbacks=5, timeout_s=60)
        gw = ModelGateway(providers=[], config=cfg)
        assert gw.config.max_fallbacks == 5
        assert gw.config.timeout_s == 60
