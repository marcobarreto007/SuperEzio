import pytest
import sys
from pathlib import Path

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.pipeline.intents import parse_user_intent
from core.pipeline.case import create_case


@pytest.mark.parametrize(
    "msg,ui_ticker,expected_case,expected_intent",
    [
        ("bob tudo bem", "TD.TO", "casual", "general_question"),
        ("oi bob", "TD.TO", "casual", "general_question"),
        ("fala bob beleza", "TD.TO", "casual", "general_question"),
        ("bom dia bob", "TD.TO", "casual", "general_question"),
        ("boa tarde", "", "casual", "general_question"),
        ("TD.TO", "", "investment_analysis", "ticker_analysis"),
        ("analise TD.TO", "", "investment_analysis", "ticker_analysis"),
        ("escanear mercado de penny stocks", "", "market_discovery", "market_scan"),
    ],
)
def test_intent_classification_matrix(msg, ui_ticker, expected_case, expected_intent):
    case = create_case(msg, ticker=ui_ticker)
    parsed = parse_user_intent(msg, ticker=ui_ticker)
    assert case.case_type.value == expected_case, (
        f"Expected case {expected_case} for '{msg}', got {case.case_type.value}"
    )
    assert parsed.intent == expected_intent, (
        f"Expected intent {expected_intent} for '{msg}', got {parsed.intent}"
    )


@pytest.mark.asyncio
async def test_casual_greeting_pipeline_fast_path():
    from core.pipeline import build_graph

    p = build_graph()
    chunks = []
    steps = []
    async for ev in p.stream_events("bob tudo bem", ticker="TD.TO"):
        if ev.get("type") == "CHUNK":
            chunks.append(ev.get("content", ""))
        elif ev.get("type") == "PIPELINE_STEP":
            steps.append(ev)
    p.shutdown()

    assert any("Tudo ótimo por aqui" in c or "Bob a postos" in c for c in chunks), (
        f"Expected casual greeting reply, got: {chunks}"
    )
    assert not any(s.get("step") == "f51_firewall" and s.get("status") == "failed" for s in steps)


def test_buy_question_is_not_casual():
    from core.pipeline.intents import _is_casual_message

    assert _is_casual_message("Compro TD.TO ou nao?") is False
    assert _is_casual_message("compro TD.TO") is False
    assert _is_casual_message("TD.TO recomenda?") is False


def test_buy_question_does_not_skip_trinity():
    from core.pipeline.graph import _is_simple_query

    assert _is_simple_query({"message": "Compro TD.TO ou nao?", "ticker": "TD.TO"}) is False
    assert _is_simple_query({"message": "TD.TO recomenda?", "ticker": "TD.TO"}) is False
    assert _is_simple_query({"message": "analisa o grafico de TD.TO", "ticker": "TD.TO"}) is False
    assert _is_simple_query({"message": "porque comprar TD.TO", "ticker": "TD.TO"}) is False
    assert _is_simple_query({"message": "TD.TO rsi", "ticker": "TD.TO"}) is True
