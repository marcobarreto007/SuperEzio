"""Smoke tests — ModelGateway routing, fallback, aliases (deterministico)."""

import pytest
import core.model_serving.gateway as gateway_module
from core.model_serving.gateway import ModelGateway
from core.model_serving.providers import (
    ModelProvider,
    GatewayConfig,
    PRIMARY_PROVIDER_NAME,
    AGENT_PROVIDER_NAME,
    DEEPSEEK_PROVIDER_NAME,
)
from core.resilience import CircuitBreaker, CircuitState


def _provider(name, priority=0, base_url="http://x/api", backend="cloud"):
    return ModelProvider(
        name=name, base_url=base_url, priority=priority, api_key="", backend=backend
    )


def _gateway(*providers, max_fallbacks=2, retry_attempts=2, retry_delay_s=0):
    return ModelGateway(
        providers=list(providers),
        config=GatewayConfig(
            max_fallbacks=max_fallbacks,
            retry_attempts=retry_attempts,
            retry_delay_s=retry_delay_s,
        ),
    )


class _HTTPFailure(Exception):
    def __init__(self, status_code):
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code


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

    def test_deepseek_is_provider_pinned(self):
        gw = _gateway(
            _provider("deepseek", priority=-300),
            _provider("agent", priority=-670),
            _provider("grok", priority=-500),
        )
        result = gw._providers_for_request("deepseek")
        assert [provider.name for provider in result] == ["deepseek"]


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


class TestProviderFailurePolicy:
    def test_auth_failure_is_not_retried_or_fallbacked(self, monkeypatch):
        deepseek = _provider(DEEPSEEK_PROVIDER_NAME, priority=-300)
        local_qwen = _provider(AGENT_PROVIDER_NAME, priority=-200)
        local_qwen.is_local = True
        gateway = _gateway(deepseek, local_qwen, retry_attempts=4)
        calls = []

        async def fail_auth(provider, *_args, **_kwargs):
            calls.append(provider.name)
            raise _HTTPFailure(401)

        monkeypatch.setattr(gateway, "generate_api", fail_auth)
        circuit = CircuitBreaker("test.auth", failure_threshold=5, recovery_timeout=60)
        monkeypatch.setattr(gateway_module, "get_circuit", lambda *_args, **_kwargs: circuit)

        with pytest.raises(RuntimeError, match="failed permanently"):
            gateway.generate("prompt", preferred_provider=DEEPSEEK_PROVIDER_NAME)

        assert calls == [DEEPSEEK_PROVIDER_NAME]
        assert gateway.last_provider_used is None
        assert circuit.failure_count == 1

    @pytest.mark.parametrize("status_code", [400, 403, 404, 409, 422])
    def test_other_4xx_failures_are_not_retried(self, monkeypatch, status_code):
        gateway = _gateway(_provider(DEEPSEEK_PROVIDER_NAME), retry_attempts=3)
        calls = 0

        async def fail_request(*_args, **_kwargs):
            nonlocal calls
            calls += 1
            raise _HTTPFailure(status_code)

        monkeypatch.setattr(gateway, "generate_api", fail_request)
        monkeypatch.setattr(
            gateway_module,
            "get_circuit",
            lambda *_args, **_kwargs: CircuitBreaker("test.4xx"),
        )

        with pytest.raises(RuntimeError, match="failed permanently"):
            gateway.generate("prompt", preferred_provider=DEEPSEEK_PROVIDER_NAME)

        assert calls == 1

    @pytest.mark.parametrize("failure", [_HTTPFailure(429), _HTTPFailure(503), TimeoutError()])
    def test_transient_failure_retries_with_bounded_backoff(self, monkeypatch, failure):
        gateway = _gateway(
            _provider(DEEPSEEK_PROVIDER_NAME),
            retry_attempts=3,
            retry_delay_s=0.25,
        )
        calls = 0
        sleeps = []

        async def recover_on_third_call(*_args, **_kwargs):
            nonlocal calls
            calls += 1
            if calls < 3:
                raise failure
            return '{"verdict":"ABSTAIN"}'

        monkeypatch.setattr(gateway, "generate_api", recover_on_third_call)
        monkeypatch.setattr(gateway_module.time, "sleep", sleeps.append)
        circuit = CircuitBreaker("test.transient", failure_threshold=5)
        monkeypatch.setattr(gateway_module, "get_circuit", lambda *_args, **_kwargs: circuit)

        result = gateway.generate("prompt", preferred_provider=DEEPSEEK_PROVIDER_NAME)

        assert result == '{"verdict":"ABSTAIN"}'
        assert calls == 3
        assert sleeps == [0.25, 0.5]
        assert gateway.last_provider_used == DEEPSEEK_PROVIDER_NAME
        assert circuit.state == CircuitState.CLOSED

    def test_unknown_failure_is_not_retried(self, monkeypatch):
        gateway = _gateway(_provider(DEEPSEEK_PROVIDER_NAME), retry_attempts=3)
        calls = 0

        class _StoppedLoop:
            @staticmethod
            def is_running():
                return False

        async def fail_unknown(*_args, **_kwargs):
            nonlocal calls
            calls += 1
            raise RuntimeError("decoder invariant broke")

        monkeypatch.setattr(gateway, "generate_api", fail_unknown)
        monkeypatch.setattr(gateway_module.asyncio, "get_event_loop", lambda: _StoppedLoop())
        monkeypatch.setattr(
            gateway_module,
            "get_circuit",
            lambda *_args, **_kwargs: CircuitBreaker("test.unknown"),
        )

        with pytest.raises(RuntimeError, match="failed permanently"):
            gateway.generate("prompt", preferred_provider=DEEPSEEK_PROVIDER_NAME)

        assert calls == 1


class TestGatewayCircuitLifecycle:
    def test_circuit_opens_and_rejects_without_provider_call(self, monkeypatch):
        gateway = _gateway(_provider(DEEPSEEK_PROVIDER_NAME), retry_attempts=1)
        circuit = CircuitBreaker("test.open", failure_threshold=2, recovery_timeout=60)
        calls = 0

        async def fail(*_args, **_kwargs):
            nonlocal calls
            calls += 1
            raise _HTTPFailure(503)

        monkeypatch.setattr(gateway, "generate_api", fail)
        monkeypatch.setattr(gateway_module, "get_circuit", lambda *_args, **_kwargs: circuit)

        for _ in range(2):
            with pytest.raises(RuntimeError, match="All external providers failed"):
                gateway.generate("prompt", preferred_provider=DEEPSEEK_PROVIDER_NAME)
        assert circuit.state == CircuitState.OPEN

        with pytest.raises(RuntimeError, match="All external providers failed"):
            gateway.generate("prompt", preferred_provider=DEEPSEEK_PROVIDER_NAME)
        assert calls == 2

    def test_expired_open_circuit_half_opens_and_closes_on_success(self, monkeypatch):
        gateway = _gateway(_provider(DEEPSEEK_PROVIDER_NAME), retry_attempts=3)
        circuit = CircuitBreaker("test.recovery", failure_threshold=1, recovery_timeout=0)
        circuit.record_failure(_HTTPFailure(503))
        assert circuit.state == CircuitState.OPEN

        async def succeed(*_args, **_kwargs):
            return '{"verdict":"ABSTAIN"}'

        monkeypatch.setattr(gateway, "generate_api", succeed)
        monkeypatch.setattr(gateway_module, "get_circuit", lambda *_args, **_kwargs: circuit)

        assert gateway.generate("prompt", preferred_provider=DEEPSEEK_PROVIDER_NAME)
        assert circuit.state == CircuitState.CLOSED
        assert circuit.failure_count == 0

    def test_half_open_failure_reopens_without_retry_burst(self, monkeypatch):
        gateway = _gateway(_provider(DEEPSEEK_PROVIDER_NAME), retry_attempts=5)
        circuit = CircuitBreaker("test.reopen", failure_threshold=1, recovery_timeout=0)
        circuit.record_failure(_HTTPFailure(503))
        calls = 0

        async def fail_probe(*_args, **_kwargs):
            nonlocal calls
            calls += 1
            raise _HTTPFailure(503)

        monkeypatch.setattr(gateway, "generate_api", fail_probe)
        monkeypatch.setattr(gateway_module, "get_circuit", lambda *_args, **_kwargs: circuit)

        with pytest.raises(RuntimeError, match="All external providers failed"):
            gateway.generate("prompt", preferred_provider=DEEPSEEK_PROVIDER_NAME)

        assert calls == 1
        assert circuit.state == CircuitState.OPEN


class TestStreamingFailurePolicy:
    def test_sync_stream_permanent_failure_is_explicit_and_not_retried(self, monkeypatch):
        deepseek = _provider(DEEPSEEK_PROVIDER_NAME, priority=-300)
        local_qwen = _provider(AGENT_PROVIDER_NAME, priority=-200)
        local_qwen.is_local = True
        gateway = _gateway(deepseek, local_qwen, retry_attempts=4)
        calls = []

        async def fail_auth(provider, *_args, **_kwargs):
            calls.append(provider.name)
            raise _HTTPFailure(401)
            yield  # pragma: no cover - makes this an async generator

        monkeypatch.setattr(gateway, "stream_generate_api", fail_auth)
        monkeypatch.setattr(
            gateway_module,
            "get_circuit",
            lambda *_args, **_kwargs: CircuitBreaker("test.stream.auth"),
        )

        chunks = list(gateway.stream_generate("prompt", preferred_provider="deepseek"))

        assert calls == [DEEPSEEK_PROVIDER_NAME]
        assert chunks == ["[ERROR] Provider deepseek failed: _HTTPFailure."]
        assert gateway.last_provider_used is None

    @pytest.mark.asyncio
    async def test_async_stream_retries_transient_before_first_chunk(self, monkeypatch):
        gateway = _gateway(
            _provider(DEEPSEEK_PROVIDER_NAME),
            retry_attempts=3,
            retry_delay_s=0.25,
        )
        calls = 0
        sleeps = []

        async def recover(*_args, **_kwargs):
            nonlocal calls
            calls += 1
            if calls < 3:
                raise _HTTPFailure(429)
            yield '{"verdict":"ABSTAIN"}'

        async def fake_sleep(delay):
            sleeps.append(delay)

        monkeypatch.setattr(gateway, "stream_generate_api", recover)
        monkeypatch.setattr(gateway_module.asyncio, "sleep", fake_sleep)
        monkeypatch.setattr(
            gateway_module,
            "get_circuit",
            lambda *_args, **_kwargs: CircuitBreaker("test.stream.transient"),
        )

        chunks = [
            chunk
            async for chunk in gateway.stream_generate_async(
                "prompt", preferred_provider=DEEPSEEK_PROVIDER_NAME
            )
        ]

        assert chunks == ['{"verdict":"ABSTAIN"}']
        assert calls == 3
        assert sleeps == [0.25, 0.5]
        assert gateway.last_provider_used == DEEPSEEK_PROVIDER_NAME

    @pytest.mark.asyncio
    async def test_async_stream_never_retries_after_partial_output(self, monkeypatch):
        gateway = _gateway(_provider(DEEPSEEK_PROVIDER_NAME), retry_attempts=3)
        calls = 0

        async def partial_then_fail(*_args, **_kwargs):
            nonlocal calls
            calls += 1
            yield "partial"
            raise _HTTPFailure(503)

        monkeypatch.setattr(gateway, "stream_generate_api", partial_then_fail)
        monkeypatch.setattr(
            gateway_module,
            "get_circuit",
            lambda *_args, **_kwargs: CircuitBreaker("test.stream.partial"),
        )

        chunks = [
            chunk
            async for chunk in gateway.stream_generate_async(
                "prompt", preferred_provider=DEEPSEEK_PROVIDER_NAME
            )
        ]

        assert chunks == ["partial", "[ERROR] Provider deepseek failed: _HTTPFailure."]
        assert calls == 1
        assert gateway.last_provider_used is None
