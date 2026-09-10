"""Regressao 2026-09-10 (2o ramo): pedido de mercado sem dado nao vira enlatado.

A falha de dado (sem provider/chave) cai no catch-all de
_contract_fallback_answer e servia o texto de advisory ("not a ticker-first"),
que parece recusa deliberada. Agora devolve veredito honesto de insumo.
"""

from core.pipeline.nodes.agent import (
    _contract_fallback_answer,
    _is_market_data_request_without_data,
    _no_data_market_answer,
)

CANNED = "not a ticker-first"


def test_market_scan_without_data_is_honest_pt():
    state = {"message": "pesquisa oportunidades de curto prazo nas bolsas", "route": "market_scan"}
    answer = _contract_fallback_answer(state)
    assert CANNED not in answer
    assert "nao invento candidato" in answer.lower()


def test_market_scan_without_data_is_honest_en():
    state = {
        "message": "find short term opportunities now",
        "route": "market_scan",
        "intent": "market_scan",
    }
    answer = _contract_fallback_answer(state)
    assert CANNED not in answer
    assert "missing data input" in answer.lower()


def test_scanner_invoked_flag_also_counts():
    state = {"message": "find short term opportunities now", "scanner_invoked": True}
    answer = _contract_fallback_answer(state)
    assert CANNED not in answer


def test_advisory_without_market_context_keeps_deliberate_answer():
    state = {"message": "o que e diversificacao?"}
    answer = _contract_fallback_answer(state)
    assert CANNED in answer  # comportamento deliberado (commit 3ac68461)


USER_SCAN_MSG = (
    "Pesquise oportunidades de curto prazo nas bolsas canadenses e americanas, apenas ativos listados. "
    "Prefira ETFs sem comissao quando existirem. Mostre os candidatos que passaram nos gates com entrada, stop e alvo."
)


def test_scan_message_without_route_field_still_honest():
    """Incidente 2: no run real o state nao tinha route na hora do fallback."""
    answer = _contract_fallback_answer({"message": USER_SCAN_MSG})
    assert CANNED not in answer
    assert "WAIT" in answer


def test_market_detection_uses_message_when_state_is_bare():
    assert _is_market_data_request_without_data({"message": USER_SCAN_MSG}) is True
    assert _is_market_data_request_without_data({"message": "me da uma dica"}) is True


def test_market_detection_matrix():
    assert _is_market_data_request_without_data({"route": "market_scan"}) is True
    assert _is_market_data_request_without_data({"intent": "another_trade_recommendation"}) is True
    assert _is_market_data_request_without_data({"scanner_invoked": True}) is True
    assert _is_market_data_request_without_data({"cognitive_mode": "TICKER_ANALYSIS"}) is True
    assert _is_market_data_request_without_data({"message": "oi"}) is False


def test_no_data_answer_mentions_wait_not_refusal():
    pt = _no_data_market_answer({"message": "pesquisa oportunidades"})
    assert "WAIT" in pt
    assert "nao uma escolha de nao responder" in pt


def test_no_data_answer_carries_data_health():
    pt = _no_data_market_answer({"message": "pesquisa oportunidades"})
    assert "price=" in pt
    assert "catalyst=" in pt
