"""Número e narrativa separados: o número sai do código, a narrativa do LLM.

Achado nº 1 da auditoria de 11/09 — "conselho enlatado" com percentuais que
não dependem do dado, e auditoria circular (o LLM produz o número e o LLM
audita o número). O bind C3 é onde a separação acontece, e até 2026-09-14 ele
só enxergava "$190.50" e "1.23": "Recomendo alocar 8% do capital" atravessava
o bind sem ser olhado.

Regra verificada aqui: todo número material da resposta carrega a conta de
código que o produziu (``{valor, fonte, calculado_em}``); o número que não
tem fonte de código é registrado como não rastreado — nunca promovido a fato
do pipeline.
"""

from __future__ import annotations

import json

import pytest

from core.evidence.snapshot import (
    bind_answer_to_snapshot,
    freeze_snapshot,
    number_claims,
    number_ledger,
    unbound_number_claims,
)
from core.pipeline.contracts import PipelineState
from core.pipeline.graph import _policy_percentage_numbers

FROZEN_AT = "2026-09-14T12:00:00+00:00"


def _snapshot(*, fractions: bool = True) -> dict:
    numbers = {
        "price": {"value": 190.5, "unit": "quote", "formula_id": "fact.price"},
        "rsi": {"value": 55.0, "unit": "index", "formula_id": "math_hub.rsi14"},
        "sharpe": {"value": 1.4, "unit": "ratio", "formula_id": "math_hub.sharpe"},
    }
    if fractions:
        numbers["volatility"] = {
            "value": 0.3187,
            "unit": "fraction",
            "formula_id": "math_hub.volatility",
        }
    return {"frozen": True, "as_of": FROZEN_AT, "numbers": numbers}


# ── O defeito: número escrito pelo modelo entrava na saída ──────────────


def test_invented_percentage_is_rejected() -> None:
    """O caso do achado nº 1: conselho de alocação com percentual sem fonte."""
    raw = "Recomendo alocar 8% do capital nesse ativo, com risco de 2.5%."
    bound = bind_answer_to_snapshot(raw, _snapshot())
    assert bound != raw
    assert bound.startswith("SNAPSHOT BIND REJECTED")
    assert "8%" in bound and "2.5%" in bound
    assert "SNAPSHOT FROZEN" in bound


def test_invented_money_without_symbol_is_rejected() -> None:
    """ "3500 CAD" é dinheiro material mesmo sem o cifrão."""
    raw = "Invista cerca de 3500 CAD nesta entrada."
    assert bind_answer_to_snapshot(raw, _snapshot()).startswith("SNAPSHOT BIND REJECTED")


def test_spelled_percentage_is_rejected() -> None:
    raw = "Retorno esperado de 15 por cento ao ano."
    claims = unbound_number_claims(raw, _snapshot())
    assert [claim.trecho for claim in claims] == ["15 por cento"]
    assert claims[0].unidade == "percent"
    assert claims[0].motivo == "sem_fonte_de_codigo"


def test_clean_text_without_numbers_passes() -> None:
    raw = "A tese segue valida; o cenario nao mudou desde a ultima leitura."
    assert bind_answer_to_snapshot(raw, _snapshot()) == raw
    assert number_claims(raw, _snapshot()) == []


# ── O número do código passa, e passa com fonte ────────────────────────


def test_code_calculated_numbers_pass_with_source() -> None:
    raw = "AAPL a $190.50, RSI 55.00, volatilidade anualizada de 32%."
    assert bind_answer_to_snapshot(raw, _snapshot()) == raw
    fontes = {claim.trecho: claim.fonte for claim in number_claims(raw, _snapshot())}
    assert fontes["$190.50"] == "fact.price"
    assert fontes["55.00"] == "math_hub.rsi14"
    # 0.3187 é fração: o humano lê "32%", e é a mesma conta do código.
    assert fontes["32%"] == "math_hub.volatility"


def test_envelope_carries_value_source_and_when() -> None:
    """O envelope: {valor, fonte, calculado_em} — e o veredito ``rastreado``."""
    envelope = number_claims("O preco de $190.50 sustenta o alvo.", _snapshot())
    assert len(envelope) == 1
    claim = envelope[0].to_dict()
    assert claim["valor"] == 190.5
    assert claim["fonte"] == "fact.price"
    assert claim["calculado_em"] == FROZEN_AT
    assert claim["rastreado"] is True
    assert claim["motivo"] == ""


def test_percentage_cannot_stretch_to_a_fraction_number() -> None:
    """Regressão medida: "8%" não pode casar com volatility=0.3187.

    A leitura de fração de um percentual tem duas casas a mais de precisão
    (8% é 0.08); tolerância larga aqui aceitava qualquer fração como fonte.
    """
    assert unbound_number_claims("Alocar 8% do capital.", _snapshot())
    assert not unbound_number_claims("Alocar 32% do capital.", _snapshot())


def test_percent_claim_is_not_validated_by_a_price_row() -> None:
    """Regressão 2026-09-14: "8%" não é validado por latest_price=8.20.

    O primeiro branch do matching comparava o valor bruto contra qualquer
    linha do razão sem olhar a unidade: com zero casas a tolerância era
    ±0,5 e o preço 8.20 validava um "8%" de alocação — medidas diferentes
    não se validam.
    """
    snapshot = {
        "frozen": True,
        "as_of": FROZEN_AT,
        "numbers": {
            "latest_price": {
                "value": 8.20,
                "unit": "quote",
                "formula_id": "math_hub.latest_price",
            },
        },
    }
    claims = {claim.trecho: claim for claim in number_claims("Alocar 8% do capital.", snapshot)}
    assert claims["8%"].rastreado is False
    assert claims["8%"].motivo == "sem_fonte_de_codigo"

    # O caso legítimo continua de pé: com a linha fraction correspondente, o
    # mesmo "8%" sai rastreado com a fonte do código.
    snapshot["numbers"]["max_position_pct"] = {
        "value": 0.08,
        "unit": "fraction",
        "formula_id": "execution_policy.max_position_pct",
    }
    claims = {claim.trecho: claim for claim in number_claims("Alocar 8% do capital.", snapshot)}
    assert claims["8%"].rastreado is True
    assert claims["8%"].fonte == "execution_policy.max_position_pct"


def test_money_and_decimal_claims_do_not_validate_percent_rows() -> None:
    """Análogo money: "8 CAD" não é validado por linha 8.20 de outra medida.

    A tolerância de escrita (±0,5 com zero casas) só vale dentro da mesma
    grandeza: dinheiro cita dinheiro/preço; uma linha percentual do razão
    não valida nem dinheiro nem número decimal solto.
    """
    snapshot = {
        "frozen": True,
        "as_of": FROZEN_AT,
        "numbers": {
            "risk_pct": {"value": 8.20, "unit": "percent", "formula_id": "risk.limit"},
            "crisis_score": {
                "value": 8.20,
                "unit": "score",
                "formula_id": "math_hub.crisis_aggregate",
            },
        },
    }
    claims = {claim.trecho: claim for claim in number_claims("Entrar com 8 CAD.", snapshot)}
    assert claims["8 CAD"].rastreado is False
    assert claims["8 CAD"].motivo == "sem_fonte_de_codigo"

    # E o decimal cai no mesmo portão: "8.00" não valida a linha percentual.
    only_percent = {
        "frozen": True,
        "as_of": FROZEN_AT,
        "numbers": {"risk_pct": {"value": 8.0, "unit": "percent", "formula_id": "risk.limit"}},
    }
    claims = {
        claim.trecho: claim for claim in number_claims("Risco de 8.00 no indicador.", only_percent)
    }
    assert claims["8.00"].rastreado is False
    assert claims["8.00"].motivo == "sem_fonte_de_codigo"


def test_negative_code_number_keeps_its_sign() -> None:
    """Regressão do caso real (MSFT): "-23,38%" é o max_drawdown do código.

    Drawdown, VaR e CVaR são negativos no razão e negativos na prosa; sem
    capturar o sinal o extrator lia 23,38 e acusava de invenção o número que
    o próprio código calculou — o risco que a resposta mais precisa citar.
    """
    snapshot = {
        "frozen": True,
        "as_of": FROZEN_AT,
        "numbers": {
            "max_drawdown": {
                "value": -0.2338,
                "unit": "fraction",
                "formula_id": "math_hub.max_drawdown",
            },
            "var_95": {"value": -0.031656, "unit": "fraction", "formula_id": "math_hub.var_95"},
        },
    }
    raw = "drawdown maximo -23,38%, VaR 95% -3,17% ao dia."
    claims = {claim.trecho: claim for claim in number_claims(raw, snapshot)}
    assert claims["-23,38%"].fonte == "math_hub.max_drawdown"
    assert claims["-3,17%"].fonte == "math_hub.var_95"
    assert claims["-23,38%"].valor == -23.38
    assert not unbound_number_claims(raw, snapshot)

    # E o sinal não é ignorado: citar o número positivo não casa com a linha
    # negativa do razão. É conservador de propósito — inverter o sinal de um
    # número é justamente o que o LLM não pode fazer.
    assert unbound_number_claims("drawdown maximo 23,38%.", snapshot)


def test_confidence_level_of_a_ledger_formula_is_not_a_claim() -> None:
    """O "95" de "VaR 95%" é parâmetro da fórmula (var_95), não valor citado."""
    snapshot = {
        "frozen": True,
        "as_of": FROZEN_AT,
        "numbers": {
            "var_95": {"value": -0.031656, "unit": "fraction", "formula_id": "math_hub.var_95"},
        },
    }
    assert number_claims("VaR 95% de -3,17% ao dia.", snapshot)[0].trecho == "-3,17%"
    assert number_claims("VaR 95% de -3,17% ao dia.", snapshot)[0].fonte == "math_hub.var_95"

    # Sem a linha que consome o parâmetro, o percentual volta a ser cobrado:
    # "VaR 8%" não pode passar só porque tem o rótulo na frente.
    assert unbound_number_claims("VaR 8% ao dia.", snapshot)


def test_untraced_claim_reports_missing_snapshot() -> None:
    claims = number_claims("Alocar 8% do capital.", None)
    assert len(claims) == 1
    assert claims[0].rastreado is False
    assert claims[0].motivo == "sem_snapshot_congelado"


def test_casual_turn_without_frozen_snapshot_passes() -> None:
    raw = "Ola! Tudo certo com $999.99 na conta?"
    assert bind_answer_to_snapshot(raw, None) == raw
    assert bind_answer_to_snapshot(raw, {"frozen": False, "numbers": {}}) == raw


# ── O razão (ledger) é do código, não do texto ─────────────────────────


def test_ledger_rows_carry_source_and_timestamp() -> None:
    rows = {row["numero"]: row for row in number_ledger(_snapshot())}
    assert rows["sharpe"]["fonte"] == "math_hub.sharpe"
    assert rows["sharpe"]["calculado_em"] == FROZEN_AT
    assert rows["sharpe"]["unidade"] == "ratio"


def test_policy_percentage_enters_the_ledger() -> None:
    """Percentual do código (stop do sizing adaptativo) não pode virar invenção."""
    extra = _policy_percentage_numbers({"adaptive_config": {"stop_loss_pct": 0.05}})
    snapshot = freeze_snapshot(
        pack={"ticker": "AAPL", "facts": {}},
        math_report={},
        run_id="policy-ledger-test",
        extra_numbers=extra,
    )
    raw = "Stop obrigatorio em 5% abaixo da entrada."
    assert bind_answer_to_snapshot(raw, snapshot) == raw
    fonte = number_claims(raw, snapshot)[0].fonte
    assert fonte == "execution_policy.default_stop_pct"


def test_freeze_snapshot_without_extra_numbers_is_unchanged() -> None:
    snapshot = freeze_snapshot(pack={"ticker": "AAPL", "facts": {}}, math_report={}, run_id="r1")
    assert "default_stop_pct" not in (snapshot.get("numbers") or {})


# ── Contrato de determinismo: mesma entrada ⇒ mesma saída numérica ─────


def test_same_input_same_numeric_output() -> None:
    """Rodar o mesmo caminho duas vezes dá exatamente os mesmos números."""
    answer = "AAPL a $190.50, RSI 55, volatilidade de 32%, alocar 8% do capital."
    snapshot = _snapshot()

    first = [claim.to_dict() for claim in number_claims(answer, snapshot)]
    second = [claim.to_dict() for claim in number_claims(answer, dict(snapshot))]
    assert first == second

    bound_first = bind_answer_to_snapshot(answer, snapshot)
    bound_second = bind_answer_to_snapshot(answer, _snapshot())
    assert bound_first == bound_second


def test_numbers_do_not_depend_on_the_narrative() -> None:
    """Duas narrativas diferentes com os mesmos números ⇒ mesmos números."""
    a = "AAPL a $190.50 com volatilidade de 32%."
    b = "O papel fechou em $190.50; a vol anualizada ficou em 32%."
    valores_a = sorted(claim.valor for claim in number_claims(a, _snapshot()))
    valores_b = sorted(claim.valor for claim in number_claims(b, _snapshot()))
    assert valores_a == valores_b == [32.0, 190.5]


# ── Ligação no pipeline: o canal de saída do agente ────────────────────


def test_number_claims_is_a_declared_state_channel() -> None:
    assert "number_claims" in PipelineState.__annotations__


@pytest.mark.asyncio
async def test_agent_node_emits_number_claims(monkeypatch) -> None:
    """O canal do agente leva o envelope: número com fonte e número sem fonte."""
    from core.pipeline.nodes import agent as agent_module

    monkeypatch.setenv("SUPEREZIO_ARCH_C3", "1")
    monkeypatch.setattr(agent_module, "get_stream_writer", lambda: lambda _event: None)
    answer = "Bob: AAPL a $190.50. Sugiro alocar 8% do capital."

    class MockGateway:
        async def chat_completion(self, **kwargs):
            return json.dumps({"tool": "final_answer", "args": {"content": answer}})

    state = {
        "run_id": "number-provenance-test",
        "route": "general",
        "message": "me fala do risco de concentracao em AAPL",
        "ticker": "AAPL",
        "agent_iterations": 1,
        "snapshot": _snapshot(),
        "data": {"ticker": "AAPL", "price": {"price": 190.5}},
    }
    result = await agent_module.node_agent(dict(state), gateway=MockGateway())

    claims = result["number_claims"]
    por_trecho = {claim["trecho"]: claim for claim in claims}
    assert por_trecho["8%"]["rastreado"] is False
    assert por_trecho["8%"]["fonte"] == ""
    assert por_trecho["8%"]["motivo"] == "sem_fonte_de_codigo"

    # Mesma entrada, mesma saída: o envelope não depende de sorte nem de ordem.
    again = await agent_module.node_agent(dict(state), gateway=MockGateway())
    assert again["number_claims"] == claims


@pytest.mark.asyncio
async def test_agent_node_skips_envelope_when_c3_off(monkeypatch) -> None:
    from core.pipeline.nodes import agent as agent_module

    monkeypatch.setenv("SUPEREZIO_ARCH_C3", "0")
    monkeypatch.setattr(agent_module, "get_stream_writer", lambda: lambda _event: None)

    class MockGateway:
        async def chat_completion(self, **kwargs):
            return json.dumps({"tool": "final_answer", "args": {"content": "Bob: ok."}})

    result = await agent_module.node_agent(
        {
            "run_id": "number-provenance-c3-off",
            "route": "general",
            "message": "me fala do risco de concentracao em AAPL",
            "agent_iterations": 1,
            "snapshot": _snapshot(),
        },
        gateway=MockGateway(),
    )
    assert result.get("number_claims", []) == []
