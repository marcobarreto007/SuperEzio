"""Tests for the DECISIVE_TRADE_ORDER mode.

Five test scenarios from the acceptance spec:
    1. Decisive prompt with valid candidate → BUY_CANDIDATE or WAIT.
    2. Liquidity formatting — raw float without unit is forbidden.
    3. Weak candidate (low confidence) → WAIT, not fake BUY.
    4. No candidate passes → REJECT_ALL, no empty response.
    5. Direct execution forbidden — never claims broker order placed.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Helpers — build scan state for testing the deterministic answer renderer
# ---------------------------------------------------------------------------


def _make_scan_state(
    message: str,
    candidates: list[dict] | None = None,
    rejected: list[dict] | None = None,
    rejected_count: int = 0,
    rejection_summary: dict | None = None,
    source_errors: list[str] | None = None,
    time_horizon: str = "14 days",
    safety_gates: bool = True,
) -> dict:
    state = {
        "message": message,
        "route": "market_scan",
        "time_horizon": time_horizon,
        "scan": {
            "candidates": candidates or [],
            "rejected": rejected or [],
            "rejected_count": rejected_count,
            "rejection_summary": rejection_summary or {},
            "universe": "US_CANADA_LIQUID",
            "filters": {
                "country": None,
                "sector": None,
                "resolved_countries": ["United States", "Canada"],
                "allow_penny_otc": False,
                "allow_microcap": False,
            },
            "source_errors": source_errors or [],
            "collected_at": "2026-05-22T21:00:00+00:00",
        },
    }
    if safety_gates:
        state["f51_verdict"] = {"passed": True, "confidence": 0.91}
        state["sdca_firewall"] = {"decision": "ALLOW", "confidence": 0.88}
    return state


_STRONG_CANDIDATE = {
    "ticker": "A",
    "name": "Agilent Technologies Inc",
    "market": "United States",
    "price": 114.96,
    "currency": "USD",
    "volume": 2_202_650,
    "catalyst": "Earnings release on 2026-05-27 after market close.",
    "risk": "Macro tape risk and sector rotation pressure.",
    "invalidation": "Close below prior-week low after earnings print.",
    "confidence": "medium",
    "provider": "finnhub",
}


_WEAK_CANDIDATE = {
    "ticker": "XYZ",
    "market": "United States",
    "price": 3.50,
    "currency": "USD",
    "volume": 50_000,
    "catalyst": "Rumored partnership announcement.",
    # no risk, no invalidation, no name, low volume, low price
}


# ---------------------------------------------------------------------------
# Test 1 — Decisive prompt + valid candidate → BUY_CANDIDATE or WAIT
# ---------------------------------------------------------------------------


def test_decisive_prompt_with_valid_candidate():
    """A decisive prompt with a strong candidate produces a model order."""
    from src.core.pipeline.nodes.agent import _market_scan_answer

    state = _make_scan_state(
        message="what stock would you recommend me to buy if I want to make a profit within the next 14 days?",
        candidates=[_STRONG_CANDIDATE],
    )

    answer = _market_scan_answer(state)

    # Mode and structure
    assert "DECISIVE_TRADE_ORDER" in answer
    assert "BUY_CANDIDATE" in answer or "WAIT" in answer
    assert "Primary Order Candidate" in answer
    assert "Suggested Order Plan" in answer
    assert "Stop/Invalidation" in answer or "Stop/Inval" in answer
    assert "Max Risk" in answer
    assert "Model Confidence" in answer
    assert "/100" in answer

    # Must NOT be just a research report
    assert "this is a market research report" not in answer.lower()

    # Must not claim guaranteed profit
    assert "guaranteed profit" not in answer.lower() or "not guaranteed profit" in answer.lower()

    # Must contain the model verdict line
    assert "Model verdict:" in answer


def test_decisive_prompt_with_strong_candidate_is_buy():
    """A strong candidate (catalyst+risk+invalidation+volume) should yield BUY_CANDIDATE."""
    from src.core.pipeline.nodes.agent import _market_scan_answer, _compute_model_confidence

    confidence = _compute_model_confidence(_STRONG_CANDIDATE)
    assert confidence >= 65, f"Strong candidate confidence {confidence} should be >= 65"

    state = _make_scan_state(
        message="what should I buy for the next 2 weeks?",
        candidates=[_STRONG_CANDIDATE],
    )

    answer = _market_scan_answer(state)
    assert "BUY_CANDIDATE" in answer
    assert "Model verdict: BUY_CANDIDATE" in answer


def test_buy_candidate_requires_f51_and_sdca_gates():
    """A decisive BUY cannot be emitted until F51 and SDCA evidence exist."""
    from src.core.pipeline.nodes.agent import _market_scan_answer

    state = _make_scan_state(
        message="what should I buy for the next 2 weeks?",
        candidates=[_STRONG_CANDIDATE],
        safety_gates=False,
    )

    answer = _market_scan_answer(state)

    assert "Final Decision: BUY_CANDIDATE" not in answer
    assert "Model verdict: BUY_CANDIDATE" not in answer
    assert "WAIT" in answer
    assert "missing_f51_verdict" in answer
    assert "missing_sdca_firewall" in answer


# ---------------------------------------------------------------------------
# Test 2 — Liquidity formatting: raw float without unit is forbidden
# ---------------------------------------------------------------------------


def test_liquidity_formatting_has_units():
    """Volume/liquidity must render with units, not raw floats."""
    from src.core.pipeline.nodes.agent import _format_liquidity

    assert "M shares/day" in _format_liquidity(2_202_650)
    assert "2.20M shares/day" == _format_liquidity(2_202_650)

    assert "K shares/day" in _format_liquidity(50_000)
    assert "50.0K shares/day" == _format_liquidity(50_000)

    assert "shares/day" in _format_liquidity(500)
    assert "500 shares/day" == _format_liquidity(500)

    assert "B shares/day" in _format_liquidity(1_500_000_000)

    assert _format_liquidity(None) == "—"
    assert _format_liquidity(0) == "—"
    assert _format_liquidity(-1) == "—"

    assert "2.20M shares/day" in _format_liquidity("2.20M shares")
    assert _format_liquidity("") == "—"


def test_liquidity_in_decisive_answer_has_units():
    """The decisive answer must render liquidity with units, not raw floats."""
    from src.core.pipeline.nodes.agent import _market_scan_answer

    state = _make_scan_state(
        message="what stock would you recommend me to buy?",
        candidates=[_STRONG_CANDIDATE],
    )

    answer = _market_scan_answer(state)

    # Must contain formatted liquidity
    assert "2.20M shares/day" in answer
    # Raw float must NOT appear alone
    assert "2202650" not in answer
    assert "2.20265" not in answer


def test_liquidity_in_old_format_also_has_units():
    """Non-decisive prompts also get formatted liquidity (regression fix)."""
    from src.core.pipeline.nodes.agent import _market_scan_answer

    state = _make_scan_state(
        # This prompt does NOT match decisive hints → old 8-section format
        message="scan US technology equities for 2-week opportunities",
        candidates=[_STRONG_CANDIDATE],
    )

    answer = _market_scan_answer(state)

    # Old format should also have units
    assert "2.20M shares/day" in answer
    assert "2202650" not in answer


# ---------------------------------------------------------------------------
# Test 3 — Weak candidate → WAIT, not fake BUY
# ---------------------------------------------------------------------------


def test_weak_candidate_produces_wait():
    """If confidence is below threshold, decision must be WAIT, not fake BUY."""
    from src.core.pipeline.nodes.agent import _market_scan_answer, _compute_model_confidence

    confidence = _compute_model_confidence(_WEAK_CANDIDATE)
    assert confidence < 65, f"Weak candidate confidence {confidence} should be < 65"

    state = _make_scan_state(
        message="what stock would you recommend me to buy?",
        candidates=[_WEAK_CANDIDATE],
    )

    answer = _market_scan_answer(state)

    assert "DECISIVE_TRADE_ORDER" in answer
    assert "WAIT" in answer
    assert "Final Decision: WAIT" in answer or "Decisao Final: WAIT" in answer
    # The Final Decision line must NOT say BUY_CANDIDATE
    assert "Final Decision: BUY_CANDIDATE" not in answer
    assert "Decisao Final: BUY_CANDIDATE" not in answer
    assert "Model verdict: WAIT" in answer

    # WAIT answer must explain why
    assert "below" in answer.lower() or "watchlist" in answer.lower()
    assert "upgrade" in answer.lower() or "elevaria" in answer.lower()


# ---------------------------------------------------------------------------
# Test 4 — No candidate passes → REJECT_ALL
# ---------------------------------------------------------------------------


def test_no_candidate_produces_reject_all():
    """When zero candidates pass, decision must be REJECT_ALL."""
    from src.core.pipeline.nodes.agent import _market_scan_answer

    state = _make_scan_state(
        message="what should I buy for the next 14 days?",
        candidates=[],
        rejected=[
            {"ticker": "AAA", "rejected_reason": "missing_price"},
            {"ticker": "BBB", "rejected_reason": "missing_liquidity"},
        ],
        rejected_count=2,
        rejection_summary={"missing_price": 1, "missing_liquidity": 1},
    )

    answer = _market_scan_answer(state)

    assert isinstance(answer, str)
    assert len(answer) > 100, "REJECT_ALL answer must not be empty"
    assert "DECISIVE_TRADE_ORDER" in answer
    assert "REJECT_ALL" in answer
    assert "Model verdict: REJECT_ALL" in answer

    # No junk ticker should appear as a recommendation
    assert "AAA" not in answer or "rejected" in answer.lower()
    assert "BBB" not in answer or "rejected" in answer.lower()


# ---------------------------------------------------------------------------
# Test 5 — Direct execution forbidden
# ---------------------------------------------------------------------------


def test_no_direct_execution_claims():
    """Bob must never claim it placed, executed, or sent an order to a broker."""
    from src.core.pipeline.nodes.agent import _market_scan_answer

    for msg in (
        "what stock would you recommend me to buy?",
        "give me an order",
        "best trade for next 2 weeks",
    ):
        state = _make_scan_state(
            message=msg,
            candidates=[_STRONG_CANDIDATE],
        )

        answer = _market_scan_answer(state)

        answer_lower = answer.lower()
        assert "order placed" not in answer_lower
        assert "order sent" not in answer_lower
        assert "order executed" not in answer_lower
        assert "order filled" not in answer_lower
        assert "sent to broker" not in answer_lower
        assert "executed the trade" not in answer_lower
        assert "trade placed" not in answer_lower


# ---------------------------------------------------------------------------
# Test 6 — Intent detection for decisive prompts
# ---------------------------------------------------------------------------


def test_decisive_trade_intent_detection():
    """Decisive trade prompts must be detected correctly."""
    from src.core.pipeline.intents import detect_decisive_trade_intent

    # Should detect
    assert detect_decisive_trade_intent("what stock would you recommend me to buy?")
    assert detect_decisive_trade_intent("what should I buy for the next 2 weeks?")
    assert detect_decisive_trade_intent("give me an order")
    assert detect_decisive_trade_intent("best trade for next 14 days")
    assert detect_decisive_trade_intent("I want to make a profit in 14 days")
    assert detect_decisive_trade_intent("qual comprar para lucrar em 2 semanas?")
    assert detect_decisive_trade_intent("me da uma ordem de compra")
    assert detect_decisive_trade_intent(
        "Bob estamos em treinamento com 100k, objetivo e oredens rapidas entara e saida "
        "com stop loss por 1 hora; pesuise e aplike 10 k em oportunidades explosisvas"
    )

    # Should NOT detect
    assert not detect_decisive_trade_intent("scan US technology equities")
    assert not detect_decisive_trade_intent("analyze AAPL")
    assert not detect_decisive_trade_intent("what is a penny stock?")
    assert not detect_decisive_trade_intent("")
    assert not detect_decisive_trade_intent("hello Bob")


def test_paper_training_ticket_prompt_routes_to_market_scan():
    from src.core.pipeline.intents import (
        detect_decisive_trade_intent,
        parse_user_intent,
    )

    prompt = (
        "Bob, estamos em treinamento paper com 100k. Sem enviar ordem ao broker. "
        "Pesquise e monte um ticket para 10k em oportunidade rapida de 1 hora, "
        "com stop loss. Mostre quais modulos decidiram."
    )

    assert detect_decisive_trade_intent(prompt)

    parsed = parse_user_intent(prompt, rigor="strict", ticker="")
    plan = parsed.to_plan()

    assert parsed.route == "market_scan"
    assert parsed.intent == "market_scan"
    assert parsed.action == "scan_market"
    assert plan["scanner_allowed"] is True
    assert "market_scan" in plan["allowed_tools"]
    assert "submit_paper_order" in plan["allowed_tools"]


def test_paper_training_prompt_returns_pending_ticket_not_research_report(monkeypatch):
    from src.core.pipeline.nodes.agent import _market_scan_answer

    monkeypatch.delenv("SUPEREZIO_ENABLE_PAPER_ORDER_SUBMIT", raising=False)
    state = _make_scan_state(
        message=(
            "Bob estamos em treinamento com 100k para investir; objetivo e oredens rapidas "
            "entara e saida com stop loss; vamos ver em 1 hora de treino; "
            "pesuise e aplike 10 k dos nossos 100 em oportunidades explosisvas"
        ),
        candidates=[_STRONG_CANDIDATE],
        time_horizon="1 hours",
    )

    answer = _market_scan_answer(state)

    assert "PAPER_TICKET_PENDING_APPROVAL" in answer
    assert "Ticket Paper" in answer or "Paper Ticket" in answer
    assert "10,000" in answer
    assert "100,000" in answer
    assert "Quantidade estimada" in answer or "Estimated quantity" in answer
    assert "transmissao paper desabilitada" in answer
    assert "Model verdict: PAPER_TICKET_PENDING_APPROVAL" in answer
    assert "relatorio de pesquisa" not in answer.lower()
    assert "order placed" not in answer.lower()
    assert "order executed" not in answer.lower()


def test_paper_training_prompt_can_render_submit_ready_when_gate_enabled(monkeypatch):
    from src.core.pipeline.nodes.agent import _market_scan_answer

    monkeypatch.setenv("SUPEREZIO_ENABLE_PAPER_ORDER_SUBMIT", "1")
    state = _make_scan_state(
        message=(
            "Bob estamos em treinamento paper com 100k. Pesquise e aplique 10k "
            "em oportunidade rapida com stop loss."
        ),
        candidates=[_STRONG_CANDIDATE],
        time_horizon="1 hours",
    )
    state["allowed_tools"] = ["market_scan", "submit_paper_order", "final_answer"]
    state["ticket_allowed"] = True

    answer = _market_scan_answer(state)

    assert "PAPER_ORDER_SUBMIT_READY" in answer
    assert "submit_paper_order LMT" in answer
    assert "Confirmacao humana obrigatoria" not in answer
    assert "live-money continua bloqueado" in answer


# ---------------------------------------------------------------------------
# Test 7 — Non-decisive prompt still gets old format
# ---------------------------------------------------------------------------


def test_paper_training_money_parser_separates_ticket_size_from_account():
    from src.core.pipeline.nodes.agent import (
        _extract_account_reference,
        _extract_requested_allocation,
        _market_scan_answer,
    )

    prompt = (
        "Bob, estamos em treinamento paper com 100k. Sem enviar ordem ao broker. "
        "Pesquise e monte um ticket para 10k em oportunidade rapida de 1 hora, "
        "com stop loss. Mostre quais modulos decidiram."
    )

    assert _extract_requested_allocation(prompt) == 10_000
    assert _extract_account_reference(prompt) == 100_000

    state = _make_scan_state(
        message=prompt,
        candidates=[_STRONG_CANDIDATE],
        time_horizon="1 hours",
    )
    answer = _market_scan_answer(state)

    assert "Capital do treino solicitado: 10,000" in answer
    assert "Capital teorico citado: 100,000" in answer
    assert "Capital teorico citado: 1\n" not in answer


def test_non_decisive_prompt_keeps_research_format():
    """Non-decisive prompts must still get the old 8-section research report."""
    from src.core.pipeline.nodes.agent import _market_scan_answer

    state = _make_scan_state(
        # This message does NOT trigger decisive mode
        message="scan US equities for opportunities in the next 2 weeks",
        candidates=[_STRONG_CANDIDATE],
    )

    answer = _market_scan_answer(state)

    # Should have old format markers
    assert "market research report" in answer.lower() or "research" in answer.lower()
    assert "DECISIVE_TRADE_ORDER" not in answer
    assert "Model verdict" not in answer


# ---------------------------------------------------------------------------
# P0 — Gate failures, follow-up routing, ranked candidates
# ---------------------------------------------------------------------------


def test_buy_blocked_missing_liquidity_in_answer():
    from src.core.pipeline.nodes.agent import _market_scan_answer

    candidate = {
        **_STRONG_CANDIDATE,
        "volume": None,
        "avg_daily_volume_shares": None,
    }
    state = _make_scan_state(
        message="what stock would you recommend me to buy?",
        candidates=[candidate],
    )
    answer = _market_scan_answer(state)
    assert "Final Decision: BUY_CANDIDATE" not in answer
    assert "Model Confidence:" in answer
    assert any(x in answer for x in ("WAIT", "REJECT_ALL"))


def test_buy_blocked_missing_risk_in_answer():
    from src.core.pipeline.nodes.agent import _market_scan_answer

    candidate = {**_STRONG_CANDIDATE, "risk": "—"}
    state = _make_scan_state(
        message="what stock would you recommend me to buy?",
        candidates=[candidate],
    )
    answer = _market_scan_answer(state)
    assert "Final Decision: BUY_CANDIDATE" not in answer
    assert "missing_risk" in answer or "Gate failures" in answer


def test_wait_candidate_is_not_rendered_as_primary_order():
    from src.core.pipeline.nodes.agent import _market_scan_answer

    candidate = {**_STRONG_CANDIDATE, "risk": "—"}
    state = _make_scan_state(
        message="what stock would you recommend me to buy?",
        candidates=[candidate],
    )

    answer = _market_scan_answer(state)

    assert "Final Decision: WAIT" in answer
    assert "Model verdict: WAIT" in answer
    assert "Primary Order Candidate" not in answer
    assert "Suggested Order Plan" not in answer
    assert "Study Candidate" in answer
    assert "No entry" in answer


def test_follow_up_another_recommendation_excludes_prior():
    from src.core.pipeline.nodes.agent import _render_decisive_trade_order

    second = {
        **_STRONG_CANDIDATE,
        "ticker": "MSFT",
        "name": "Microsoft Corporation",
    }
    ranked = [
        {
            "candidate": _STRONG_CANDIDATE,
            "confidence": 85,
            "gate_failures": [],
            "eligible": True,
            "decision": "BUY_CANDIDATE",
        },
        {
            "candidate": second,
            "confidence": 82,
            "gate_failures": [],
            "eligible": True,
            "decision": "BUY_CANDIDATE",
        },
    ]
    state = {
        "message": "give me another recommendation",
        "intent": "another_trade_recommendation",
        "route": "market_scan",
        "time_horizon": "14 days",
        "trade_order_context": {
            "mode": "DECISIVE_TRADE_ORDER",
            "primary_ticker": "A",
            "excluded_tickers": ["A"],
            "time_horizon": "14 days",
            "universe": "US_CANADA_LIQUID",
            "ranked_candidates": ranked,
        },
        "scan": {
            "candidates": [_STRONG_CANDIDATE, second],
            "ranked_candidates": ranked,
            "rejected_count": 0,
            "rejection_summary": {},
            "universe": "US_CANADA_LIQUID",
            "filters": {},
            "source_errors": [],
        },
    }
    answer, ctx = _render_decisive_trade_order(state)
    assert "DECISIVE_TRADE_ORDER_FOLLOWUP" in answer
    assert "MSFT" in answer
    assert "Previous Candidate Excluded: A" in answer
    assert ctx is not None
    assert "MSFT" in ctx.get("excluded_tickers", []) or ctx.get("primary_ticker") == "MSFT"


def test_follow_up_no_second_candidate_reject_all():
    from src.core.pipeline.nodes.agent import _render_decisive_trade_order

    ranked = [
        {
            "candidate": _STRONG_CANDIDATE,
            "confidence": 85,
            "gate_failures": [],
            "eligible": True,
            "decision": "BUY_CANDIDATE",
        },
    ]
    state = {
        "message": "give me another recommendation",
        "intent": "another_trade_recommendation",
        "route": "market_scan",
        "time_horizon": "14 days",
        "trade_order_context": {
            "mode": "DECISIVE_TRADE_ORDER",
            "primary_ticker": "A",
            "excluded_tickers": ["A"],
            "ranked_candidates": ranked,
        },
        "scan": {
            "candidates": [_STRONG_CANDIDATE],
            "ranked_candidates": ranked,
            "rejected_count": 3,
            "rejection_summary": {"missing_liquidity": 2, "missing_risk": 1},
            "universe": "US_CANADA_LIQUID",
            "filters": {},
            "source_errors": [],
        },
    }
    answer, _ = _render_decisive_trade_order(state)
    assert "REJECT_ALL" in answer
    assert "No second candidate passed the quality gate" in answer
    assert len(answer) > 80


def test_follow_up_cached_scan_preserves_rejection_telemetry():
    from src.core.pipeline.nodes.agent import _render_decisive_trade_order
    from src.core.pipeline.nodes.collector import _scan_from_cached_ranked

    ranked = [
        {
            "candidate": _STRONG_CANDIDATE,
            "confidence": 85,
            "gate_failures": [],
            "eligible": True,
            "decision": "BUY_CANDIDATE",
        },
    ]
    state = {
        "message": "what stock would you recommend me to buy?",
        "route": "market_scan",
        "time_horizon": "14 days",
        "scan": {
            "candidates": [_STRONG_CANDIDATE],
            "ranked_candidates": ranked,
            "rejected_count": 23,
            "rejection_summary": {
                "missing_short_term_thesis": 20,
                "missing_price": 2,
                "missing_risk": 1,
            },
            "universe": "US_CANADA_LIQUID",
            "filters": {"resolved_countries": ["United States", "Canada"]},
            "source_errors": ["price_provider: no_provider_result_for_price=1"],
        },
        "f51_verdict": {"passed": True, "confidence": 0.91},
        "sdca_firewall": {"decision": "ALLOW", "confidence": 0.88},
    }

    _, ctx = _render_decisive_trade_order(state)
    assert ctx is not None
    assert ctx["rejected_count"] == 23
    assert ctx["rejection_summary"]["missing_short_term_thesis"] == 20

    cached = _scan_from_cached_ranked(ctx, "I want another recommendation.", ["A"])

    assert cached["rejected_count"] == 23
    assert cached["rejection_summary"]["missing_short_term_thesis"] == 20
    assert cached["source_errors"] == ["price_provider: no_provider_result_for_price=1"]


def test_another_trade_intent_parsing_with_context():
    from src.core.pipeline.intents import parse_user_intent

    parsed = parse_user_intent(
        "give me another recommendation",
        trade_order_context={"mode": "DECISIVE_TRADE_ORDER", "primary_ticker": "A"},
    )
    assert parsed.intent == "another_trade_recommendation"
    assert parsed.route == "market_scan"


def test_confidence_not_80_with_weak_data():
    from src.core.pipeline.nodes.agent import _compute_model_confidence

    weak = {**_STRONG_CANDIDATE, "risk": "—", "volume": 100}
    assert _compute_model_confidence(weak) < 80
