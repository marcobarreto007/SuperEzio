"""Contract 2026-09-05 — "Sugestão sem ticker".

A suggestion request (capital + risk profile, no ticker, no order/scan
vocabulary) must route to a product-strategy answer — never to a market scan,
DECISIVE_TRADE_ORDER/REJECT_ALL, or the old "stay in cash / give me a ticker"
dead-end. Scans and orders with explicit vocabulary stay intact.
"""

from __future__ import annotations

from src.core.pipeline.intents import (
    detect_capital_allocation_intent,
    detect_decisive_trade_intent,
    is_product_strategy_suggestion,
    parse_user_intent,
)
from src.core.pipeline.nodes.agent import _forced_tool_call_before_final
from src.core.pipeline.strategy_speech import render_product_strategy_suggestion

B1 = "quero investir 1000 cad em alto risco"
B2 = "quero que vc escolha e me diga um produto"
B3 = B1 + " " + B2
B4_RESERVA = "reserva vs etf"
B4_EMERGENCIA = "reserva de emergencia vs investir em etf"
B5 = (
    "cara eu tenho 100 cad para investir o que vc me suugere , quero risco alto e maximo de retorno"
)
MINI_CAP = "vamos investir 100 cad segunda , escolhe mini cap"
TICKER_PROMPT = "me indica uma acao barata com catalisador para comprar"

_BANNED = (
    "REJECT_ALL",
    "US_CANADA_LIQUID",
    "price_routes",
    "Limite de dados",
    "prompt sugerido",
    "2 semanas",
    "fica em caixa",
    "td.to",
)


def _lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.strip()]


class TestRoutingSuggestionIsNotScan:
    def test_suggestion_messages_are_detected(self):
        # Detector exige verbo de sugestao ("escolhe/sugere/me diga um produto");
        # B1/B5 (sem verbo ou com typo) caem na heuristica de investimento
        # no despacho do agent (coberto abaixo) — nunca em scan.
        for msg in (B2, B3):
            assert is_product_strategy_suggestion(msg) is True, msg
        assert is_product_strategy_suggestion(MINI_CAP) is False
        assert is_product_strategy_suggestion(TICKER_PROMPT) is False

    def test_suggestion_messages_are_not_decisive(self):
        for msg in (B1, B2, B3, B4_RESERVA, B4_EMERGENCIA, B5):
            assert detect_decisive_trade_intent(msg) is False, msg
        assert detect_decisive_trade_intent(MINI_CAP) is True  # scan/ordem intacto

    def test_suggestion_routes_to_answer_without_scanner(self):
        for msg in (B1, B2, B3, B4_RESERVA, B4_EMERGENCIA):
            parsed = parse_user_intent(msg, rigor="strict", ticker="")
            assert parsed.route == "general", msg
            assert parsed.intent in {
                "capital_allocation",
                "personal_finance",
                "general_question",
            }, msg
            assert parsed.action == "answer", msg
            plan = parsed.to_plan()
            assert plan["scanner_allowed"] is False
            tools = plan.get("allowed_tools") or []
            assert "market_scan" not in tools

    def test_capital_allocation_detected(self):
        for msg in (B1, B3, B5):
            assert detect_capital_allocation_intent(msg) is True, msg

    def test_scan_vocabulary_stays_scan(self):
        parsed = parse_user_intent(MINI_CAP, rigor="strict", ticker="")
        assert parsed.route == "market_scan"
        assert parsed.to_plan()["scanner_allowed"] is True


class TestForcedToolsNeverScanSuggestion:
    def _state(self, experts_done: bool) -> dict:
        return {
            "message": B3,
            "route": "general",
            "intent": "capital_allocation",
            "action": "answer",
            "ticker": "",
            "scan": None,
            "data": None,
            "allowed_tools": ["final_answer", "run_experts"],
            "scanner_allowed": False,
            "executed_tools": ["run_experts"] if experts_done else [],
            "expert_results": [{"ok": True}] if experts_done else None,
        }

    def test_no_forced_scan_after_experts(self):
        assert _forced_tool_call_before_final(self._state(experts_done=True)) is None

    def test_experts_still_precede(self):
        forced = _forced_tool_call_before_final(self._state(experts_done=False))
        assert forced is not None
        assert forced["tool"] == "run_experts"


class TestSuggestionSpeech:
    def test_speech_content_pt(self):
        answer = render_product_strategy_suggestion(B3)
        lowered = answer.lower()
        assert "1000" in lowered
        assert "alto risco" in lowered
        assert len(_lines(answer)) <= 16
        for token in _BANNED:
            assert token not in lowered, token
        # honesty about live data + two explicit next steps
        assert "ao vivo" in lowered or "verificado" in lowered or "neste run" in lowered
        assert "pode escanear" in lowered or "candidato" in lowered

    def test_speech_offers_product_classes(self):
        answer = render_product_strategy_suggestion(B1)
        assert "etf" in answer.lower() or "gic" in answer.lower() or "hisa" in answer.lower()

    def test_speech_english_variant(self):
        answer = render_product_strategy_suggestion("invest 1000 cad high risk", portuguese=False)
        assert len(_lines(answer)) <= 16
        assert "REJECT_ALL" not in answer

    def test_personal_finance_framework_not_scan(self):
        """'reserva vs ETF' gets a planning framework, never a scan report."""
        from src.core.pipeline.nodes.agent import _contract_fallback_answer

        answer = _contract_fallback_answer(
            {
                "message": B4_EMERGENCIA,
                "intent": "capital_allocation",
                "action": "answer",
                "route": "general",
            }
        )
        lowered = answer.lower()
        assert "reserva" in lowered
        for token in _BANNED:
            assert token not in lowered, token
