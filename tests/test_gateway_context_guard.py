"""Guarda pre-flight de contexto do gateway local (janela 98304 tokens).

A demo de 24/08 falhou com dois prompts de 34k-37k tokens rejeitados pelo
llama-server com 400 cru. O guard rejeita ANTES de mandar, com mensagem
acionavel. Estimativa conservadora: ~3 chars/token de texto e 768 tokens
por imagem.

A janela era 8192 (era Qwen3.8) e subiu para 98304 em 11/09/2026, quando o
build de 2 GPUs passou a servir -c 98304 (medido: prefill ~1255 tok/s,
geracao ~32 tok/s em prompt de 7k).
"""

from __future__ import annotations

import pytest

import core.model_serving.gateway as gateway_module
from core.model_serving.gateway import (
    LOCAL_CONTEXT_HARD_TOKEN_CAP,
    LOCAL_CONTEXT_OUTPUT_RESERVE,
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
        gateway_module,
        "local_context_fits",
        lambda messages, window=None: (False, 99000, "over_hard_cap"),
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
        gateway_module,
        "local_context_fits",
        lambda messages, window=None: (False, 99000, "over_hard_cap"),
    )
    with pytest.raises(RuntimeError, match="local_context_exceeded"):
        await gw.chat_completion(
            [{"role": "user", "content": "oi"}],
            preferred_provider="agent",
            allow_fallback=False,
        )


# ── Janela 98304 (11/09/2026) ──────────────────────────────────────────────
# Contagens medidas com /tokenize do servidor real em 11/09/2026:
#   financial_engine.py 1.647 | f51_trade_gate.py 7.055 | tool_executor.py 11.710
#   gateway.py 12.372 | endpoints.py 29.482          (soma dos 5: 62.266)
# Com o teto antigo (8000), TRES dos cinco eram inalcancaveis para a boca local.

_TOKENS_ENDPOINTS_PY = 29_482
_TETO_ANTIGO = 8_000
_JANELA_REAL_DO_SERVIDOR = 98_304  # -c 98304 no start-f51.ps1


def test_arquivo_real_que_antes_estourava_agora_cabe() -> None:
    """O endpoints.py do proprio repo (29.482 tokens) era rejeitado antes daqui.

    Falha no codigo antigo: com o teto de 8000 o guard recusava o prompt e a
    boca local nao conseguia ler um arquivo medio do SuperEzio.
    """
    conteudo = "a" * (_TOKENS_ENDPOINTS_PY * 3)  # o estimador usa len // 3
    fits, estimated, reason = local_context_fits([{"role": "user", "content": conteudo}])

    assert estimated > _TETO_ANTIGO, "o teste so prova algo se estourar o teto antigo"
    assert fits is True
    assert reason == "fits"


def test_teto_deixa_folga_para_geracao() -> None:
    """Teto HARD tem que caber na janela real e ainda sobrar espaco pra resposta."""
    assert LOCAL_CONTEXT_HARD_TOKEN_CAP <= _JANELA_REAL_DO_SERVIDOR
    folga = _JANELA_REAL_DO_SERVIDOR - LOCAL_CONTEXT_HARD_TOKEN_CAP
    assert folga >= 2_000, f"sobra de {folga} tokens e pouca para a geracao"


# ── A janela vem do provedor (refactor 11/09/2026) ─────────────────────────
# Antes o teto era so a constante do modulo. Agora ModelProvider.n_ctx (lido de
# config/runtime.yml, entrada local_voice) vence a constante, e a constante
# virou fallback para quando a janela nao e declarada.


def test_janela_do_provedor_vence_a_constante() -> None:
    """n_ctx declarado no config manda; a constante so vale sem declaracao."""
    # um token acima do teto de fallback: reprovado sem janela...
    conteudo = "a" * (LOCAL_CONTEXT_HARD_TOKEN_CAP * 3 + 30)
    assert local_context_fits([{"role": "user", "content": conteudo}])[0] is False

    # ...e aprovado quando o endpoint declara uma janela 4x maior.
    janela = LOCAL_CONTEXT_HARD_TOKEN_CAP * 4
    fits, estimated, reason = local_context_fits([{"role": "user", "content": conteudo}], janela)
    assert estimated > LOCAL_CONTEXT_HARD_TOKEN_CAP
    assert fits is True
    assert reason == "fits"


def test_janela_declarada_desconta_a_folga_de_saida() -> None:
    """Entrada e resposta dividem o slot: teto efetivo = janela - reserva."""
    janela = 32_000
    teto = janela - LOCAL_CONTEXT_OUTPUT_RESERVE

    no_teto = "a" * (teto * 3)  # o estimador usa len // 3
    assert local_context_fits([{"role": "user", "content": no_teto}], janela)[0] is True

    acima = "a" * (teto * 3 + 3)
    assert local_context_fits([{"role": "user", "content": acima}], janela)[0] is False


def test_provedor_sem_janela_usa_o_fallback() -> None:
    """n_ctx=0 ou ausente preserva o comportamento anterior ao refactor."""
    conteudo = "a" * (LOCAL_CONTEXT_HARD_TOKEN_CAP * 3)  # estimated == cap
    assert local_context_fits([{"role": "user", "content": conteudo}], 0)[0] is True
    assert local_context_fits([{"role": "user", "content": conteudo}], None)[0] is True


def test_janela_vem_do_config() -> None:
    """Ponta: ModelConfig.n_ctx (is_local) -> janela que o guard recebe.

    Sem esta ligacao o guard cai sempre no fallback, que era o problema.
    """
    from core.config.schema import UniversalConfig
    from core.model_serving.providers import _local_window_from_config

    cfg = UniversalConfig.from_dict(
        {
            "models": {
                "local_voice": {"name": "voz", "is_local": True, "n_ctx": 98_304},
                "agent": {"name": "nuvem", "is_local": False, "n_ctx": 4_096},
            }
        }
    )
    assert _local_window_from_config(cfg) == 98_304, "so o modelo is_local conta"


def test_config_so_com_nuvem_nao_declara_janela() -> None:
    """Sem modelo local no config a janela e 0 -> guard usa o fallback."""
    from core.config.schema import UniversalConfig
    from core.model_serving.providers import _local_window_from_config

    cfg = UniversalConfig.from_dict(
        {"models": {"agent": {"name": "nuvem", "is_local": False, "n_ctx": 98_304}}}
    )
    assert _local_window_from_config(cfg) == 0


def test_runtime_yml_declara_a_janela_do_endpoint_local() -> None:
    """O config REAL precisa declarar a janela, senao o guard cai no fallback.

    Regressao de 11/09/2026: ate entao nenhuma entrada declarava n_ctx, entao o
    guard ignorava o servidor real (-c 98304) e barrava em 8000 tokens.
    """
    import yaml

    from core.config.schema import UniversalConfig
    from core.model_serving.providers import _local_window_from_config

    with open("config/runtime.yml", encoding="utf-8") as handle:
        cfg = UniversalConfig.from_dict(yaml.safe_load(handle))

    janela = _local_window_from_config(cfg)
    assert janela == _JANELA_REAL_DO_SERVIDOR, (
        f"config/runtime.yml declara {janela}, mas o servidor serve "
        f"{_JANELA_REAL_DO_SERVIDOR}. Guard e servidor tem que concordar."
    )
