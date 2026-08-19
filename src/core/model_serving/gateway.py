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
from typing import AsyncGenerator, List, Dict, Any, Generator

from ..observability.neural_log import log_event, trace_span, SpanContext, metrics
from ..ports.protocol import A2AMessage, MessageType
from .sanitizer import PrivateChannelFilter, strip_private_model_channels
from ..resilience import get_circuit, CircuitOpenError

# OpenAI SDK for external API operations
from openai import AsyncOpenAI

# Re-export from providers module for backward compatibility
from .providers import (  # noqa: F401 — re-exports
    ModelProvider,
    GatewayConfig,
    PRIMARY_PROVIDER_NAME,
    PRIMARY_MODEL_ID,
    DEEPSEEK_PROVIDER_NAME,
    GEMINI_PROVIDER_NAME,
    AGENT_PROVIDER_NAME,
    build_default_providers,
)

logger = logging.getLogger(__name__)


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
        self._deepseek_provider = None
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

    def set_deepseek_provider(self, deepseek_provider) -> None:
        """Habilita o provedor DeepSeek para tarefas complexas."""
        self._deepseek_provider = deepseek_provider
        log_event("MODEL_GATEWAY", "DEEPSEEK_ENABLED", {"status": "active"})

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

        import time as _time

        now = _time.monotonic()

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
                    if p.name == AGENT_PROVIDER_NAME or not allow_fallback:
                        return [p]
                    return [p] + [
                        other
                        for other in self.providers
                        if other != p
                        and other.name != AGENT_PROVIDER_NAME
                        and not _skip_cooldown(other.name)
                    ]
        # No preferred provider: keep external-provider order and avoid routing
        # generic tasks to local agent runtime.
        non_local = [
            p
            for p in self.providers
            if p.name != AGENT_PROVIDER_NAME and not _skip_cooldown(p.name)
        ]
        return non_local or self.providers

    def _max_attempts(self, providers_to_try: list[ModelProvider]) -> int:
        if not providers_to_try:
            return 0
        return min(len(providers_to_try), max(0, self.config.max_fallbacks) + 1)

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

    @staticmethod
    def _apply_gemini_options(provider: ModelProvider, kwargs: Dict[str, Any]) -> None:
        """Gemini 2.5 Flash on the /v1beta/openai path runs without thinking by
        default — no special parameters needed. The provider's max_tokens
        is already set from GEMINI_MAX_TOKENS env (default 4096), which is
        sufficient for structured JSON expert output."""
        pass

    async def stream_generate_api(
        self,
        provider: ModelProvider,
        prompt: str,
        system_prompt: str = "",
        max_tokens: int | None = None,
        temperature: float | None = None,
        json_mode: bool = False,
        assistant_prefix: str = "",
        tools: List[Dict[str, Any]] | None = None,
    ) -> AsyncGenerator[str, None]:
        """Gera resposta via API OpenAI-compatible (Streaming).

        assistant_prefix: texto inicial forçado na resposta do assistente.
        Injeta como mensagem role=assistant no final da lista — impede que o
        modelo dispare filtros de recusa antes de gerar conteúdo (prefill trick).
        """
        client = AsyncOpenAI(
            base_url=provider.base_url,
            api_key=provider.api_key,
            timeout=provider.timeout_s,
        )

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        if assistant_prefix:
            messages.append({"role": "assistant", "content": assistant_prefix})

        tok = max_tokens if max_tokens is not None else provider.max_tokens
        temp = temperature if temperature is not None else provider.temperature

        kwargs = {
            "model": provider.model,
            "messages": messages,
            "max_tokens": tok,
            "temperature": temp,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = tools

        self._apply_deepseek_options(provider, kwargs)
        self._apply_gemini_options(provider, kwargs)
        if json_mode:
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
        prompt: str,
        system_prompt: str = "",
        max_tokens: int | None = None,
        temperature: float | None = None,
        json_mode: bool = False,
        assistant_prefix: str = "",
    ) -> str:
        """Gera resposta via API OpenAI-compatible (Não-streaming).

        assistant_prefix: injeta mensagem role=assistant antes da geração
        para contornar filtros de recusa do modelo (prefill trick).
        """
        client = AsyncOpenAI(
            base_url=provider.base_url,
            api_key=provider.api_key,
            timeout=provider.timeout_s,
        )

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        if assistant_prefix:
            messages.append({"role": "assistant", "content": assistant_prefix})

        tok = max_tokens if max_tokens is not None else provider.max_tokens
        temp = temperature if temperature is not None else provider.temperature

        kwargs = {
            "model": provider.model,
            "messages": messages,
            "max_tokens": tok,
            "temperature": temp,
        }
        self._apply_deepseek_options(provider, kwargs)
        self._apply_gemini_options(provider, kwargs)
        if json_mode:
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
            if _cb.is_open:
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

            for retry in range(self.config.retry_attempts):
                try:
                    with SpanContext(f"provider.{provider.name}"):
                        # External API sync bridge
                        try:
                            loop = asyncio.get_event_loop()
                            if loop.is_running():
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
                                    )
                                )
                        except RuntimeError:
                            result = asyncio.run(
                                self.generate_api(
                                    provider,
                                    prompt,
                                    system_prompt,
                                    max_tokens,
                                    temperature,
                                    json_mode,
                                    assistant_prefix,
                                )
                            )

                        metrics.increment(f"model.{provider.name}.success")
                        # Reset error counter on success
                        self._provider_errors.pop(provider.name, None)
                        self._provider_cooldown_until.pop(provider.name, None)
                        self.last_provider_used = provider.name
                        _cb._on_success()
                        return result

                except Exception as e:
                    last_error = e
                    err_count = self._provider_errors.get(provider.name, 0) + 1
                    self._provider_errors[provider.name] = err_count
                    if err_count >= self._provider_cooldown_max_errors:
                        import time as _time

                        self._provider_cooldown_until[provider.name] = (
                            _time.monotonic() + self._provider_cooldown_seconds
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
                    else:
                        log_event(
                            "MODEL_GATEWAY",
                            "PROVIDER_ERROR",
                            {"provider": provider.name, "error": str(e)[:200]},
                        )
                    metrics.increment(f"model.{provider.name}.error")

                    if retry < self.config.retry_attempts - 1:
                        import time

                        time.sleep(self.config.retry_delay_s * (2**retry))

            # ── Circuit breaker: record failure after all retries exhausted ──
            if last_error:
                _cb._on_failure(last_error)

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

        for i in range(max_attempts):
            provider = providers_to_try[i]

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
                        except Exception as e:
                            q.put(e)
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
                    yield item
                return
            except Exception as e:
                log_event(
                    "MODEL_GATEWAY",
                    "STREAM_FALLBACK",
                    {"provider": provider.name, "error": str(e)},
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

        for i in range(max_attempts):
            provider = providers_to_try[i]
            attempted.append(provider.name)
            try:
                async for chunk in self.stream_generate_api(
                    provider,
                    prompt,
                    system_prompt=system_prompt,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    assistant_prefix=assistant_prefix,
                    tools=tools,
                ):
                    yield chunk
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
            except Exception as e:
                log_event("GATEWAY", "ASYNC_ERROR", {"error": str(e)})

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

        # Extrai assistant prefix do último message se role=assistant
        prefix = assistant_prefix
        msgs = list(messages)
        if msgs and msgs[-1].get("role") == "assistant":
            prefix = prefix or msgs[-1].get("content", "")
            msgs = msgs[:-1]

        # Convert to prompt
        prompt = ""
        system_prompt = ""
        for msg in msgs:
            if msg["role"] == "system":
                system_prompt = msg["content"]
            else:
                prompt += f"\n{msg['role'].capitalize()}: {msg['content']}"

        # A2A Check. OpenAI-compatible /v1 endpoints also start with http,
        # so only providers explicitly marked as A2A use the remote protocol.
        if provider_obj and self._is_a2a_provider(provider_obj):
            return await self.generate_a2a_remote(prompt, provider_obj)

        # Default Generate API
        import functools

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

    def unload_all(self) -> None:
        """Cleanup."""
        pass

    @staticmethod
    def _is_a2a_provider(provider: ModelProvider) -> bool:
        base_url = (provider.base_url or "").rstrip("/")
        return provider.backend == "a2a" or base_url.endswith("/task/submit")

    async def warmup(self) -> None:
        """No warmup needed for external models."""
        pass

    async def generate_a2a_remote(self, prompt: str, provider: ModelProvider) -> str:
        """Chamada para outro agente SuperEzio via protocolo A2A."""
        import httpx
        import json

        envelope = A2AMessage(
            from_agent="orchestrator",
            to_agent=provider.name,
            type=MessageType.TASK_SUBMIT,
            payload={"message": prompt},
        )

        try:
            async with httpx.AsyncClient(timeout=self.config.timeout_s) as client:
                base_url = provider.base_url.rstrip("/")
                target_url = (
                    base_url if base_url.endswith("/task/submit") else f"{base_url}/task/submit"
                )
                full_response = []
                async with client.stream(
                    "POST", target_url, json=envelope.model_dump(by_alias=True)
                ) as response:
                    if response.status_code != 200:
                        raise Exception(f"Remote agent error {response.status_code}")

                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            if data.get("type") == "CHUNK":
                                full_response.append(data.get("content", ""))
                            elif data.get("type") == "ERROR":
                                raise Exception(f"Remote failure: {data.get('detail')}")
                        except json.JSONDecodeError:
                            continue

                return "".join(full_response)
        except Exception as e:
            log_event("MODEL_GATEWAY", "REMOTE_ERROR", {"error": str(e)})
            raise


def create_gateway_from_config(config, audit=None) -> ModelGateway:
    """Cria gateway a partir da configuração."""
    providers, gw_config = build_default_providers(config)
    return ModelGateway(providers=providers, config=gw_config, audit=audit)


def create_gateway(config=None, audit=None) -> ModelGateway:
    """Backward-compatible gateway factory used by integration tests."""
    if config is None:
        from ..config import get_config

        config = get_config()
    return create_gateway_from_config(config, audit=audit)
