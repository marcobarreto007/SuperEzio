"""Contrato para gateway de modelos.

A camada de aplicação (pipeline, agentes) depende deste port,
nunca da implementação concreta (OpenAI-compatible, local, etc.).
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any, Protocol


class ModelGatewayPort(Protocol):
    """Gateway de modelos com fallback em cascata."""

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        preferred_provider: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Gera resposta não-streaming."""
        ...

    async def stream_generate(
        self,
        prompt: str,
        system_prompt: str = "",
        preferred_provider: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        assistant_prefix: str = "",
    ) -> AsyncGenerator[str, None]:
        """Gera resposta streaming via provider preferido com fallback."""
        ...

    async def stream_generate_api(
        self,
        provider: Any,
        prompt: str,
        system_prompt: str = "",
        max_tokens: int | None = None,
        temperature: float | None = None,
        json_mode: bool = False,
        assistant_prefix: str = "",
    ) -> AsyncGenerator[str, None]:
        """Gera streaming direto em um provider específico (raw)."""
        ...

    async def generate_api(
        self,
        provider: Any,
        prompt: str,
        system_prompt: str = "",
        max_tokens: int | None = None,
        temperature: float | None = None,
        json_mode: bool = False,
        assistant_prefix: str = "",
        messages: list[dict[str, Any]] | None = None,
    ) -> str:
        """Gera resposta não-streaming direto em um provider específico (raw)."""
        ...

    def list_providers(self) -> list[Any]:
        """Lista providers ativos."""
        ...
