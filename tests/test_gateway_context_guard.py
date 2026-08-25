"""Guarda pre-flight de contexto do gateway local (janela 8192 tokens).

A demo de 24/08 falhou com dois prompts de 34k-37k tokens rejeitados pelo
llama-server com 400 cru. O guard rejeita ANTES de mandar, com mensagem
acionavel. Estimativa conservadora: ~3 chars/token de texto e 768 tokens
por imagem.
"""

from __future__ import annotations

from core.model_serving.gateway import (
    LOCAL_CONTEXT_HARD_TOKEN_CAP,
    local_context_fits,
)


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
