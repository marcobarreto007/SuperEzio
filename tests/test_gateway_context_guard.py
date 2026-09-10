"""Guarda pre-flight de contexto do gateway local (janela 8192 tokens).

A demo de 24/08 falhou com dois prompts de 34k-37k tokens rejeitados pelo
llama-server com 400 cru. O guard rejeita ANTES de mandar, com mensagem
acionavel. Estimativa conservadora: ~3 chars/token de texto e 768 tokens
por imagem.
"""

from __future__ import annotations

import pytest

import core.model_serving.gateway as gateway_module
from core.model_serving.gateway import (
    LOCAL_CONTEXT_HARD_TOKEN_CAP,
    ModelGateway,
    local_context_fits,
)
from core.model_serving.providers import GatewayConfig, ModelProvider


def _provider(name: str, base_url: str, *, is_local: bool = False) -> ModelProvider:
    return ModelProvider(name=name, base_url=base_url, api_key="", is_local=is_local)


def test_small_prompt_fits() -> None:
    fits, estimated, reason = local_context_fits(
        [{"role": "system", "content": "voce e o bob"}, {"role": "user", "content": "oi"}]
    )
    assert fits is True
    assert reason == "fits"
    assert estimated < 100


def test_oversized_prompt_is_rejected_before_the_model() -> None:
    huge = "a" * (LOCAL_CONTEXT_HARD_TOKEN_CAP * 4)  # ~4x the token cap in chars
    fits, estimated, reason = local_context_fits([{"role": "user", "content": huge}])
    assert fits is False
    assert reason == "over_hard_cap"
    assert estimated > LOCAL_CONTEXT_HARD_TOKEN_CAP


def test_image_parts_are_counted() -> None:
    fits, estimated, _ = local_context_fits(
        [
            {"role": "user", "content": "veja o grafico"},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "analise"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
                ],
            },
        ]
    )
    assert fits is True
    assert estimated >= 768, "imagem precisa contar na estimativa (mmproj consome janela)"


async def test_cloud_agent_mouth_is_not_guarded_by_local_window(monkeypatch) -> None:
    """Incidente 2026-09-10: a boca "agent" e nuvem (deepseek-v4), janela grande."""
    gw = ModelGateway(
        providers=[_provider("agent", "https://api.deepseek.com")],
        config=GatewayConfig(),
    )
    monkeypatch.setattr(
        gateway_module, "local_context_fits", lambda messages: (False, 99000, "over_hard_cap")
    )

    def _fake_generate(*args, **kwargs):
        return "ok"

    monkeypatch.setattr(gw, "generate", _fake_generate)
    out = await gw.chat_completion(
        [{"role": "user", "content": "oi"}],
        preferred_provider="agent",
        allow_fallback=False,
    )
    assert out == "ok"


async def test_local_llama_mouth_still_guarded(monkeypatch) -> None:
    gw = ModelGateway(
        providers=[_provider("agent", "http://127.0.0.1:8080/v1")],
        config=GatewayConfig(),
    )
    monkeypatch.setattr(
        gateway_module, "local_context_fits", lambda messages: (False, 99000, "over_hard_cap")
    )
    with pytest.raises(RuntimeError, match="local_context_exceeded"):
        await gw.chat_completion(
            [{"role": "user", "content": "oi"}],
            preferred_provider="agent",
            allow_fallback=False,
        )
