"""
SuperEzio - Model Gateway
====================================
Gateway para modelos via API (external providers).
Suporta:
- APIs OpenAI-compatíveis
- Retry com exponential backoff
- Cascade entre múltiplos providers
"""

import asyncio
import logging
import time
from enum import Enum
from typing import AsyncGenerator, List, Dict, Any, Generator

from ..observability.neural_log import log_event, trace_span, SpanContext, metrics
from .sanitizer import PrivateChannelFilter, strip_private_model_channels
from ..resilience import CircuitOpenError, CircuitState, get_circuit

# OpenAI SDK for external API operations
from openai import AsyncOpenAI

# Re-export from providers module for backward compatibility
from .providers import (  # noqa: F401 — re-exports
    ModelProvider,
    GatewayConfig,
    PRIMARY_PROVIDER_NAME,
    PRIMARY_MODEL_ID,
    DEEPSEEK_PROVIDER_NAME,
    AGENT_PROVIDER_NAME,
    DAYTRADE_JUDGE_PROVIDER_NAME,
    DAYTRADE_AUDITOR_PROVIDER_NAME,
    build_default_providers,
)
from ..config.secrets import load_local_env

logger = logging.getLogger(__name__)

# Local llama window is 8192 tokens. Guard thresholds: reject above HARD (the
# request would die with a raw 400), warn near the limit (generation also needs
# headroom). Estimates are conservative: ~3.5 chars/token for PT/EN text and
# 768 tokens per image (llama.cpp mmproj patch heuristic) — over-estimating is
# the safe direction for a fail-fast guard.
LOCAL_CONTEXT_HARD_TOKEN_CAP = 8000
_LOCAL_CONTEXT_IMAGE_TOKENS = 768


def local_context_fits(messages: List[Dict[str, str]]) -> tuple[bool, int, str]:
    """Estimate input tokens and decide whether they fit the local window.

    Returns (fits, estimated_tokens, reason). Pure and deterministic — no I/O.
    """
    estimated = 0
    for message in messages:
        content = message.get("content", "")
        if isinstance(content, list):
            for part in content:
                if not isinstance(part, dict):
                    continue
                part_type = part.get("type")
                if part_type == "text":
                    estimated += len(str(part.get("text") or "")) // 3
                elif part_type == "image_url":
                    estimated += _LOCAL_CONTEXT_IMAGE_TOKENS
        else:
            estimated += len(str(content or "")) // 3
    if estimated > LOCAL_CONTEXT_HARD_TOKEN_CAP:
        return False, estimated, "over_hard_cap"
    return True, estimated, "fits"


def _has_image_content(messages: List[Dict[str, Any]] | None) -> bool:
    """True when any message carries an OpenAI image_url part."""
    for msg in messages or []:
        if not isinstance(msg, dict):
            continue
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if isinstance(part, dict) and part.get("type") == "image_url":
                return True
    return False


def _openai_messages(raw: List[Dict[str, Any]] | None) -> List[Dict[str, Any]]:
    """Drop internal keys (e.g. _chart_facts) before the provider call."""
    out: List[Dict[str, Any]] = []
    for msg in raw or []:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        if role not in {"system", "user", "assistant"}:
            continue
        out.append({"role": role, "content": msg.get("content")})
    return out


class _FailureKind(Enum):
    """Internal retry classification for provider failures."""

    TRANSIENT = "transient"
    PERMANENT = "permanent"


class ModelGateway:
    """
    Gateway para modelos com fallback em cascata.

    Fluxo:
    1. Tenta o modelo primário (ou preferido)
    2. Se falhar, tenta o próximo na lista
    3. Retry com exponential backoff
    4. Retorna erro gracioso se todos falharem
    """

    def __init__(
        self,
        providers: List[ModelProvider] = None,
        config: GatewayConfig = None,
        audit=None,
    ):
        self.providers = sorted(providers or [], key=lambda p: p.priority)
        self.config = config or GatewayConfig()
        self._audit = audit
        self._provider_errors: dict[str, int] = {}  # consecutive error counter
        self._provider_cooldown_until: dict[str, float] = {}  # timestamp until provider is skipped
        self._provider_cooldown_max_errors = 3  # consecutive errors before cooldown
        self._provider_cooldown_seconds = 120  # cooldown duration

        log_event(
            "MODEL_GATEWAY",
            "INIT",
            {
                "providers": [p.name for p in self.providers],
                "max_fallbacks": self.config.max_fallbacks,
            },
        )

    def add_provider(self, provider: ModelProvider) -> None:
        """Adiciona um provedor."""
        self.providers.append(provider)
        self.providers.sort(key=lambda p: p.priority)

    def _primary_provider(self) -> ModelProvider:
        for provider in self.providers:
            if provider.name == PRIMARY_PROVIDER_NAME:
                return provider
        # Fallback para o primeiro disponível se primary não estiver presente
        if self.providers:
            return self.providers[0]
        raise RuntimeError("No model provider is available.")

    def _providers_for_request(
        self, preferred_provider: str = None, allow_fallback: bool = True
    ) -> list[ModelProvider]:
        """Policy: prioritizes the requested provider, falls back to list order.

        Providers in cooldown (after consecutive failures) are skipped so that
        a broken external API (e.g. Gemini) does not waste time on every request.
        """
        if preferred_provider == "openai":
            preferred_provider = DEEPSEEK_PROVIDER_NAME
        if preferred_provider == "bob":
            preferred_provider = AGENT_PROVIDER_NAME

        now = time.monotonic()

        def _skip_cooldown(name: str) -> bool:
            until = self._provider_cooldown_until.get(name)
            if until is not None and now < until:
                return True
            if until is not None:
                del self._provider_cooldown_until[name]
                self._provider_errors.pop(name, None)
            return False

        if preferred_provider:
            for p in self.providers:
                if p.name == preferred_provider:
                    # Zero-cloud (operator directive 2026-08-17): the agent/CEO
                    # is local-only — no cloud fallback exists. If :8080 is down,
                    # the call must fail so the caller can enter MAN_AT_WORK.
                    # DeepSeek calls are also provider-pinned. Expert responses
                    # carry role/model provenance; silently replacing DeepSeek
                    # with Qwen (or a different external model) would turn a
                    # failed DeepSeek evaluation into apparently valid evidence.
                    if (
                        p.name
                        in {
                            AGENT_PROVIDER_NAME,
                            DEEPSEEK_PROVIDER_NAME,
                            DAYTRADE_JUDGE_PROVIDER_NAME,
                            DAYTRADE_AUDITOR_PROVIDER_NAME,
                        }
                        or not allow_fallback
                    ):
                        return [p]
                    return [p] + [
                        other
                        for other in self.providers
                        if other != p
                        and other.name != AGENT_PROVIDER_NAME
                        and not _skip_cooldown(other.name)
                    ]
        # No preferred provider: keep external-provider order and avoid routing
        # generic tasks to local agent runtime. Arbitration-only roles
        # (daytrade judge/auditor) are not generic fallbacks either — a generic
        # task routed to them would spend external DeepSeek tokens outside the
        # arbitration flow. The plain deepseek provider stays eligible.
        non_local = [
            p
            for p in self.providers
            if p.name
            not in {
                AGENT_PROVIDER_NAME,
                DAYTRADE_JUDGE_PROVIDER_NAME,
                DAYTRADE_AUDITOR_PROVIDER_NAME,
            }
            and not _skip_cooldown(p.name)
        ]
        return non_local or self.providers

    def _max_attempts(self, providers_to_try: list[ModelProvider]) -> int:
        if not providers_to_try:
            return 0
        return min(len(providers_to_try), max(0, self.config.max_fallbacks) + 1)

    @staticmethod
    def _classify_provider_failure(exc: Exception) -> _FailureKind:
        """Classify only known recoverable failures as transient.

        HTTP 429 and 5xx responses, timeouts and connection failures may
        recover. Authentication and all other 4xx responses are permanent for
        the current request/configuration and must never be retried. Unknown
        exceptions default to permanent so programming/validation errors do
        not create retry storms.
        """

        response = getattr(exc, "response", None)
        status = getattr(exc, "status_code", None) or getattr(response, "status_code", None)
        if isinstance(status, int):
            if status == 429 or status == 408 or 500 <= status <= 599:
                return _FailureKind.TRANSIENT
            if 400 <= status <= 499:
                return _FailureKind.PERMANENT

        if isinstance(exc, (asyncio.TimeoutError, TimeoutError, ConnectionError)):
            return _FailureKind.TRANSIENT

        error_name = type(exc).__name__.lower()
        if any(
            token in error_name
            for token in (
                "timeout",
                "connection",
                "ratelimit",
                "servererror",
                "serviceunavailable",
            )
        ):
            return _FailureKind.TRANSIENT
        if any(
            token in error_name
            for token in (
                "authentication",
                "permissiondenied",
                "badrequest",
                "notfound",
                "unprocessable",
                "conflict",
            )
        ):
            return _FailureKind.PERMANENT
        return _FailureKind.PERMANENT

    @staticmethod
    def _record_circuit_state(provider_name: str, circuit) -> None:
        """Expose CLOSED=0, OPEN=1, HALF_OPEN=2 through existing metrics."""

        state_value = {
            CircuitState.CLOSED: 0,
            CircuitState.OPEN: 1,
            CircuitState.HALF_OPEN: 2,
        }[circuit.state]
        metrics.observe(f"model.{provider_name}.circuit_state", state_value)
        log_event(
            "MODEL_GATEWAY",
            "CIRCUIT_STATE",
            {
                "provider": provider_name,
                "state": circuit.state.value,
                "state_value": state_value,
                "failures": circuit.failure_count,
            },
        )

    @classmethod
    def _circuit_allows_attempt(cls, provider_name: str, circuit) -> bool:
        """Advance an expired OPEN circuit to HALF_OPEN for one probe."""

        previous_state = circuit.state
        allowed = circuit.allow_request()
        if previous_state == CircuitState.OPEN and circuit.state == CircuitState.HALF_OPEN:
            metrics.increment(f"model.{provider_name}.circuit_half_open")
        cls._record_circuit_state(provider_name, circuit)
        return allowed

    def _record_provider_error(
        self,
        provider: ModelProvider,
        exc: Exception,
        failure_kind: _FailureKind,
    ) -> None:
        """Record one failed API attempt without changing the public API."""

        err_count = self._provider_errors.get(provider.name, 0) + 1
        self._provider_errors[provider.name] = err_count
        event = (
            "PROVIDER_TRANSIENT_ERROR"
            if failure_kind is _FailureKind.TRANSIENT
            else "PROVIDER_PERMANENT_ERROR"
        )
        log_event(
            "MODEL_GATEWAY",
            event,
            {
                "provider": provider.name,
                "error_type": type(exc).__name__,
                "consecutive_errors": err_count,
            },
        )
        metrics.increment(f"model.{provider.name}.error")
        metrics.increment(f"model.{provider.name}.{failure_kind.value}_error")

        if err_count >= self._provider_cooldown_max_errors:
            self._provider_cooldown_until[provider.name] = (
                time.monotonic() + self._provider_cooldown_seconds
            )
            log_event(
                "MODEL_GATEWAY",
                "PROVIDER_COOLDOWN",
                {
                    "provider": provider.name,
                    "consecutive_errors": err_count,
                    "cooldown_s": self._provider_cooldown_seconds,
                },
            )

    @staticmethod
    def _apply_deepseek_options(provider: ModelProvider, kwargs: Dict[str, Any]) -> None:
        """Apply DeepSeek V4 thinking controls for OpenAI-compatible calls."""
        import os

        if provider.name not in {
            DEEPSEEK_PROVIDER_NAME,
            PRIMARY_PROVIDER_NAME,
            "openai",
        } and "api.deepseek.com" not in (provider.base_url or ""):
            return
        if not provider.model.startswith("deepseek-v4-"):
            return

        thinking = os.getenv("SUPEREZIO_DEEPSEEK_THINKING", "disabled").lower()
        if thinking not in {"enabled", "disabled"}:
            thinking = "disabled"

        kwargs["extra_body"] = {"thinking": {"type": thinking}}
        if thinking == "enabled":
            kwargs["reasoning_effort"] = os.getenv("SUPEREZIO_DEEPSEEK_REASONING_EFFORT", "high")
            kwargs.pop("temperature", None)

    async def stream_generate_api(
        self,
        provider: ModelProvider,
        prompt: str = "",
        system_prompt: str = "",
        max_tokens: int | None = None,
        temperature: float | None = None,
        json_mode: bool = False,
        assistant_prefix: str = "",
        tools: List[Dict[str, Any]] | None = None,
        messages: List[Dict[str, Any]] | None = None,
    ) -> AsyncGenerator[str, None]:
        """Gera resposta via API OpenAI-compatible (Streaming).

        assistant_prefix: texto inicial forçado na resposta do assistente.
        Injeta como mensagem role=assistant no final da lista — impede que o
        modelo dispare filtros de recusa antes de gerar conteúdo (prefill trick).
        messages: when set, sent as-is (vision image_url parts included).
        """
        client = AsyncOpenAI(
            base_url=provider.base_url,
            api_key=provider.api_key,
            timeout=provider.timeout_s,
        )

        if messages:
            api_messages = _openai_messages(messages)
        else:
            api_messages = []
            if system_prompt:
                api_messages.append({"role": "system", "content": system_prompt})
            api_messages.append({"role": "user", "content": prompt})
        if assistant_prefix:
            api_messages.append({"role": "assistant", "content": assistant_prefix})

        tok = max_tokens if max_tokens is not None else provider.max_tokens
        temp = temperature if temperature is not None else provider.temperature
        if json_mode and _has_image_content(api_messages):
            logger.warning(
                "json_mode disabled: image content present (vision cannot emit structured JSON)"
            )
        use_json = bool(json_mode) and not _has_image_content(api_messages)

        kwargs = {
            "model": provider.model,
            "messages": api_messages,
            "max_tokens": tok,
            "temperature": temp,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = tools

        self._apply_deepseek_options(provider, kwargs)
        if use_json:
            kwargs["response_format"] = {"type": "json_object"}

        try:
            stream = await client.chat.completions.create(**kwargs)

            channel_filter = PrivateChannelFilter()
            if assistant_prefix:
                prefix = channel_filter.feed(assistant_prefix)
                if prefix:
                    yield prefix

            async for chunk in stream:
                delta = chunk.choices[0].delta
                # Thinking models (Qwen3.6) put reasoning in a separate field;
                # we stream both so the pipeline never receives empty output.
                content = delta.content or ""
                reasoning = getattr(delta, "reasoning_content", None) or ""
                text = content or reasoning
                if text:
                    clean = channel_filter.feed(text)
                    if clean:
                        yield clean

            tail = channel_filter.flush()
            if tail:
                yield tail
        finally:
            await client.close()

    async def generate_api(
        self,
        provider: ModelProvider,
        prompt: str = "",
        system_prompt: str = "",
        max_tokens: int | None = None,
        temperature: float | None = None,
        json_mode: bool = False,
        assistant_prefix: str = "",
        messages: List[Dict[str, Any]] | None = None,
    ) -> str:
        """Gera resposta via API OpenAI-compatible (Não-streaming).

        assistant_prefix: injeta mensagem role=assistant antes da geração
        para contornar filtros de recusa do modelo (prefill trick).
        messages: when set, sent as-is (vision image_url parts included).
        json_mode is forced off when an image is present.
        """
        client = AsyncOpenAI(
            base_url=provider.base_url,
            api_key=provider.api_key,
            timeout=provider.timeout_s,
        )

        if messages:
            api_messages = _openai_messages(messages)
        else:
            api_messages = []
            if system_prompt:
                api_messages.append({"role": "system", "content": system_prompt})
            api_messages.append({"role": "user", "content": prompt})
        if assistant_prefix:
            api_messages.append({"role": "assistant", "content": assistant_prefix})

        tok = max_tokens if max_tokens is not None else provider.max_tokens
        temp = temperature if temperature is not None else provider.temperature
        if json_mode and _has_image_content(api_messages):
            logger.warning(
                "json_mode disabled: image content present (vision cannot emit structured JSON)"
            )
        use_json = bool(json_mode) and not _has_image_content(api_messages)

        kwargs = {
            "model": provider.model,
            "messages": api_messages,
            "max_tokens": tok,
            "temperature": temp,
        }
        self._apply_deepseek_options(provider, kwargs)
        if use_json:
            kwargs["response_format"] = {"type": "json_object"}

        try:
            response = await client.chat.completions.create(**kwargs)
            msg = response.choices[0].message
            # Thinking models may return the answer in reasoning_content
            # when content is empty (all tokens spent on reasoning).
            text = msg.content or getattr(msg, "reasoning_content", None) or ""
            result = (assistant_prefix + text) if assistant_prefix else text
            return strip_private_model_channels(result)
        finally:
            await client.close()

    def _retry_attempts_for(self, circuit) -> int:
        """HALF_OPEN is a single recovery probe, never a retry burst."""
        return 1 if circuit.state == CircuitState.HALF_OPEN else max(1, self.config.retry_attempts)

    def _mark_provider_success(self, provider_name: str, circuit) -> None:
        """Reset failure state and record a successful provider response."""
        circuit.record_success()
        self._record_circuit_state(provider_name, circuit)
        self._provider_errors.pop(provider_name, None)
        self._provider_cooldown_until.pop(provider_name, None)
        self.last_provider_used = provider_name

    def _mark_provider_exhausted(
        self,
        provider_name: str,
        circuit,
        exc: Exception,
        next_name: str | None,
        event: str,
        failure_kind: _FailureKind,
    ) -> None:
        """Record failure after retries are exhausted and log the fallback hop."""
        circuit.record_failure(exc)
        self._record_circuit_state(provider_name, circuit)
        if next_name is not None:
            log_event(
                "MODEL_GATEWAY",
                event,
                {
                    "from_provider": provider_name,
                    "to_provider": next_name,
                    "failure_kind": failure_kind.value,
                },
            )

    @trace_span("gateway.generate")
    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        max_tokens: int | None = None,
        temperature: float | None = None,
        preferred_provider: str = None,
        json_mode: bool = False,
        assistant_prefix: str = "",
        allow_fallback: bool = True,
        messages: List[Dict[str, Any]] | None = None,
    ) -> str:
        """Gera resposta com fallback cascade (Síncrono para compatibilidade).

        allow_fallback=False restricts the attempt to the preferred provider
        only. The agent/CEO provider never falls back to another provider
        (zero-cloud policy, 2026-08-17) — if the local server is down the call
        fails so the caller can enter MAN_AT_WORK.
        Required for research/audit modes where the caller must know exactly
        which model answered (see audit/component_lab/reports/phase2_model_gateway.md).
        """
        providers_to_try = self._providers_for_request(
            preferred_provider, allow_fallback=allow_fallback
        )

        max_attempts = self._max_attempts(providers_to_try)
        last_error = None
        self.last_provider_used: str | None = None

        for i in range(max_attempts):
            provider = providers_to_try[i]
            log_event("MODEL_GATEWAY", "ATTEMPTING", {"provider": provider.name})

            # ── Circuit breaker gate ──
            _cb = get_circuit(f"model.{provider.name}", failure_threshold=5, recovery_timeout=60)
            if not self._circuit_allows_attempt(provider.name, _cb):
                next_name = (
                    providers_to_try[i + 1].name if i + 1 < len(providers_to_try) else "NONE"
                )
                logger.warning(
                    "CIRCUIT_OPEN: %s after %d failures, falling back to %s",
                    provider.name,
                    _cb.failure_count,
                    next_name,
                )
                last_error = CircuitOpenError(f"Circuit model.{provider.name} is OPEN")
                continue

            retry_attempts = self._retry_attempts_for(_cb)
            provider_error: Exception | None = None
            for retry_index in range(retry_attempts):
                try:
                    with SpanContext(f"provider.{provider.name}"):
                        # External API sync bridge
                        try:
                            loop = asyncio.get_event_loop()
                        except RuntimeError:
                            loop = None

                        if loop is not None and loop.is_running():
                            import concurrent.futures

                            with concurrent.futures.ThreadPoolExecutor() as executor:
                                future = executor.submit(
                                    lambda: asyncio.run(
                                        self.generate_api(
                                            provider,
                                            prompt,
                                            system_prompt,
                                            max_tokens,
                                            temperature,
                                            json_mode,
                                            assistant_prefix,
                                            messages,
                                        )
                                    )
                                )
                                result = future.result()
                        else:
                            result = asyncio.run(
                                self.generate_api(
                                    provider,
                                    prompt,
                                    system_prompt,
                                    max_tokens,
                                    temperature,
                                    json_mode,
                                    assistant_prefix,
                                    messages,
                                )
                            )

                        metrics.increment(f"model.{provider.name}.success")
                        self._mark_provider_success(provider.name, _cb)
                        return result

                except Exception as e:
                    last_error = e
                    provider_error = e
                    failure_kind = self._classify_provider_failure(e)
                    self._record_provider_error(provider, e, failure_kind)

                    if failure_kind is _FailureKind.PERMANENT:
                        _cb.record_failure(e)
                        self._record_circuit_state(provider.name, _cb)
                        metrics.increment(f"model.{provider.name}.retry_suppressed")
                        raise RuntimeError(
                            f"Provider {provider.name} failed permanently: {type(e).__name__}"
                        ) from e

                    if retry_index < retry_attempts - 1:
                        delay = self.config.retry_delay_s * (2**retry_index)
                        metrics.increment(f"model.{provider.name}.retry")
                        log_event(
                            "MODEL_GATEWAY",
                            "PROVIDER_RETRY",
                            {
                                "provider": provider.name,
                                "attempt": retry_index + 2,
                                "max_attempts": retry_attempts,
                                "delay_s": delay,
                            },
                        )
                        time.sleep(delay)

            # ── Circuit breaker: record failure after all retries exhausted ──
            if provider_error is not None:
                self._mark_provider_exhausted(
                    provider.name,
                    _cb,
                    provider_error,
                    providers_to_try[i + 1].name if i + 1 < max_attempts else None,
                    "PROVIDER_FALLBACK",
                    _FailureKind.TRANSIENT,
                )

        metrics.increment("model.all_failed")
        raise RuntimeError(f"All external providers failed. Last error: {last_error}")

    def stream_generate(
        self,
        prompt: str,
        system_prompt: str = "",
        max_tokens: int | None = None,
        temperature: float | None = None,
        preferred_provider: str = None,
        assistant_prefix: str = "",
    ) -> Generator[str, None, None]:
        """Stream generate com fallback (Síncrono para compatibilidade)."""
        providers_to_try = self._providers_for_request(preferred_provider)

        max_attempts = self._max_attempts(providers_to_try)
        self.last_provider_used = None

        for i in range(max_attempts):
            provider = providers_to_try[i]
            circuit = get_circuit(
                f"model.{provider.name}", failure_threshold=5, recovery_timeout=60
            )
            if not self._circuit_allows_attempt(provider.name, circuit):
                continue

            retry_attempts = self._retry_attempts_for(circuit)
            for retry_index in range(retry_attempts):
                emitted = False
                try:
                    # External Async Bridge
                    import queue
                    import threading

                    q: queue.Queue = queue.Queue()

                    def run_async_stream():
                        async def task():
                            try:
                                async for chunk in self.stream_generate_api(
                                    provider,
                                    prompt,
                                    system_prompt,
                                    max_tokens,
                                    temperature,
                                    assistant_prefix=assistant_prefix,
                                ):
                                    q.put(chunk)
                                q.put(None)
                            except Exception as exc:
                                q.put(exc)
                                q.put(None)

                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        loop.run_until_complete(task())
                        loop.close()

                    threading.Thread(target=run_async_stream, daemon=True).start()

                    while True:
                        item = q.get()
                        if item is None:
                            break
                        if isinstance(item, Exception):
                            raise item
                        emitted = True
                        yield item
                    self._mark_provider_success(provider.name, circuit)
                    return
                except Exception as exc:
                    failure_kind = self._classify_provider_failure(exc)
                    self._record_provider_error(provider, exc, failure_kind)
                    if emitted or failure_kind is _FailureKind.PERMANENT:
                        circuit.record_failure(exc)
                        self._record_circuit_state(provider.name, circuit)
                        metrics.increment(f"model.{provider.name}.retry_suppressed")
                        yield f"[ERROR] Provider {provider.name} failed: {type(exc).__name__}."
                        return
                    if retry_index < retry_attempts - 1:
                        delay = self.config.retry_delay_s * (2**retry_index)
                        metrics.increment(f"model.{provider.name}.retry")
                        time.sleep(delay)
                        continue
                    self._mark_provider_exhausted(
                        provider.name,
                        circuit,
                        exc,
                        providers_to_try[i + 1].name if i + 1 < max_attempts else None,
                        "STREAM_FALLBACK",
                        failure_kind,
                    )

        yield "[ERROR] Todos os modelos de nuvem falharam."

    async def stream_generate_async(
        self,
        prompt: str,
        system_prompt: str = "",
        max_tokens: int | None = None,
        temperature: float | None = None,
        preferred_provider: str = None,
        assistant_prefix: str = "",
        allow_fallback: bool = True,
        tools: List[Dict[str, Any]] | None = None,
        messages: List[Dict[str, Any]] | None = None,
        json_mode: bool = False,
    ) -> "AsyncGenerator[str, None]":
        """Stream generate Assíncrono (Non-blocking)."""

        import uuid

        request_id = uuid.uuid4().hex[:12]
        providers_to_try = self._providers_for_request(
            preferred_provider,
            allow_fallback=allow_fallback,
        )
        max_attempts = self._max_attempts(providers_to_try)
        attempted: list[str] = []
        self.last_provider_used = None

        for i in range(max_attempts):
            provider = providers_to_try[i]
            attempted.append(provider.name)
            circuit = get_circuit(
                f"model.{provider.name}", failure_threshold=5, recovery_timeout=60
            )
            if not self._circuit_allows_attempt(provider.name, circuit):
                continue

            retry_attempts = self._retry_attempts_for(circuit)
            for retry_index in range(retry_attempts):
                emitted = False
                try:
                    async for chunk in self.stream_generate_api(
                        provider,
                        prompt,
                        system_prompt=system_prompt,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        json_mode=json_mode,
                        assistant_prefix=assistant_prefix,
                        tools=tools,
                        messages=messages,
                    ):
                        emitted = True
                        yield chunk
                    self._mark_provider_success(provider.name, circuit)
                    if self._audit:
                        self._audit.record_decision(
                            run_id=request_id,
                            step="gateway_fallback",
                            decision=provider.name,
                            rationale={
                                "preferred": preferred_provider,
                                "attempted": attempted,
                                "success": True,
                            },
                        )
                    return
                except Exception as exc:
                    failure_kind = self._classify_provider_failure(exc)
                    self._record_provider_error(provider, exc, failure_kind)
                    if emitted or failure_kind is _FailureKind.PERMANENT:
                        circuit.record_failure(exc)
                        self._record_circuit_state(provider.name, circuit)
                        metrics.increment(f"model.{provider.name}.retry_suppressed")
                        yield f"[ERROR] Provider {provider.name} failed: {type(exc).__name__}."
                        return
                    if retry_index < retry_attempts - 1:
                        delay = self.config.retry_delay_s * (2**retry_index)
                        metrics.increment(f"model.{provider.name}.retry")
                        await asyncio.sleep(delay)
                        continue
                    self._mark_provider_exhausted(
                        provider.name,
                        circuit,
                        exc,
                        providers_to_try[i + 1].name if i + 1 < max_attempts else None,
                        "ASYNC_STREAM_FALLBACK",
                        failure_kind,
                    )
        if self._audit:
            self._audit.record_decision(
                run_id=request_id,
                step="gateway_fallback",
                decision="ALL_FAILED",
                rationale={
                    "preferred": preferred_provider,
                    "attempted": attempted,
                    "success": False,
                },
            )
        yield "[ERROR] Todos os modelos de nuvem falharam (Async)."

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        json_mode: bool = False,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        preferred_provider: str = None,
        assistant_prefix: str = "",
        allow_fallback: bool = True,
    ) -> str:
        """OpenAI-compatible async proxy.

        Se a última mensagem for role=assistant, extrai como assistant_prefix
        (ou usa o parâmetro explícito assistant_prefix).

        allow_fallback=False forces the exact preferred_provider (no silent
        cascade to another provider/model). Callers that need to know which
        provider actually answered should read gateway.last_provider_used
        immediately after awaiting this call.
        """
        provider_obj = self._providers_for_request(
            preferred_provider, allow_fallback=allow_fallback
        )[0]

        # ── Local-context pre-flight guard ──
        # The local llama window is 8192 tokens. Requests far beyond it were
        # rejected by llama-server with a raw 400 (demo failure 24/08: two
        # requests of 34k-37k tokens), surfacing as "runtime error". Fail here
        # first, with an actionable message, instead of sending garbage.
        if provider_obj.name in ("agent", "local_orchestrator"):
            ok, estimated, _reason = local_context_fits(messages)
            if not ok:
                raise RuntimeError(
                    "local_context_exceeded: prompt estimates at ~"
                    f"{estimated} tokens, the local window is 8192. "
                    "Shorten the conversation (or attach fewer images) and retry."
                )
            if estimated > 6500:
                logger.warning("local_context_near_limit: %s tokens of 8192", estimated)

        # Extrai assistant prefix do último message se role=assistant
        prefix = assistant_prefix
        msgs = list(messages)
        if msgs and msgs[-1].get("role") == "assistant":
            prefix = prefix or msgs[-1].get("content", "")
            msgs = msgs[:-1]

        # Vision: keep native OpenAI messages so image_url parts reach llama-server.
        # Text-only stays on the flattened prompt path (existing Bob contract).
        import functools

        if _has_image_content(msgs):
            func = functools.partial(
                self.generate,
                prompt="",
                system_prompt="",
                max_tokens=max_tokens,
                temperature=temperature,
                preferred_provider=provider_obj.name,
                json_mode=False,
                assistant_prefix=prefix,
                allow_fallback=allow_fallback,
                messages=msgs,
            )
            return await asyncio.to_thread(func)

        prompt = ""
        system_prompt = ""
        for msg in msgs:
            content = msg.get("content", "")
            if msg["role"] == "system":
                system_prompt = content if isinstance(content, str) else str(content)
            else:
                prompt += f"\n{msg['role'].capitalize()}: {content}"

        func = functools.partial(
            self.generate,
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            preferred_provider=provider_obj.name,
            json_mode=json_mode,
            assistant_prefix=prefix,
            allow_fallback=allow_fallback,
        )
        return await asyncio.to_thread(func)

    async def stream_chat_completion(
        self,
        messages: List[Dict[str, Any]],
        json_mode: bool = False,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        preferred_provider: str = None,
        assistant_prefix: str = "",
        allow_fallback: bool = True,
    ) -> AsyncGenerator[str, None]:
        """Stream OpenAI-compatible chat; yields tokens until the decision is complete."""
        prefix = assistant_prefix
        msgs = list(messages)
        if msgs and msgs[-1].get("role") == "assistant":
            content = msgs[-1].get("content", "")
            prefix = prefix or (content if isinstance(content, str) else "")
            msgs = msgs[:-1]

        if _has_image_content(msgs):
            async for chunk in self.stream_generate_async(
                prompt="",
                system_prompt="",
                max_tokens=max_tokens,
                temperature=temperature,
                preferred_provider=preferred_provider,
                assistant_prefix=prefix,
                allow_fallback=allow_fallback,
                messages=msgs,
                json_mode=False,
            ):
                yield chunk
            return

        prompt = ""
        system_prompt = ""
        for msg in msgs:
            content = msg.get("content", "")
            if msg["role"] == "system":
                system_prompt = content if isinstance(content, str) else str(content)
            else:
                prompt += f"\n{msg['role'].capitalize()}: {content}"

        async for chunk in self.stream_generate_async(
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            preferred_provider=preferred_provider,
            assistant_prefix=prefix,
            allow_fallback=allow_fallback,
            json_mode=json_mode,
        ):
            yield chunk

    def unload_all(self) -> None:
        """Cleanup."""
        pass

    @staticmethod
    def _is_a2a_provider(provider: ModelProvider) -> bool:
        base_url = (provider.base_url or "").rstrip("/")
        return provider.backend == "a2a" or base_url.endswith("/task/submit")


def create_gateway_from_config(config, audit=None) -> ModelGateway:
    """Cria gateway a partir da configuração.

    Loads .env/.env.local (never overriding already-set OS variables) so
    SUPEREZIO_DEEPSEEK_API_KEY resolves regardless of which entrypoint
    constructs the gateway. Idempotent: first call wins.
    """
    load_local_env()
    providers, gw_config = build_default_providers(config)
    return ModelGateway(providers=providers, config=gw_config, audit=audit)


def create_gateway(config=None, audit=None) -> ModelGateway:
    """Backward-compatible gateway factory used by integration tests."""
    if config is None:
        from ..config import get_config

        config = get_config()
    return create_gateway_from_config(config, audit=audit)
