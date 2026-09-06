"""100 CAD + investir is allocation speech, not a 2-week scan dump."""

from __future__ import annotations

from src.core.pipeline.intents import (
    _has_scan_scope,
    _is_market_scan_request,
    detect_capital_allocation_intent,
    parse_user_intent,
)
from src.core.pipeline.nodes.agent import _contract_fallback_answer, _market_scan_answer
from src.core.pipeline.prompts.builder import build_agent_prompt

OPERATOR_CAD100 = (
    "cara eu tenho 100 cad para investir o que vc me suugere , quero risco alto e maximo de retorno"
)
MINI_CAP = "vamos investir 100 cad segunda , escolhe mini cap"

_TELEMETRY = (
    "US_CANADA_LIQUID",
    "REJECT_ALL",
    "price_routes_active",
    "Limite de dados",
    "prompt sugerido",
)


def _nonempty_lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.strip()]


def test_operator_cad100_investir_is_capital_allocation_not_scan():
    assert detect_capital_allocation_intent(OPERATOR_CAD100) is True
    assert _has_scan_scope(OPERATOR_CAD100) is False
    assert _is_market_scan_request(OPERATOR_CAD100) is False

    parsed = parse_user_intent(OPERATOR_CAD100, rigor="strict", ticker="")
    assert parsed.route == "general"
    assert parsed.intent == "capital_allocation"
    plan = parsed.to_plan()
    assert plan["scanner_allowed"] is False


def test_forty_cad_penny_stock_stays_scan():
    prompt = (
        "cara, em vez de gastar 40 CAD na Lotto Quebec, acha uma penny stock "
        "que me dê adrenalina sem perder tudo"
    )
    assert detect_capital_allocation_intent(prompt) is False
    assert _is_market_scan_request(prompt) is True


def test_mini_cap_prompt_stays_market_scan():
    parsed = parse_user_intent(MINI_CAP, rigor="strict", ticker="")
    assert parsed.route == "market_scan"
    assert parsed.intent == "market_scan"
    assert detect_capital_allocation_intent(MINI_CAP) is False


def test_operator_cad100_speech_is_short_and_has_no_scan_telemetry():
    """Contract 2026-09-05: a suggestion request (capital + risk profile, no
    ticker) gets a product-strategy suggestion — not the old "stay in cash /
    give me a ticker (TD.TO)" scan dead-end."""
    state = {"message": OPERATOR_CAD100, "intent": "capital_allocation"}
    answer = _contract_fallback_answer(state)
    lowered = answer.lower()
    for token in _TELEMETRY:
        assert token not in answer, token
    assert "fica em caixa" not in lowered
    assert "td.to" not in lowered
    assert "100" in lowered
    assert "alto risco" in lowered or "risco" in lowered
    assert len(_nonempty_lines(answer)) <= 16
    assert "2 semanas" not in lowered


def test_empty_scan_speech_omits_chunk_telemetry():
    state = {
        "message": "Bob, pesquisa mercado pequeno com risco alto",
        "scan": {
            "candidates": [],
            "rejected": [{"ticker": "GRTS", "rejected_reason": "missing_price"}],
            "rejected_count": 20,
            "rejection_summary": {"missing_price": 20},
            "universe": "US_CANADA_LIQUID",
            "filters": {"resolved_countries": ["United States", "Canada"]},
            "source_errors": ["price_provider: exception=20", "price_routes_active: finnhub"],
        },
    }
    answer = _market_scan_answer(state)
    assert "Nenhum candidato passou" in answer
    assert "GRTS" not in answer
    assert "US_CANADA_LIQUID" not in answer
    assert "REJECT_ALL" not in answer
    assert "price_routes_active" not in answer
    assert "Limite de dados" not in answer
    assert "prompt sugerido" not in answer.lower()


def test_small_ticket_prompt_skips_twelve_section_contract():
    prompt = build_agent_prompt(
        {
            "message": OPERATOR_CAD100,
            "intent": "capital_allocation",
            "route": "general",
        }
    )
    assert "SMALL CAPITAL ADVISORY" in prompt
    assert "COMPLEX FINANCE ADVISORY CONTRACT" not in prompt
    assert "12-section" in prompt or "12 short lines" in prompt
