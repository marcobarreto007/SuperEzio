"""Contract tests for orchestrator node — intent classification and routing."""

import os

import src.core.pipeline.nodes.orchestrator as orchestrator_node
from src.core.pipeline.nodes.orchestrator import (
    ALLOWED_INTENTS,
    ALLOWED_ROUTES,
    _extract_time_horizon,
    _render_plan,
    node_orchestrator,
)


def _noop_writer(_event: dict) -> None:
    return None


# ---------------------------------------------------------------------------
# Route constants
# ---------------------------------------------------------------------------


def test_allowed_routes_are_non_empty():
    assert len(ALLOWED_ROUTES) >= 3
    assert "general" in ALLOWED_ROUTES
    assert "ticker_analysis" in ALLOWED_ROUTES
    assert "market_scan" in ALLOWED_ROUTES


def test_allowed_intents_cover_all_routes():
    assert len(ALLOWED_INTENTS) >= 5
    assert "general_question" in ALLOWED_INTENTS
    assert "market_scan" in ALLOWED_INTENTS


def test_ibkr_broker_status_question_is_not_ticker_analysis():
    from src.core.pipeline.intents import (
        detect_broker_status_intent,
        detect_ticker,
        parse_user_intent,
    )

    prompt = (
        "Bob, qual e seu estado atual? Voce esta em modo paper/read-only no IBKR? "
        "Explique o que consegue ler e o que nao pode fazer."
    )

    assert detect_broker_status_intent(prompt)
    assert detect_ticker(prompt) == ""

    parsed = parse_user_intent(prompt, rigor="strict", ticker="")
    assert parsed.route == "general"
    assert parsed.intent == "general_question"
    assert parsed.ticker == ""
    assert "broker_status_question" in parsed.reasons


def test_ibkr_paper_order_prompt_routes_to_market_scan_not_status(monkeypatch):
    from src.core.pipeline.intents import (
        detect_broker_status_intent,
        detect_decisive_trade_intent,
        detect_ticker,
        parse_user_intent,
    )

    monkeypatch.delenv("SUPEREZIO_ENABLE_PAPER_ORDER_SUBMIT", raising=False)
    prompt = (
        "Bob, estamos em treinamento paper na IBKR com capital teorico de 100k. "
        "Use 10k para buscar uma oportunidade de investimento com retorno esperado "
        "em uma semana. Envie a ordem paper LMT pelo IBKR paper se os gates aprovarem. "
        "Nao use dinheiro real."
    )

    assert detect_decisive_trade_intent(prompt)
    assert not detect_broker_status_intent(prompt)
    assert detect_ticker(prompt) == ""
    assert detect_ticker("analyze IBKR stock") == "IBKR"

    parsed = parse_user_intent(prompt, rigor="strict", ticker="")
    plan = parsed.to_plan()
    assert parsed.route == "market_scan"
    assert parsed.intent == "market_scan"
    assert plan["scanner_allowed"] is True
    assert plan["ticket_allowed"] is False
    assert "submit_paper_order" not in plan["allowed_tools"]

    monkeypatch.setenv("SUPEREZIO_ENABLE_PAPER_ORDER_SUBMIT", "1")
    enabled_plan = parse_user_intent(prompt, rigor="strict", ticker="").to_plan()
    assert enabled_plan["ticket_allowed"] is True
    assert "submit_paper_order" in enabled_plan["allowed_tools"]


def test_operational_status_with_no_recommendation_blocks_market_tools():
    from src.core.pipeline.intents import detect_market_scan_intent, parse_user_intent

    prompt = "Responda curto: qual e o estado operacional do sistema agora? Nao recomende compra."

    assert not detect_market_scan_intent(prompt)

    parsed = parse_user_intent(prompt, rigor="strict", ticker="")
    plan = parsed.to_plan()
    assert parsed.route == "general"
    assert parsed.intent == "general_question"
    assert plan["cognitive_mode"] == "STATUS_ONLY"
    assert plan["scanner_allowed"] is False
    assert plan["ticket_allowed"] is False
    assert plan["allowed_tools"] == ["final_answer"]


# ---------------------------------------------------------------------------
# Time horizon extraction
# ---------------------------------------------------------------------------


def test_extract_time_horizon_english_days():
    assert _extract_time_horizon("AAPL 14 days") == "14 days"
    assert _extract_time_horizon("analyze 3 day forecast") == "3 days"


def test_extract_time_horizon_hours():
    assert _extract_time_horizon("treino de 1 hora") == "1 hours"
    assert _extract_time_horizon("paper trade for 2 hours") == "2 hours"


def test_extract_time_horizon_english_weeks():
    assert _extract_time_horizon("2 weeks outlook") == "2 weeks"


def test_extract_time_horizon_english_months():
    assert _extract_time_horizon("1 month forecast") == "1 months"


def test_extract_time_horizon_portuguese():
    assert _extract_time_horizon("14 dias") == "14 days"
    assert _extract_time_horizon("2 semanas") == "2 weeks"
    assert _extract_time_horizon("3 meses") == "3 months"
    assert _extract_time_horizon("1 ano") == "12 months"


def test_extract_time_horizon_empty():
    assert _extract_time_horizon("") == ""
    assert _extract_time_horizon("no time mentioned here") == ""


# ---------------------------------------------------------------------------
# Plan rendering
# ---------------------------------------------------------------------------


def test_render_plan_minimal():
    result = _render_plan({"route": "general", "intent": "general_question"})
    assert "general" in result
    assert "general_question" in result


def test_render_plan_with_ticker():
    result = _render_plan(
        {
            "route": "ticker_analysis",
            "intent": "ticker_analysis",
            "ticker": "AAPL",
            "intent_confidence": 0.95,
        }
    )
    assert "AAPL" in result
    assert "ticker_analysis" in result


# ---------------------------------------------------------------------------
# Node: empty state (deterministic path)
# ---------------------------------------------------------------------------


def test_node_orchestrator_empty_state():
    """Orchestrator must produce a valid plan even with empty state."""
    os.environ["UNIVERSAL_SKIP_GATEWAY"] = "1"
    import asyncio

    orchestrator_node.get_stream_writer = lambda: _noop_writer

    async def _run():
        return await node_orchestrator(
            {"message": "Hello", "rigor": "strict", "run_id": "test-orch-1"}
        )

    result = asyncio.run(_run())
    assert isinstance(result, dict)
    assert "route" in result
    assert result["route"] in ALLOWED_ROUTES
    assert "intent" in result
    assert result["intent"] in ALLOWED_INTENTS


def test_node_orchestrator_portuguese_prompt():
    """Portuguese financial prompts must not be blocked."""
    os.environ["UNIVERSAL_SKIP_GATEWAY"] = "1"
    import asyncio

    orchestrator_node.get_stream_writer = lambda: _noop_writer

    async def _run():
        return await node_orchestrator(
            {
                "message": "quero uma dica de investimento",
                "rigor": "strict",
                "run_id": "test-orch-pt",
            }
        )

    result = asyncio.run(_run())
    assert isinstance(result, dict)
    # Must not route to needs_scope for Portuguese financial prompts
    assert result.get("route") != "needs_scope"


def test_node_orchestrator_extracts_time_horizon():
    """Time horizon from user message must be extracted into plan."""
    os.environ["UNIVERSAL_SKIP_GATEWAY"] = "1"
    import asyncio

    orchestrator_node.get_stream_writer = lambda: _noop_writer

    async def _run():
        return await node_orchestrator(
            {
                "message": "AAPL 14 days analysis",
                "rigor": "strict",
                "run_id": "test-orch-horizon",
            }
        )

    result = asyncio.run(_run())
    assert "time_horizon" in result
    assert "14 days" in result.get("time_horizon", "")


def test_node_orchestrator_ignores_classifier_gateway_in_passthrough(monkeypatch):
    """Passthrough mode must not call or trust a classifier gateway."""
    import asyncio

    monkeypatch.delenv("SUPEREZIO_BOB_SOVEREIGN", raising=False)
    orchestrator_node.get_stream_writer = lambda: _noop_writer

    class MockGateway:
        async def chat_completion(self, **kwargs):
            return (
                '{"route":"general","intent":"capital_allocation","action":"answer",'
                '"ticker":"","risk_tolerance":"alta","filters":{},'
                '"required_slots":[],"confidence":0.91,"reasons":["ceo_risk"]}'
            )

    async def _run():
        return await node_orchestrator(
            {
                "message": "quero alocar em small caps agressivas por 2 anos",
                "rigor": "strict",
                "run_id": "test-orch-risk",
            },
            gateway=MockGateway(),
            config=None,
        )

    result = asyncio.run(_run())
    assert result["intent_source"] == "passthrough"
    assert result["intent"] == "bob_decides"
    assert result["risk_tolerance"] == "moderada"


def test_detect_ticker_no_prefix_false_positives():
    """Keyword prefixes must not capture leftovers as tickers.

    Regression 2026-08-23: "apenas ativos listados" produced ticker "S"
    ("ativo" matched the prefix of "ativos" and the leftover "s" became
    the symbol). Same class for "acoes".
    """
    from core.pipeline.intents import detect_ticker

    assert detect_ticker("apenas ativos listados") == ""
    assert detect_ticker("acoes e etfs") == ""
    assert detect_ticker("ativo: AAPL") == "AAPL"
    assert detect_ticker("papel PETR4") == "PETR4"
