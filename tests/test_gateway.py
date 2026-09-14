"""Smoke tests — ModelGateway routing, fallback, aliases (deterministico)."""

from typing import ClassVar

import pytest

import core.model_serving.gateway as gateway_module
from core.model_serving.gateway import ModelGateway
from core.model_serving.providers import (
    AGENT_MODEL_ID,
    AGENT_PROVIDER_NAME,
    BRAIN_MODEL_ID,
    DEEPSEEK_MODEL_ID,
    DEEPSEEK_PROVIDER_NAME,
    PRIMARY_PROVIDER_NAME,
    GatewayConfig,
    ModelProvider,
)
from core.resilience import CircuitBreaker, CircuitState


def _provider(
    name,
    priority=0,
    base_url="http://x/api",
    backend="cloud",
    model="test-model",
    degrade_model=None,
):
    kwargs = {} if degrade_model is None else {"degrade_model": degrade_model}
    return ModelProvider(
        name=name,
        base_url=base_url,
        priority=priority,
        api_key="",
        backend=backend,
        model=model,
        **kwargs,
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

    def test_no_preference_excludes_arbitration_roles(self):
        """T4: generic requests (no preferred_provider) must not fall back to
        the arbitration-only judge/auditor roles; deepseek stays eligible."""
        gw = _gateway(
            _provider(AGENT_PROVIDER_NAME, priority=-670),
            _provider("local_orchestrator", priority=-400),
            _provider("deepseek", priority=-300),
            _provider("daytrade_judge", priority=-304),
            _provider("daytrade_auditor", priority=-305),
        )
        result = gw._providers_for_request(None)
        names = [p.name for p in result]
        assert "daytrade_judge" not in names
        assert "daytrade_auditor" not in names
        assert "deepseek" in names
        assert names == ["local_orchestrator", "deepseek"]

    def test_glm_fallback_keeps_the_role_model_of_a_deciding_role(self, monkeypatch):
        """GLM credit fallback must respect the role: a deciding provider
        (degrade_model = brain) hops to DeepSeek on ITS model, never on the
        support one — and the shared deepseek provider is not mutated."""
        monkeypatch.delenv("SUPEREZIO_GLM_FALLBACK_TO_DEEPSEEK", raising=False)
        glm_agent = _provider(
            AGENT_PROVIDER_NAME,
            priority=-10,
            base_url="https://api.z.ai/api/coding/paas/v4",
            model="glm-5.3",
            degrade_model=BRAIN_MODEL_ID,
        )
        plain_deepseek = _provider(
            DEEPSEEK_PROVIDER_NAME,
            priority=-290,
            base_url="https://api.deepseek.com",
            model=DEEPSEEK_MODEL_ID,
        )
        gw = _gateway(glm_agent, plain_deepseek)

        result = gw._providers_for_request(AGENT_PROVIDER_NAME)

        assert [p.name for p in result] == [AGENT_PROVIDER_NAME, DEEPSEEK_PROVIDER_NAME]
        assert result[0].model == "glm-5.3"
        assert result[1].model == BRAIN_MODEL_ID == AGENT_MODEL_ID
        assert result[1].base_url == "https://api.deepseek.com"
        assert plain_deepseek.model == DEEPSEEK_MODEL_ID  # shared provider untouched
        stored = {p.name: p for p in gw.providers}
        assert stored[DEEPSEEK_PROVIDER_NAME].model == DEEPSEEK_MODEL_ID

    def test_glm_fallback_keeps_the_role_model_of_a_support_role(self, monkeypatch):
        """A support provider (default degrade_model = flash) keeps the support
        model on the same hop, reusing the existing deepseek provider object."""
        monkeypatch.delenv("SUPEREZIO_GLM_FALLBACK_TO_DEEPSEEK", raising=False)
        glm_judge = _provider(
            "daytrade_judge",
            priority=-304,
            base_url="https://api.z.ai/api/coding/paas/v4",
            model="glm-5.3",
        )
        plain_deepseek = _provider(
            DEEPSEEK_PROVIDER_NAME,
            priority=-290,
            base_url="https://api.deepseek.com",
            model=DEEPSEEK_MODEL_ID,
        )
        gw = _gateway(glm_judge, plain_deepseek)

        result = gw._providers_for_request("daytrade_judge")

        assert [p.name for p in result] == ["daytrade_judge", DEEPSEEK_PROVIDER_NAME]
        assert result[1] is plain_deepseek
        assert result[1].model == DEEPSEEK_MODEL_ID


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


class TestApplyGlmCodingPlanOptions:
    def test_non_glm_skipped(self):
        p = _provider("agent", base_url="https://api.deepseek.com")
        p.model = "deepseek-v4-pro"
        kwargs = {}
        ModelGateway._apply_glm_coding_plan_options(p, kwargs)
        assert "extra_body" not in kwargs

    def test_glm53_forces_thinking_enabled(self, monkeypatch):
        monkeypatch.setenv("SUPEREZIO_GLM_REASONING_EFFORT", "low")
        p = _provider("agent", base_url="https://api.z.ai/api/coding/paas/v4")
        p.model = "glm-5.3"
        kwargs = {}
        ModelGateway._apply_glm_coding_plan_options(p, kwargs)
        assert kwargs["extra_body"] == {
            "thinking": {"type": "enabled"},
            "reasoning_effort": "low",
        }

    def test_invalid_effort_falls_back_to_low(self, monkeypatch):
        monkeypatch.setenv("SUPEREZIO_GLM_REASONING_EFFORT", "banana")
        p = _provider("agent", base_url="https://api.z.ai/api/coding/paas/v4")
        p.model = "glm-5.3"
        kwargs = {}
        ModelGateway._apply_glm_coding_plan_options(p, kwargs)
        assert kwargs["extra_body"]["reasoning_effort"] == "low"


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


class TestStreamChatCompletion:
    @pytest.mark.asyncio
    async def test_strips_vision_messages_for_local_mouth(self, monkeypatch):
        gateway = _gateway(_provider(AGENT_PROVIDER_NAME, backend="openai_compatible"))
        captured = {}

        async def capture(**kwargs):
            captured.update(kwargs)
            yield "WAIT"

        monkeypatch.setattr(gateway, "stream_generate_async", capture)
        msgs = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "leia o grafico"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,xx"}},
                ],
            }
        ]
        chunks = [
            chunk
            async for chunk in gateway.stream_chat_completion(
                messages=msgs,
                json_mode=True,
                preferred_provider=AGENT_PROVIDER_NAME,
            )
        ]
        assert chunks == ["WAIT"]
        assert captured.get("messages") in (None, [])
        assert "leia o grafico" in captured["prompt"]
        assert "image_url" not in captured["prompt"]


class TestPortSignatureParity:
    """Testa paridade de assinatura entre Port e implementação."""

    def test_generate_api_signature_parity(self):
        """Port.generate_api tem os mesmos parâmetros que ModelGateway.generate_api."""
        import inspect

        from core.ports.model_gateway import ModelGatewayPort

        port_sig = inspect.signature(ModelGatewayPort.generate_api)
        impl_sig = inspect.signature(ModelGateway.generate_api)

        port_params = set(port_sig.parameters.keys())
        impl_params = set(impl_sig.parameters.keys())

        assert port_params == impl_params, f"Port params {port_params} != impl params {impl_params}"


class TestJsonModeWithImageWarning:
    """Testa warning emitido quando json_mode=True + imagem."""

    @pytest.mark.asyncio
    async def test_json_mode_with_image_emits_warning(self, caplog, monkeypatch):
        """json_mode=True + image_url deve emitir warning em generate_api."""
        import logging

        gateway = _gateway(_provider(DEEPSEEK_PROVIDER_NAME, backend="openai_compatible"))
        msgs = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "descreva"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
                ],
            }
        ]

        # Mock the AsyncOpenAI client to avoid actual API calls
        async def mock_create(*args, **kwargs):
            class MockChoice:
                class MockMessage:
                    content = "{}"

                message = MockMessage()

            class MockResponse:
                choices: ClassVar[list[MockChoice]] = [MockChoice()]

            return MockResponse()

        class MockClient:
            class MockChat:
                class MockCompletions:
                    create = mock_create

                completions = MockCompletions()

            chat = MockChat()

            async def close(self):
                pass

        monkeypatch.setattr(
            "core.model_serving.gateway.AsyncOpenAI", lambda *args, **kwargs: MockClient()
        )

        with caplog.at_level(logging.WARNING):
            await gateway.generate_api(
                provider=gateway.providers[0],
                messages=msgs,
                json_mode=True,
            )

        assert (
            "json_mode disabled: image content present (vision cannot emit structured JSON)"
            in caplog.text
        )

    @pytest.mark.asyncio
    async def test_json_mode_without_image_no_warning(self, caplog, monkeypatch):
        """json_mode=True sem imagem não deve emitir warning em generate_api."""
        import logging

        gateway = _gateway(_provider(AGENT_PROVIDER_NAME, backend="openai_compatible"))
        msgs = [{"role": "user", "content": "retorne JSON"}]

        # Mock the AsyncOpenAI client to avoid actual API calls
        async def mock_create(*args, **kwargs):
            class MockChoice:
                class MockMessage:
                    content = "{}"

                message = MockMessage()

            class MockResponse:
                choices: ClassVar[list[MockChoice]] = [MockChoice()]

            return MockResponse()

        class MockClient:
            class MockChat:
                class MockCompletions:
                    create = mock_create

                completions = MockCompletions()

            chat = MockChat()

            async def close(self):
                pass

        monkeypatch.setattr(
            "core.model_serving.gateway.AsyncOpenAI", lambda *args, **kwargs: MockClient()
        )

        with caplog.at_level(logging.WARNING):
            await gateway.generate_api(
                provider=gateway.providers[0],
                messages=msgs,
                json_mode=True,
            )

        assert "json_mode disabled" not in caplog.text


class TestStreamReasoningNeverVisible:
    """Contract 2026-09-05: raw reasoning_content (GLM-5.3/DeepSeek, no channel
    markers) must never surface as user-visible text. Before this pin, the
    stream emitted ``content or reasoning``, leaking the English CoT into the
    answer and burning max_tokens before the real PT content started."""

    @staticmethod
    def _make_client(chunks):
        class MockCompletions:
            def __init__(self, items):
                self._items = items

            async def _stream(self):
                for chunk in self._items:
                    yield chunk

            async def create(self, *_args, **_kwargs):
                return self._stream()

        class MockChat:
            def __init__(self, items):
                self.completions = MockCompletions(items)

        class MockClient:
            def __init__(self, items):
                self.chat = MockChat(items)

            async def close(self):
                pass

        return MockClient(chunks)

    @pytest.mark.asyncio
    async def test_reasoning_only_emits_nothing(self, monkeypatch):
        from types import SimpleNamespace

        delta = SimpleNamespace(
            content=None,
            reasoning_content=(
                "Let me analyze this carefully. The user is asking a general "
                "financial planning question... they live in Canada..."
            ),
        )
        chunk = SimpleNamespace(choices=[SimpleNamespace(delta=delta)])
        client = self._make_client([chunk, chunk, chunk])
        monkeypatch.setattr("core.model_serving.gateway.AsyncOpenAI", lambda *_a, **_k: client)

        gateway = _gateway(_provider(AGENT_PROVIDER_NAME, backend="openai_compatible"))
        provider = gateway.providers[0]
        out = [c async for c in gateway.stream_generate_api(provider, prompt="oi")]
        assert out == []

    @pytest.mark.asyncio
    async def test_reasoning_then_content_emits_only_content(self, monkeypatch):
        from types import SimpleNamespace

        reasoning = SimpleNamespace(
            content=None,
            reasoning_content=("Let me analyze this carefully... 1. Diagnóstico financeiro"),
        )
        real = SimpleNamespace(
            content="Vou analisar seu cenario em portugues.", reasoning_content=None
        )
        chunk = lambda d: SimpleNamespace(choices=[SimpleNamespace(delta=d)])
        client = self._make_client([chunk(reasoning), chunk(real)])
        monkeypatch.setattr("core.model_serving.gateway.AsyncOpenAI", lambda *_a, **_k: client)

        gateway = _gateway(_provider(AGENT_PROVIDER_NAME, backend="openai_compatible"))
        provider = gateway.providers[0]
        out = [c async for c in gateway.stream_generate_api(provider, prompt="oi")]
        assert out == ["Vou analisar seu cenario em portugues."]

    @pytest.mark.asyncio
    async def test_plain_content_still_streams(self, monkeypatch):
        from types import SimpleNamespace

        delta = SimpleNamespace(content="Resposta direta.", reasoning_content=None)
        chunk = SimpleNamespace(choices=[SimpleNamespace(delta=delta)])
        client = self._make_client([chunk])
        monkeypatch.setattr("core.model_serving.gateway.AsyncOpenAI", lambda *_a, **_k: client)

        gateway = _gateway(_provider(AGENT_PROVIDER_NAME, backend="openai_compatible"))
        provider = gateway.providers[0]
        out = [c async for c in gateway.stream_generate_api(provider, prompt="oi")]
        assert out == ["Resposta direta."]


class TestGenerateReasoningNeverVisible:
    """Non-streaming counterpart of the same contract: generate_api must not
    return raw reasoning_content as the visible answer."""

    @staticmethod
    def _make_client(message):
        from types import SimpleNamespace

        class MockCompletions:
            async def create(self, *_args, **_kwargs):
                return SimpleNamespace(choices=[SimpleNamespace(message=message)])

        class MockChat:
            completions = MockCompletions()

        class MockClient:
            chat = MockChat()

            async def close(self):
                pass

        return MockClient()

    @pytest.mark.asyncio
    async def test_reasoning_only_returns_empty(self, monkeypatch):
        from types import SimpleNamespace

        message = SimpleNamespace(
            content=None,
            reasoning_content="Let me analyze this carefully. They live in Canada...",
        )
        client = self._make_client(message)
        monkeypatch.setattr("core.model_serving.gateway.AsyncOpenAI", lambda *_a, **_k: client)

        gateway = _gateway(_provider(AGENT_PROVIDER_NAME, backend="openai_compatible"))
        provider = gateway.providers[0]
        out = await gateway.generate_api(provider, prompt="oi")
        assert out == ""

    @pytest.mark.asyncio
    async def test_content_wins_over_reasoning(self, monkeypatch):
        from types import SimpleNamespace

        message = SimpleNamespace(
            content="Resposta em portugues.",
            reasoning_content="Let me analyze this carefully...",
        )
        client = self._make_client(message)
        monkeypatch.setattr("core.model_serving.gateway.AsyncOpenAI", lambda *_a, **_k: client)

        gateway = _gateway(_provider(AGENT_PROVIDER_NAME, backend="openai_compatible"))
        provider = gateway.providers[0]
        out = await gateway.generate_api(provider, prompt="oi")
        assert out == "Resposta em portugues."


class TestGlmTokenFloor:
    """Contract 2026-09-05: GLM (thinking forced on, sharing the output
    budget) gets a 4096-token floor so the visible content survives the
    deliberation. Non-GLM providers keep their requested budget."""

    @staticmethod
    def _capture_client(captured: dict):
        from types import SimpleNamespace

        class MockCompletions:
            def __init__(self, box):
                self._box = box

            async def _stream(self):
                delta = SimpleNamespace(content="ok", reasoning_content=None)
                yield SimpleNamespace(choices=[SimpleNamespace(delta=delta)])

            async def create(self, *_args, **_kwargs):
                self._box.update(_kwargs)
                return self._stream()

        class MockChat:
            def __init__(self, box):
                self.completions = MockCompletions(box)

        class MockClient:
            def __init__(self, box):
                self.chat = MockChat(box)

            async def close(self):
                pass

        return MockClient(captured)

    @staticmethod
    def _glm_provider():
        p = _provider("agent", base_url="https://api.z.ai/api/coding/paas/v4")
        p.model = "glm-5.3"
        return p

    @pytest.mark.asyncio
    async def test_glm_stream_gets_4096_floor(self, monkeypatch):
        captured = {}
        monkeypatch.setattr(
            "core.model_serving.gateway.AsyncOpenAI",
            lambda *_a, **_k: self._capture_client(captured),
        )

        gateway = _gateway(self._glm_provider())
        provider = gateway.providers[0]
        out = [c async for c in gateway.stream_generate_api(provider, prompt="oi", max_tokens=100)]
        assert out == ["ok"]
        assert captured["max_tokens"] == 4096

    @pytest.mark.asyncio
    async def test_glm_generate_gets_4096_floor(self, monkeypatch):
        from types import SimpleNamespace

        captured = {}
        box = captured

        class MockCompletions:
            async def create(self, *_args, **_kwargs):
                box.update(_kwargs)
                return SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            message=SimpleNamespace(content="ok", reasoning_content=None)
                        )
                    ]
                )

        class MockChat:
            completions = MockCompletions()

        class MockClient:
            chat = MockChat()

            async def close(self):
                pass

        monkeypatch.setattr(
            "core.model_serving.gateway.AsyncOpenAI", lambda *_a, **_k: MockClient()
        )

        gateway = _gateway(self._glm_provider())
        provider = gateway.providers[0]
        out = await gateway.generate_api(provider, prompt="oi", max_tokens=100)
        assert out == "ok"
        assert captured["max_tokens"] == 4096

    @pytest.mark.asyncio
    async def test_deepseek_keeps_requested_budget(self, monkeypatch):
        captured = {}
        monkeypatch.setattr(
            "core.model_serving.gateway.AsyncOpenAI",
            lambda *_a, **_k: self._capture_client(captured),
        )

        p = _provider(DEEPSEEK_PROVIDER_NAME, base_url="https://api.deepseek.com")
        p.model = "deepseek-v4-pro"
        gateway = _gateway(p)
        provider = gateway.providers[0]
        out = [c async for c in gateway.stream_generate_api(provider, prompt="oi", max_tokens=100)]
        assert out == ["ok"]
        assert captured["max_tokens"] == 100


class TestRateLimitVsCircuit:
    """Contract 2026-09-05: an exhausted 429 (rate limit) must NOT open the
    circuit breaker — it has its own retry/cooldown policy, and a parallel
    burst (expert fan-out) would otherwise trip the 60s circuit for a quota
    condition that recovers on its own."""

    def test_rate_limit_exhausted_keeps_circuit_closed(self, monkeypatch):
        deepseek = _provider(DEEPSEEK_PROVIDER_NAME, priority=-300)
        gateway = _gateway(deepseek, retry_attempts=2, retry_delay_s=0)
        calls = 0

        async def fail_429(provider, *_args, **_kwargs):
            nonlocal calls
            calls += 1
            raise _HTTPFailure(429)
            yield  # pragma: no cover

        monkeypatch.setattr(gateway, "stream_generate_api", fail_429)
        # Threshold 1: even a single exhausted failure would open a normal
        # circuit — rate limit must keep it closed regardless.
        circuit = CircuitBreaker("test.rate-limit", failure_threshold=1)
        monkeypatch.setattr(gateway_module, "get_circuit", lambda *_a, **_k: circuit)

        chunks = list(gateway.stream_generate("prompt", preferred_provider=DEEPSEEK_PROVIDER_NAME))

        assert calls == 2  # retry_attempts=2 -> 2 attempts, all exhausted
        assert len(chunks) == 1 and "ERROR" in chunks[0]
        assert circuit.state == CircuitState.CLOSED  # 429 never opened it

    def test_permanent_failure_still_opens_circuit(self, monkeypatch):
        deepseek = _provider(DEEPSEEK_PROVIDER_NAME, priority=-300)
        gateway = _gateway(deepseek, retry_attempts=2, retry_delay_s=0)

        async def fail_401(provider, *_args, **_kwargs):
            raise _HTTPFailure(401)
            yield  # pragma: no cover

        monkeypatch.setattr(gateway, "stream_generate_api", fail_401)
        circuit = CircuitBreaker("test.permanent", failure_threshold=1)
        monkeypatch.setattr(gateway_module, "get_circuit", lambda *_a, **_k: circuit)

        list(gateway.stream_generate("prompt", preferred_provider=DEEPSEEK_PROVIDER_NAME))

        assert circuit.state == CircuitState.OPEN

    def test_daytrade_judge_fallback_to_deepseek_on_cooldown(self):
        import time

        from core.model_serving.providers import DAYTRADE_JUDGE_PROVIDER_NAME

        judge = _provider(DAYTRADE_JUDGE_PROVIDER_NAME, priority=-304, model="glm-5.2")
        deepseek = _provider(DEEPSEEK_PROVIDER_NAME, priority=-300, model="deepseek-v4-flash")
        gateway = _gateway(judge, deepseek)

        # In normal state with allow_fallback=True, both are available
        providers = gateway._providers_for_request(DAYTRADE_JUDGE_PROVIDER_NAME, allow_fallback=True)
        assert len(providers) == 2
        assert providers[0].name == DAYTRADE_JUDGE_PROVIDER_NAME
        assert providers[1].name == DEEPSEEK_PROVIDER_NAME

        # In cooldown, judge is skipped and deepseek is used
        gateway._provider_cooldown_until[DAYTRADE_JUDGE_PROVIDER_NAME] = time.monotonic() + 100
        fallback_providers = gateway._providers_for_request(DAYTRADE_JUDGE_PROVIDER_NAME, allow_fallback=True)
        assert len(fallback_providers) == 1
        assert fallback_providers[0].name == DEEPSEEK_PROVIDER_NAME

    def test_daytrade_auditor_fallback_to_deepseek_on_cooldown(self):
        from core.model_serving.providers import DAYTRADE_AUDITOR_PROVIDER_NAME

        auditor = _provider(DAYTRADE_AUDITOR_PROVIDER_NAME, priority=-305, model="glm-5.2")
        deepseek = _provider(DEEPSEEK_PROVIDER_NAME, priority=-300, model="deepseek-v4-flash")
        gateway = _gateway(auditor, deepseek)

        providers = gateway._providers_for_request(DAYTRADE_AUDITOR_PROVIDER_NAME, allow_fallback=True)
        assert len(providers) == 2
        assert providers[0].name == DAYTRADE_AUDITOR_PROVIDER_NAME
        assert providers[1].name == DEEPSEEK_PROVIDER_NAME
