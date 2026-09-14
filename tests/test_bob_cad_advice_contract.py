"""Contract tests for Bob investment advice in CAD and Survival Protocol routing.

Garante que pedidos de conselho/dica/ideia de investimento em CAD nunca caiam
em scan cego de penny stocks com REJECT_ALL ("fica em caixa / peca mini caps"),
mas sim recebam a alocacao do Protocolo de Sobrevivencia TD Canada.
"""

from __future__ import annotations

from core.pipeline.intents import (
    detect_decisive_trade_intent,
    is_product_strategy_suggestion,
    parse_user_intent,
)
from core.pipeline.strategy_speech import render_product_strategy_suggestion

USER_PROMPT = "oi bob , me de uma dica de investimento de 500 cad e porquye"
VARIATION_DICA = "me de uma dica de 500 cad"
VARIATION_IDEIA = "me da uma ideia de investimento com 1000 cad"


def test_user_prompt_detected_as_product_strategy_suggestion():
    assert is_product_strategy_suggestion(USER_PROMPT) is True
    assert is_product_strategy_suggestion(VARIATION_DICA) is True
    assert is_product_strategy_suggestion(VARIATION_IDEIA) is True


def test_user_prompt_is_not_decisive_trade_order():
    assert detect_decisive_trade_intent(USER_PROMPT) is False
    assert detect_decisive_trade_intent(VARIATION_DICA) is False


def test_user_prompt_routes_to_general_answer_without_scanner():
    parsed = parse_user_intent(USER_PROMPT, rigor="strict", ticker="")
    assert parsed.route == "general"
    assert parsed.intent == "personal_finance"
    assert parsed.action == "answer"
    plan = parsed.to_plan()
    assert plan["scanner_allowed"] is False
    assert "market_scan" not in (plan.get("allowed_tools") or [])


def test_cad_strategy_speech_answers_why_and_cites_td_etfs():
    speech = render_product_strategy_suggestion(USER_PROMPT)
    lowered = speech.lower()

    # Leitura do valor e protocolo de sobrevivência
    assert "500" in lowered
    assert "sobrevivencia" in lowered or "sobrevivência" in lowered

    # Cita os ETFs do universo TD
    assert "vfv.to" in lowered or "xeqt.to" in lowered or "zeb.to" in lowered

    # Responde o porquê: taxa zero, risco estrito, meta-labeling
    assert "taxa zero" in lowered
    assert "risco" in lowered
    assert "meta-labeling" in lowered

    # Não deve sugerir mini caps nem mandar ficar em caixa com reject all
    assert "mini cap" not in lowered
    assert "fica em caixa" not in lowered
    assert "reject_all" not in lowered
