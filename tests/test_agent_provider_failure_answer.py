"""Regressao: falha de provider vira resposta honesta.

O texto enlatado de contrato ("not a ticker-first request") parece recusa
deliberada do Bob — incidente 2026-09-10: BadRequestError do provider virou
essa resposta em vez de um erro honesto.
"""

from core.pipeline.nodes.agent import (
    _looks_like_provider_failure,
    _provider_failure_answer,
)

CANNED = "not a ticker-first request"
PROVIDER_FAILURE = "[ERROR] Provider agent failed: BadRequestError."


def test_provider_failure_answer_pt_is_honest():
    answer = _provider_failure_answer(
        {"message": "tenho 10 mil para investir, me da uma dica"}, PROVIDER_FAILURE
    )
    assert "Nao consegui falar com os modelos de nuvem" in answer
    assert "Provider agent failed: BadRequestError." in answer
    assert "nao foi respondida" in answer
    assert CANNED not in answer


def test_provider_failure_answer_en_is_honest():
    answer = _provider_failure_answer(
        {"message": "what should I buy now"}, "RuntimeError: All external providers failed"
    )
    assert "provider failure" in answer.lower()
    assert "All external providers failed" in answer
    assert CANNED not in answer


def test_looks_like_provider_failure_markers():
    assert _looks_like_provider_failure("BadRequestError: Error code: 400") is True
    assert _looks_like_provider_failure("All external providers failed") is True
    assert _looks_like_provider_failure("APIConnectionError: peer closed") is True
    assert _looks_like_provider_failure("local_context_exceeded: ~9000 tokens") is False
    assert _looks_like_provider_failure("ValueError: bad math") is False
