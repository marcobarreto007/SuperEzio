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
import os
import time
from collections.abc import AsyncGenerator, Generator
from dataclasses import replace
from enum import Enum
from typing import Any

# OpenAI SDK for external API operations
from openai import AsyncOpenAI

from ..config.secrets import load_local_env
from ..observability.neural_log import SpanContext, log_event, metrics, trace_span
from ..resilience import CircuitOpenError, CircuitState, get_circuit

# Re-export from providers module for backward compatibility
from .providers import (  # noqa: F401 — re-exports
    AGENT_PROVIDER_NAME,
    DAYTRADE_AUDITOR_PROVIDER_NAME,
    DAYTRADE_JUDGE_PROVIDER_NAME,
    DEEPSEEK_PROVIDER_NAME,
    GLM_PROVIDER_NAME,
    PRIMARY_MODEL_ID,
    PRIMARY_PROVIDER_NAME,
    GatewayConfig,
    ModelProvider,
    build_default_providers,
)
from .sanitizer import PrivateChannelFilter, strip_private_model_channels

logger = logging.getLogger(__name__)

# Local llama window: 98304 tokens (raised 2026-09-11 — the 2-GPU build serves
# -c 98304; the previous 8192 dated from the Qwen3.8 era and blocked the local
# mouth from reading any medium source file). Guard thresholds: reject above
# HARD (the request would die with a raw 400), warn near the limit (generation
# also needs headroom). Estimates are conservative: ~3.5 chars/token for PT/EN
# text and 768 tokens per image (llama.cpp mmproj patch heuristic) —
# over-estimating is the safe direction for a fail-fast guard.
# Janela conhecida do servidor local (start-f51.ps1: -c 98304). O config pode
# declarar outra (ModelProvider.n_ctx) e ela vence; isto aqui e o fallback.
LOCAL_CONTEXT_DEFAULT_WINDOW = 98_304
# Entrada e resposta dividem o mesmo slot (-np 1), entao o teto desconta a folga.
LOCAL_CONTEXT_OUTPUT_RESERVE = 2_048
LOCAL_CONTEXT_HARD_TOKEN_CAP = LOCAL_CONTEXT_DEFAULT_WINDOW - LOCAL_CONTEXT_OUTPUT_RESERVE
# Warn at the same fraction of the window the old 6500/8000 pair used (~81%).
LOCAL_CONTEXT_WARN_TOKEN_CAP = 78_000
_LOCAL_CONTEXT_IMAGE_TOKENS = 768


def _context_cap(window: int | None = None) -> int:
    """Teto efetivo de entrada.

    A janela declarada (ModelProvider.n_ctx) vence a constante; entrada e
    resposta dividem o mesmo slot (-np 1), entao a folga de saida e descontada.
    """
    if window and window > 0:
        return max(window - LOCAL_CONTEXT_OUTPUT_RESERVE, 1)
    return LOCAL_CONTEXT_HARD_TOKEN_CAP


def local_context_fits(
    messages: list[dict[str, str]], window: int | None = None
) -> tuple[bool, int, str]:
    """Estimate input tokens and decide whether they fit the local window.

    `window` e a janela real do endpoint local quando conhecida; sem ela vale
    LOCAL_CONTEXT_HARD_TOKEN_CAP.

    Returns (fits, estimated_tokens, reason). Pure and deterministic — no I/O.
    """
    cap = _context_cap(window)
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
    if estimated > cap:
        return False, estimated, "over_hard_cap"
    return True, estimated, "fits"


def _has_image_content(messages: list[dict[str, Any]] | None) -> bool:
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


def _is_text_only_mouth(provider: Any) -> bool:
    """Local CEO/orchestrator has no mmproj. Images 500 the llama-server."""
    name = getattr(provider, "name", "")
    return bool(getattr(provider, "is_local", False)) or name in {
        "agent",
        "local_orchestrator",
    }


def _strip_image_content(
    messages: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Drop image_url parts. Keep caption text. Local mouth is text-only."""
    out: list[dict[str, Any]] = []
    for msg in messages or []:
        if not isinstance(msg, dict):
            continue
        content = msg.get("content")
        if not isinstance(content, list):
            out.append(dict(msg))
            continue
        texts: list[str] = []
        kept: list[dict[str, Any]] = []
        dropped_image = False
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "image_url":
                dropped_image = True
                continue
            if part.get("type") == "text":
                texts.append(str(part.get("text") or ""))
            else:
                kept.append(part)
        new_msg = {k: v for k, v in msg.items() if k != "content"}
        if kept:
            new_msg["content"] = [{"type": "text", "text": t} for t in texts if t] + kept
        elif texts:
            new_msg["content"] = "\n".join(t for t in texts if t)
        elif dropped_image:
            new_msg["content"] = (
                "GRAFICO OMITIDO: a boca local e texto-only. "
                "Use os numeros do pipeline (preco, RSI, MACD, F51, SDCA)."
            )
        else:
            new_msg["content"] = ""
        out.append(new_msg)
    return out


def _is_local_provider(provider: Any) -> bool:
    """True quando o provedor e a boca LOCAL (llama-server, janela 98304).

    O cerebro em nuvem (deepseek-v4 na api.deepseek.com) tem janela grande —
    o guard legado de contexto nao deve disparar nele (incidente 2026-09-10:
    a boca "agent" e nuvem e levava "local_context_exceeded").
    """
    base_url = (getattr(provider, "base_url", "") or "").lower()
    return (
        bool(getattr(provider, "is_local", False))
        or "127.0.0.1" in base_url
        or "localhost" in base_url
    )


def _openai_messages(raw: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Drop internal keys (e.g. _chart_facts) before the provider call."""
    out: list[dict[str, Any]] = []
    for msg in raw or []:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        if role not in {"system", "user", "assistant"}:
            continue
        out.append({"role": role, "content": msg.get("content")})
    return out


_JSON_MODE_HINT = "Responda somente com JSON valido."


def _ensure_json_word(api_messages: list[dict[str, Any]]) -> None:
    """Garante a palavra "json" no request quando o modo JSON esta ativo.

    A API OpenAI-compatible (DeepSeek oficial) devolve 400 quando
    ``response_format={"type": "json_object"}`` e enviado sem a palavra
    "json" em nenhuma mensagem ("Prompt must contain the word 'json' ...
    to use 'response_format' of type 'json_object'"). Injeta a instrucao de
    forma idempotente: no system prompt, senao na ultima mensagem; se nao
    houver texto mutavel, prepende um system novo.
    """
    for msg in api_messages:
        content = msg.get("content")
        if isinstance(content, str) and "json" in content.lower():
            return
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and "json" in str(part.get("text") or "").lower():
                    return
    for msg in api_messages:
        if msg.get("role") == "system" and isinstance(msg.get("content"), str):
            msg["content"] = f"{msg['content']}\n{_JSON_MODE_HINT}"
            return
    for msg in reversed(api_messages):
        if msg.get("role") == "user" and isinstance(msg.get("content"), str):
            msg["content"] = f"{msg['content']}\n{_JSON_MODE_HINT}"
            return
    api_messages.insert(0, {"role": "system", "content": _JSON_MODE_HINT})


class _FailureKind(Enum):
    """Internal retry classification for provider failures."""

    TRANSIENT = "transient"
    PERMANENT = "permanent"


def _is_glm_provider(provider: Any) -> bool:
    """Check if the provider is a Z.ai GLM model."""
    if provider is None:
        return False
    model = (getattr(provider, "model", "") or "").strip().lower()
    base_url = (getattr(provider, "base_url", "") or "").strip().lower()
    return model.startswith("glm") or "api.z.ai" in base_url or "bigmodel" in base_url


def is_insufficient_credit_error(exc: Exception | None) -> bool:
    """Check if an exception indicates the model provider is out of credit / quota / balance."""
    if exc is None:
        return False

    # 1. Direct status code check
    response = getattr(exc, "response", None)
    status = getattr(exc, "status_code", None) or getattr(response, "status_code", None)
    if status == 402:
        return True

    # 2. Extract error code from OpenAI exception or dict payload
    code = getattr(exc, "code", None)
    if code is not None:
        code_str = str(code).strip().lower()
        if code_str in {
            "1301",
            "1302",
            "insufficient_quota",
            "quota_exceeded",
            "out_of_credit",
            "account_deactivated",
            "billing_not_active",
        }:
            return True

    # 3. Check error string and response body
    error_text = str(exc).lower()
    if response is not None:
        try:
            resp_text = getattr(response, "text", "") or ""
            error_text += " " + str(resp_text).lower()
        except (AttributeError, TypeError, ValueError, RuntimeError):
            pass

    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        error_text += " " + str(body).lower()
        err_obj = body.get("error")
        if isinstance(err_obj, dict):
            b_code = str(err_obj.get("code") or "").lower()
            if b_code in {
                "1301",
                "1302",
                "insufficient_quota",
                "quota_exceeded",
                "out_of_credit",
            }:
                return True
    elif isinstance(body, str):
        error_text += " " + body.lower()

    credit_keywords = (
        "insufficient_quota",
        "insufficient quota",
        "out of credit",
        "out_of_credit",
        "sem credito",
        "sem crédito",
        "balance is insufficient",
        "insufficient balance",
        "account arrears",
        "account is in arrears",
        "arrears",
        "payment required",
        "run out of balance",
        "quota exceeded",
        "exceeded your current quota",
        "credit exhausted",
        "billing",
        "1301",
        "1302",
    )
    return any(kw in error_text for kw in credit_keywords)


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
        providers: list[ModelProvider] | None = None,
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

    @staticmethod
    def _role_degrade_provider(
        role_provider: ModelProvider, deepseek_provider: ModelProvider
    ) -> ModelProvider:
        """Return the DeepSeek hop a GLM role degrades to, on THAT role's model.

        The GLM credit fallback must not silently demote a deciding role (CEO,
        orchestrator) to the support model: every provider carries where its own
        role degrades (``ModelProvider.degrade_model``, set by the builder that
        knows the role). Only the model id changes — provider name, endpoint and
        circuit/cooldown identity stay on the DeepSeek boundary — and the shared
        provider object is never mutated. When the role degrades to the model
        the plain DeepSeek provider already runs, that object is reused as-is.
        """
        target = (getattr(role_provider, "degrade_model", "") or "").strip()
        if not target or target == deepseek_provider.model:
            return deepseek_provider
        return replace(deepseek_provider, model=target)

    def _providers_for_request(
        self, preferred_provider: str | None = None, allow_fallback: bool = True
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

        fallback_glm_to_deepseek = os.getenv(
            "SUPEREZIO_GLM_FALLBACK_TO_DEEPSEEK", "1"
        ).strip().lower() in {"1", "true", "yes", "on"}

        if preferred_provider:
            for p in self.providers:
                if p.name == preferred_provider:
                    # GLM credit fallback: if the requested provider is running GLM and
                    # fallback is allowed, provide DeepSeek as fallback.
                    if allow_fallback and fallback_glm_to_deepseek and _is_glm_provider(p):
                        deepseek_p = next(
                            (
                                other
                                for other in self.providers
                                if other.name == DEEPSEEK_PROVIDER_NAME
                            ),
                            None,
                        )
                        if deepseek_p and deepseek_p != p:
                            fallback_p = self._role_degrade_provider(p, deepseek_p)
                            if _skip_cooldown(p.name):
                                return [fallback_p]
                            return [p, fallback_p]

                    if (
                        p.name
                        in {
                            AGENT_PROVIDER_NAME,
                            GLM_PROVIDER_NAME,
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
    def _is_rate_limit_error(exc: Exception) -> bool:
        """429 / rate-limit has its own policy (retry + backoff + cooldown) and
        must never open the circuit breaker — a parallel burst of 429s (expert
        fan-out) would otherwise trip the 60s circuit and degrade the whole
        committee for a quota condition that recovers on its own."""
        response = getattr(exc, "response", None)
        status = getattr(exc, "status_code", None) or getattr(response, "status_code", None)
        if status == 429:
            return True
        text = str(exc or "").lower()
        return "429" in text or "rate limit" in text or "too many requests" in text

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
    def _apply_deepseek_options(provider: ModelProvider, kwargs: dict[str, Any]) -> None:
        """Apply DeepSeek V4 thinking controls for OpenAI-compatible calls."""
        import os

        if provider.name not in {
            DEEPSEEK_PROVIDER_NAME,
            PRIMARY_PROVIDER_NAME,
            AGENT_PROVIDER_NAME,
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
    def _apply_glm_coding_plan_options(provider: ModelProvider, kwargs: dict[str, Any]) -> None:
        """GLM-5.3 Coding Plan always reasons; disabling thinking 400s the request."""
        import os

        model = (provider.model or "").strip().lower()
        if not model.startswith("glm-5"):
            return
        effort = os.getenv("SUPEREZIO_GLM_REASONING_EFFORT", "low").strip().lower()
        if effort not in {"low", "high", "max"}:
            effort = "low"
        extra = dict(kwargs.get("extra_body") or {})
        extra["thinking"] = {"type": "enabled"}
        extra["reasoning_effort"] = effort
        kwargs["extra_body"] = extra

    async def stream_generate_api(
        self,
        provider: ModelProvider,
        prompt: str = "",
        system_prompt: str = "",
        max_tokens: int | None = None,
        temperature: float | None = None,
        json_mode: bool = False,
        assistant_prefix: str = "",
        tools: list[dict[str, Any]] | None = None,
        messages: list[dict[str, Any]] | None = None,
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
        if _is_text_only_mouth(provider):
            api_messages = _strip_image_content(api_messages)
        if assistant_prefix:
            api_messages.append({"role": "assistant", "content": assistant_prefix})

        tok = max_tokens if max_tokens is not None else provider.max_tokens
        if _is_glm_provider(provider):
            # Thinking is forced on for GLM (disabling it 400s); the
            # deliberation shares the output budget, so 1800 leaves no room
            # for the visible content (2026-09-05: reasoning-only replies).
            tok = max(tok, 4096)
        temp = temperature if temperature is not None else provider.temperature
        if json_mode and _has_image_content(api_messages):
            logger.warning(
                "json_mode disabled: image content present (vision cannot emit structured JSON)"
            )
        use_json = bool(json_mode) and not _has_image_content(api_messages)
        if use_json:
            _ensure_json_word(api_messages)

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
        self._apply_glm_coding_plan_options(provider, kwargs)
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
                content = delta.content or ""
                reasoning = getattr(delta, "reasoning_content", None) or ""
                # GLM-5.3/DeepSeek emit raw deliberation in reasoning_content
                # with no channel markers. Streaming it as visible text leaks
                # the CoT into the user answer and burns max_tokens before the
                # real content starts (regression 2026-09-05: chat answered in
                # English, reasoning-only). Only Qwen-style reasoning carrying
                # explicit channel/think markers is routed to the filter.
                text = content
                if not text and ("<|channel|" in reasoning or "<think" in reasoning.lower()):
                    text = reasoning
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
        messages: list[dict[str, Any]] | None = None,
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
        if _is_text_only_mouth(provider):
            api_messages = _strip_image_content(api_messages)
        if assistant_prefix:
            api_messages.append({"role": "assistant", "content": assistant_prefix})

        tok = max_tokens if max_tokens is not None else provider.max_tokens
        if _is_glm_provider(provider):
            # Thinking is forced on for GLM (disabling it 400s); the
            # deliberation shares the output budget, so 1800 leaves no room
            # for the visible content (2026-09-05: reasoning-only replies).
            tok = max(tok, 4096)
        temp = temperature if temperature is not None else provider.temperature
        if json_mode and _has_image_content(api_messages):
            logger.warning(
                "json_mode disabled: image content present (vision cannot emit structured JSON)"
            )
        use_json = bool(json_mode) and not _has_image_content(api_messages)
        if use_json:
            _ensure_json_word(api_messages)

        kwargs = {
            "model": provider.model,
            "messages": api_messages,
            "max_tokens": tok,
            "temperature": temp,
        }
        self._apply_deepseek_options(provider, kwargs)
        self._apply_glm_coding_plan_options(provider, kwargs)
        if use_json:
            kwargs["response_format"] = {"type": "json_object"}

        try:
            response = await client.chat.completions.create(**kwargs)
            msg = response.choices[0].message
            content = msg.content or ""
            reasoning = getattr(msg, "reasoning_content", None) or ""
            # Same contract as the streaming path: raw reasoning (GLM/DeepSeek,
            # no channel markers) must never surface as the visible answer.
            text = content
            if not text and ("<|channel|" in reasoning or "<think" in reasoning.lower()):
                text = reasoning
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
        if self._is_rate_limit_error(exc):
            log_event(
                "MODEL_GATEWAY",
                "RATE_LIMIT_EXHAUSTED",
                {
                    "provider": provider_name,
                    "next": next_name or "",
                    "note": "429 keeps its own retry/cooldown policy; circuit not opened",
                },
            )
        else:
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
        preferred_provider: str | None = None,
        json_mode: bool = False,
        assistant_prefix: str = "",
        allow_fallback: bool = True,
        messages: list[dict[str, Any]] | None = None,
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
                                    lambda provider=provider: asyncio.run(
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

                    if is_insufficient_credit_error(e):
                        _cb.record_failure(e)
                        self._record_circuit_state(provider.name, _cb)
                        metrics.increment(f"model.{provider.name}.insufficient_credit")
                        self._provider_cooldown_until[provider.name] = (
                            time.monotonic() + self._provider_cooldown_seconds
                        )
                        if i + 1 < max_attempts:
                            next_provider = providers_to_try[i + 1]
                            logger.warning(
                                "INSUFFICIENT_CREDIT: Provider %s is out of credit (%s). Falling back to %s.",
                                provider.name,
                                e,
                                next_provider.name,
                            )
                            break
                        raise RuntimeError(
                            f"Provider {provider.name} is out of credit and no fallback provider available: {e}"
                        ) from e

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
        preferred_provider: str | None = None,
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

                    def run_async_stream(q=q, provider=provider):
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
                            except Exception as exc:  # noqa: BLE001 — falha do stream é empacotada na queue para re-lançar no thread principal
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
                except Exception as exc:  # noqa: BLE001 — falha de provider é classificada para retry/fallback; catch amplo deliberado
                    failure_kind = self._classify_provider_failure(exc)
                    self._record_provider_error(provider, exc, failure_kind)
                    if is_insufficient_credit_error(exc):
                        circuit.record_failure(exc)
                        self._record_circuit_state(provider.name, circuit)
                        metrics.increment(f"model.{provider.name}.insufficient_credit")
                        self._provider_cooldown_until[provider.name] = (
                            time.monotonic() + self._provider_cooldown_seconds
                        )
                        if not emitted and i + 1 < max_attempts:
                            next_provider = providers_to_try[i + 1]
                            logger.warning(
                                "INSUFFICIENT_CREDIT (stream): Provider %s is out of credit (%s). Falling back to %s.",
                                provider.name,
                                exc,
                                next_provider.name,
                            )
                            break
                        logger.error(
                            "PROVIDER_OUT_OF_CREDIT (stream): %s - %s",
                            provider.name,
                            str(exc)[:400],
                        )
                        yield f"[ERROR] Provider {provider.name} out of credit: {type(exc).__name__}."
                        return
                    if emitted or failure_kind is _FailureKind.PERMANENT:
                        circuit.record_failure(exc)
                        self._record_circuit_state(provider.name, circuit)
                        metrics.increment(f"model.{provider.name}.retry_suppressed")
                        logger.error(
                            "PROVIDER_FAILED (stream): %s (%s) - %s",
                            provider.name,
                            type(exc).__name__,
                            str(exc)[:400],
                        )
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
        preferred_provider: str | None = None,
        assistant_prefix: str = "",
        allow_fallback: bool = True,
        tools: list[dict[str, Any]] | None = None,
        messages: list[dict[str, Any]] | None = None,
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
                except Exception as exc:  # noqa: BLE001 — falha de provider é classificada para retry/fallback; catch amplo deliberado
                    failure_kind = self._classify_provider_failure(exc)
                    self._record_provider_error(provider, exc, failure_kind)
                    if is_insufficient_credit_error(exc):
                        circuit.record_failure(exc)
                        self._record_circuit_state(provider.name, circuit)
                        metrics.increment(f"model.{provider.name}.insufficient_credit")
                        self._provider_cooldown_until[provider.name] = (
                            time.monotonic() + self._provider_cooldown_seconds
                        )
                        if not emitted and i + 1 < max_attempts:
                            next_provider = providers_to_try[i + 1]
                            logger.warning(
                                "INSUFFICIENT_CREDIT (async stream): Provider %s is out of credit (%s). Falling back to %s.",
                                provider.name,
                                exc,
                                next_provider.name,
                            )
                            break
                        logger.error(
                            "PROVIDER_OUT_OF_CREDIT (async stream): %s - %s",
                            provider.name,
                            str(exc)[:400],
                        )
                        yield f"[ERROR] Provider {provider.name} out of credit: {type(exc).__name__}."
                        return
                    if emitted or failure_kind is _FailureKind.PERMANENT:
                        circuit.record_failure(exc)
                        self._record_circuit_state(provider.name, circuit)
                        metrics.increment(f"model.{provider.name}.retry_suppressed")
                        logger.error(
                            "PROVIDER_FAILED (async stream): %s (%s) - %s",
                            provider.name,
                            type(exc).__name__,
                            str(exc)[:400],
                        )
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
        messages: list[dict[str, str]],
        json_mode: bool = False,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        preferred_provider: str | None = None,
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

        if _is_text_only_mouth(provider_obj):
            messages = _strip_image_content(messages)

        # ── Local-context pre-flight guard ──
        # Requests far beyond the local window were rejected by llama-server
        # with a raw 400 (demo failure 24/08: two requests of 34k-37k tokens),
        # surfacing as "runtime error". Fail here first, with an actionable
        # message, instead of sending garbage. Cloud mouths (deepseek-v4) have
        # a large window — only the LOCAL llama-server is guarded (incident
        # 2026-09-10). Thresholds live in LOCAL_CONTEXT_HARD_TOKEN_CAP /
        # LOCAL_CONTEXT_WARN_TOKEN_CAP so the window is stated in one place.
        if provider_obj.name in ("agent", "local_orchestrator") and _is_local_provider(
            provider_obj
        ):
            ok, estimated, _reason = local_context_fits(
                messages, getattr(provider_obj, "n_ctx", 0) or None
            )
            if not ok:
                raise RuntimeError(
                    "local_context_exceeded: prompt estimates at ~"
                    f"{estimated} tokens, the local window is "
                    f"{LOCAL_CONTEXT_HARD_TOKEN_CAP}. "
                    "Shorten the conversation (or attach fewer images) and retry."
                )
            if estimated > LOCAL_CONTEXT_WARN_TOKEN_CAP:
                logger.warning(
                    "local_context_near_limit: %s tokens of %s",
                    estimated,
                    LOCAL_CONTEXT_HARD_TOKEN_CAP,
                )

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
        messages: list[dict[str, Any]],
        json_mode: bool = False,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        preferred_provider: str | None = None,
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

        stream_provider = self._providers_for_request(
            preferred_provider, allow_fallback=allow_fallback
        )[0]
        if _is_text_only_mouth(stream_provider):
            msgs = _strip_image_content(msgs)

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
