"""Unit tests for trade_order quality gates, liquidity, and confidence."""

from __future__ import annotations

from src.core.pipeline.trade_order import (
    MAX_CONFIDENCE_WITH_GATE_FAILURE,
    STRONG_CONFIDENCE_THRESHOLD,
    compute_model_confidence,
    decide_final_action,
    evaluate_quality_gates,
    format_liquidity_display,
    normalize_liquidity_fields,
    pick_candidate,
    rank_candidates,
    volume_shares_from_raw,
)


def _strong_candidate(**overrides) -> dict:
    base = {
        "ticker": "A",
        "name": "Agilent Technologies Inc",
        "price": 114.96,
        "currency": "USD",
        "avg_daily_volume_shares": 2_202_650,
        "catalyst": "Earnings release on 2026-05-27 after market close.",
        "risk": "Macro tape risk and sector rotation pressure.",
        "invalidation": "Close below prior-week low after earnings print.",
        "provider": "finnhub",
    }
    base.update(overrides)
    return base


def test_finnhub_millions_volume_renders_with_units():
    """Finnhub metric stored as share count must not render as '2 shares'."""
    candidate = _strong_candidate(avg_daily_volume_shares=2_202_650)
    text = format_liquidity_display(candidate)
    assert "2.20M shares/day" in text
    assert "2 shares" not in text
    assert "2.20265" not in text


def test_provider_scaled_volume_from_raw_metric():
    """After provider scaling, 2.20265M -> ~2.2M shares/day display."""
    shares = volume_shares_from_raw(2_202_650.0)
    assert shares == 2_202_650.0
    candidate = {"price": 114.96, "avg_daily_volume_shares": shares}
    assert "2.20M shares/day" in format_liquidity_display(candidate)


def test_buy_blocked_when_liquidity_invalid():
    candidate = _strong_candidate(avg_daily_volume_shares=50_000)
    ok, failures = evaluate_quality_gates(candidate)
    assert not ok
    assert "liquidity_below_minimum" in failures
    confidence = compute_model_confidence(candidate, gate_failures=failures)
    assert confidence <= MAX_CONFIDENCE_WITH_GATE_FAILURE
    assert decide_final_action(confidence, failures) != "BUY_CANDIDATE"


def test_buy_blocked_when_risk_missing():
    candidate = _strong_candidate(risk="—")
    ok, failures = evaluate_quality_gates(candidate)
    assert not ok
    assert "missing_risk" in failures
    confidence = compute_model_confidence(candidate, gate_failures=failures)
    assert confidence <= MAX_CONFIDENCE_WITH_GATE_FAILURE
    assert decide_final_action(confidence, failures) != "BUY_CANDIDATE"


def test_confidence_cannot_be_80_plus_with_gate_failures():
    candidate = _strong_candidate(risk="", avg_daily_volume_shares=None, volume=None)
    _, failures = evaluate_quality_gates(candidate)
    confidence = compute_model_confidence(candidate, gate_failures=failures)
    assert confidence < STRONG_CONFIDENCE_THRESHOLD


def test_rank_and_pick_excludes_previous_ticker():
    ranked = rank_candidates(
        [
            _strong_candidate(ticker="A"),
            _strong_candidate(ticker="MSFT", name="Microsoft"),
        ]
    )
    entry, _ = pick_candidate(ranked, excluded_tickers={"A"})
    assert entry is not None
    assert entry["candidate"]["ticker"] == "MSFT"


def test_normalize_liquidity_computes_dollar_volume():
    candidate = {"price": 100.0, "volume": 1_000_000}
    normalize_liquidity_fields(candidate)
    assert candidate["avg_daily_volume_shares"] == 1_000_000
    assert candidate["avg_daily_dollar_volume"] == 100_000_000.0
