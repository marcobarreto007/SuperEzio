"""
DeepSeek Provider â€” CÃ©rebro externo do Family Investor Mode
===========================================================
API compatÃ­vel com OpenAI Chat Completions.
Base URL: https://api.deepseek.com

SEGURANÃ‡A:
- API key NUNCA hardcoded.
- API key NUNCA logada.
- API key NUNCA retornada em /health ou qualquer endpoint.
- Chave lida APENAS de variÃ¡vel de ambiente: SUPEREZIO_DEEPSEEK_API_KEY
- Header Authorization NUNCA aparece em logs.

Se a chave nÃ£o estiver configurada, o provider fica em modo degraded.
O servidor sobe normalmente e retorna erro claro nas chamadas.
"""

from __future__ import annotations

import os
from typing import Any, AsyncGenerator, Dict, List, Optional

from core.security.constants import FORBIDDEN_OUTPUT_PHRASES as FORBIDDEN_PHRASES

from ..observability.neural_log import log_event

# Provider states
_STATE_READY = "ready"
_STATE_DEGRADED = "degraded"
_STATE_DISABLED = "disabled"


def _sanitize_response(text: str) -> str:
    """
    Remove ou sinaliza frases proibidas do output do modelo.
    Adiciona aviso de risco se detectar frases de garantia.
    """
    sanitized = text
    lower = sanitized.lower()
    found = [p for p in FORBIDDEN_PHRASES if p in lower]
    if found:
        import re

        for phrase in found:
            sanitized = re.sub(
                re.escape(phrase),
                "[REMOVED]",
                sanitized,
                flags=re.IGNORECASE,
            )
        warning = (
            "\n\n[SYSTEM] Guarantee phrases were detected and removed. "
            "No analysis guarantees profit."
        )
        return sanitized + warning
    return sanitized


class DeepSeekProvider:
    """
    Provider para DeepSeek API (OpenAI-compatible).

    Modelos suportados:
    - deepseek-chat  -> anÃ¡lise normal, rÃ¡pida
    - deepseek-reasoner    -> revisÃ£o profunda, incerteza alta, anÃ¡lise de risco

    Se reasoning_content vier na resposta do reasoner, NUNCA Ã© exposto ao usuÃ¡rio.
    Apenas o campo 'content' final Ã© retornado.

    Status:
    - ready    â†’ chave configurada e vÃ¡lida
    - degraded â†’ chave ausente (servidor sobe, chamadas retornam erro claro)
    - disabled â†’ SDK nÃ£o disponÃ­vel
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.deepseek.com",
        model: str = "deepseek-chat",
        reasoner_model: str = "deepseek-reasoner",
        timeout_sec: int = 120,
        max_tokens: int = 1800,
        temperature: float = 0.2,
        reasoning_effort: str = "high",
    ) -> None:
        # LÃª da env se nÃ£o fornecida â€” NUNCA hardcoded
        self._api_key: Optional[str] = api_key or os.getenv(
            "SUPEREZIO_DEEPSEEK_API_KEY"
        )
        self.base_url = base_url or os.getenv(
            "SUPEREZIO_DEEPSEEK_BASE_URL", "https://api.deepseek.com"
        )
        self.model = model or os.getenv("SUPEREZIO_DEEPSEEK_MODEL", "deepseek-chat")
        self.reasoner_model = reasoner_model or os.getenv(
            "SUPEREZIO_DEEPSEEK_REASONER_MODEL", "deepseek-reasoner"
        )
        self.timeout_sec = timeout_sec
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.reasoning_effort = reasoning_effort

        self._client = None
        self._status: str = _STATE_DISABLED
        self._status_detail: str = ""

        self._init_client()

    # ------------------------------------------------------------------
    # Internal init
    # ------------------------------------------------------------------

    def _init_client(self) -> None:
        """Inicializa o cliente OpenAI apontando para DeepSeek."""
        try:
            from openai import AsyncOpenAI  # type: ignore
        except ImportError:
            self._status = _STATE_DISABLED
            self._status_detail = "openai SDK not installed"
            log_event("DEEPSEEK", "DISABLED", {"reason": "openai SDK not installed"})
            return

        if not self._api_key:
            self._status = _STATE_DEGRADED
            self._status_detail = "SUPEREZIO_DEEPSEEK_API_KEY not set"
            # Log sem a chave â€” intencionalmente
            log_event(
                "DEEPSEEK",
                "DEGRADED",
                {
                    "reason": "API key not configured",
                    "env_var": "SUPEREZIO_DEEPSEEK_API_KEY",
                },
            )
            return

        # Cria cliente â€” header Authorization configurado internamente pelo SDK
        # NUNCA logamos o conteÃºdo da chave
        self._client = AsyncOpenAI(
            api_key=self._api_key,
            base_url=self.base_url,
            timeout=self.timeout_sec,
        )
        self._status = _STATE_READY
        log_event(
            "DEEPSEEK",
            "READY",
            {
                "model": self.model,
                "reasoner": self.reasoner_model,
                "base_url": self.base_url,
                # api_key NUNCA logada
            },
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def is_ready(self) -> bool:
        return self._status == _STATE_READY

    def health_dict(self) -> Dict[str, Any]:
        """
        Retorna status para /health.
        NUNCA expÃµe a chave â€” apenas se estÃ¡ configurada (bool).
        """
        return {
            "configured": bool(self._api_key),
            "ready": self.is_ready,
            "status": self._status,
            "base_url": self.base_url,
            "model": self.model,
            "reasoner_model": self.reasoner_model,
            "api_key_configured": bool(self._api_key),
            # api_key_value NUNCA incluÃ­da
        }

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        use_reasoner: bool = False,
        json_mode: bool = False,
        model: str | None = None,
    ) -> str:
        """
        Chamada ao DeepSeek Chat Completions.

        Args:
            messages: Lista de mensagens no formato OpenAI.
            temperature: Override de temperatura.
            max_tokens: Override de max_tokens.
            use_reasoner: Se True, habilita thinking mode/anÃ¡lise profunda.
            json_mode: Se True, solicita resposta em JSON.
            model: Override de modelo dinÃ¢mico.

        Returns:
            String com o conteÃºdo final da resposta.
            Se use_reasoner=True, reasoning_content NUNCA Ã© retornado.

        Raises:
            RuntimeError: Se o provider estiver degraded/disabled.
        """
        self._assert_ready()

        active_model = model or (self.reasoner_model if use_reasoner else self.model)
        temp = temperature if temperature is not None else self.temperature
        tok = max_tokens or self.max_tokens

        kwargs: Dict[str, Any] = {
            "model": active_model,
            "messages": messages,
            "max_tokens": tok,
        }
        if use_reasoner:
            kwargs["reasoning_effort"] = self.reasoning_effort
            kwargs["extra_body"] = {"thinking": {"type": "enabled"}}
        else:
            kwargs["temperature"] = temp
            if active_model.startswith("deepseek-v4-"):
                kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        try:
            log_event(
                "DEEPSEEK",
                "CALL",
                {
                    "model": active_model,
                    "messages_count": len(messages),
                    "use_reasoner": use_reasoner,
                },
            )
            response = await self._client.chat.completions.create(**kwargs)

            choice = response.choices[0]
            msg = choice.message

            # reasoning_content pode existir em thinking mode; NUNCA expor ao usuÃ¡rio.
            content: str = msg.content or ""

            usage = response.usage
            log_event(
                "DEEPSEEK",
                "DONE",
                {
                    "model": model,
                    "prompt_tokens": usage.prompt_tokens if usage else -1,
                    "completion_tokens": usage.completion_tokens if usage else -1,
                    "has_reasoning": hasattr(msg, "reasoning_content")
                    and bool(getattr(msg, "reasoning_content", None)),
                },
            )

            return _sanitize_response(content)

        except Exception as exc:
            return self._handle_error(exc)

    async def stream_chat(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
    ) -> AsyncGenerator[str, None]:
        """Streaming de resposta do DeepSeek."""
        self._assert_ready()

        temp = temperature if temperature is not None else self.temperature

        try:
            stream = await self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temp,
                max_tokens=self.max_tokens,
                stream=True,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    yield delta.content
        except Exception as exc:
            yield self._handle_error(exc)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _assert_ready(self) -> None:
        if self._status == _STATE_DEGRADED:
            raise RuntimeError(
                "deepseek_provider_degraded: SUPEREZIO_DEEPSEEK_API_KEY not configured. "
                "Set the environment variable and restart the server."
            )
        if self._status == _STATE_DISABLED:
            raise RuntimeError(
                "deepseek_provider_disabled: openai SDK not installed. "
                "Run: pip install openai"
            )

    def _handle_error(self, exc: Exception) -> str:
        """Converte exceÃ§Ãµes da API em erros legÃ­veis sem vazar a chave."""
        exc_str = str(exc)
        # Garante que a chave nunca aparece no erro
        if self._api_key and self._api_key in exc_str:
            exc_str = exc_str.replace(self._api_key, "[REDACTED]")

        err_lower = exc_str.lower()

        if "401" in exc_str or "403" in exc_str or "authentication" in err_lower:
            msg = "deepseek_credential_error: API key is invalid or unauthorized."
            log_event("DEEPSEEK", "CREDENTIAL_ERROR", {"detail": "401/403 from API"})
            raise RuntimeError(msg) from exc

        if "timeout" in err_lower or "timed out" in err_lower:
            msg = f"deepseek_timeout: Request exceeded {self.timeout_sec}s timeout."
            log_event("DEEPSEEK", "TIMEOUT", {"timeout_sec": self.timeout_sec})
            raise RuntimeError(msg) from exc

        log_event("DEEPSEEK", "API_ERROR", {"error_type": type(exc).__name__})
        raise RuntimeError(f"deepseek_api_error: {exc_str}") from exc


def create_deepseek_provider() -> DeepSeekProvider:
    """
    Factory que cria o provider lendo configuraÃ§Ãµes das variÃ¡veis de ambiente.
    Servidor sobe mesmo sem chave configurada (status = degraded).
    """
    return DeepSeekProvider(
        api_key=None,  # Lido de SUPEREZIO_DEEPSEEK_API_KEY pela classe
        base_url=os.getenv("SUPEREZIO_DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        model=os.getenv("SUPEREZIO_DEEPSEEK_MODEL", "deepseek-chat"),
        reasoner_model=os.getenv(
            "SUPEREZIO_DEEPSEEK_REASONER_MODEL", "deepseek-reasoner"
        ),
        timeout_sec=int(os.getenv("SUPEREZIO_DEEPSEEK_TIMEOUT_SEC", "120")),
        max_tokens=int(os.getenv("SUPEREZIO_DEEPSEEK_MAX_TOKENS", "1800")),
        temperature=float(os.getenv("SUPEREZIO_DEEPSEEK_TEMPERATURE", "0.2")),
        reasoning_effort=os.getenv("SUPEREZIO_DEEPSEEK_REASONING_EFFORT", "high"),
    )
