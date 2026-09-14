"""Tests for Marcos López de Prado's Meta-Labeling & Triple Barrier Gate."""

from __future__ import annotations

from core.trading.execution_policy import meta_labeling_block_reason
from core.trading.meta_labeling import (
    BarrierProfile,
    build_barriers,
    evaluate_meta_labeling_gate,
)


def test_build_barriers_buy():
    barriers = build_barriers(
        entry_price=100.0,
        stop_loss_price=95.0,  # $5 risk
        take_profit_price=115.0,  # $15 reward
        side="BUY",
    )
    assert isinstance(barriers, BarrierProfile)
    assert barriers.stop_distance == 5.0
    assert barriers.profit_distance == 15.0
    assert barriers.asymmetry_ratio == 3.0


def test_build_barriers_default_asymmetry():
    barriers = build_barriers(entry_price=50.0, side="BUY")
    assert barriers.stop_loss_price == 47.5  # 5% default stop ($2.50)
    assert barriers.asymmetry_ratio == 2.5  # default 2.5:1
    assert barriers.take_profit_price == 56.25  # 50 + 2.5 * 2.5


def test_meta_labeling_allows_favorable_setup():
    state = {
        "expert_consensus": {"decision": "SUPPORT", "score": 0.8},
        "neural_decision": {"decision": "UP"},
        "math_report": {
            "modules": {"technical_indicators": {"values": {"atr_14": 1.0, "rsi_14": 42.0}}}
        },
        "data": {"price": {"volume": 500_000}},
    }

    result = evaluate_meta_labeling_gate(
        state,
        "SPY",
        side="BUY",
        entry_price=100.0,
        stop_loss_price=96.0,
        take_profit_price=112.0,  # 3:1 asymmetry
    )

    assert result.allowed is True
    assert result.decision == "ALLOW"
    assert result.code == "META_LABEL_ALLOW"
    assert result.meta_probability > 0.65
    assert result.sizing_multiplier > 0.3
    assert result.rejection_reason is None


def test_meta_labeling_abstains_on_poor_asymmetry():
    # 1:1 risk/reward is unacceptable under López de Prado triple barrier
    state = {}
    result = evaluate_meta_labeling_gate(
        state,
        "SPY",
        side="BUY",
        entry_price=100.0,
        stop_loss_price=95.0,  # $5 risk
        take_profit_price=105.0,  # $5 reward -> 1.0 R:R < 2.0 min
    )

    assert result.allowed is False
    assert result.decision == "ABSTAIN"
    assert result.code == "META_LABEL_ASYMMETRY_TOO_LOW"
    assert "insufficient_asymmetry" in result.rejection_reason


def test_meta_labeling_abstains_on_conflicting_consensus():
    # Committee opposes the trade
    state = {
        "expert_consensus": {"decision": "BLOCK", "score": -0.8},
        "neural_decision": {"decision": "DOWN"},
        "math_report": {
            "modules": {
                "technical_indicators": {
                    "values": {"atr_14": 5.0, "rsi_14": 75.0}  # Overbought + high vol
                }
            }
        },
    }

    result = evaluate_meta_labeling_gate(
        state,
        "SPY",
        side="BUY",
        entry_price=100.0,
        stop_loss_price=96.0,
        take_profit_price=110.0,
    )

    assert result.allowed is False
    assert result.decision == "ABSTAIN"
    assert result.code == "META_LABEL_ABSTAIN"
    assert result.meta_probability < 0.50
    assert result.sizing_multiplier == 0.0


def test_meta_labeling_block_reason_integration():
    # Favorable state -> block reason is None
    fav_state = {
        "expert_consensus": {"decision": "SUPPORT", "score": 0.5},
        "neural_decision": {"decision": "UP"},
    }
    assert (
        meta_labeling_block_reason(
            fav_state,
            "SPY",
            side="BUY",
            entry_price=100.0,
            stop_loss_price=96.0,
            take_profit_price=112.0,
        )
        is None
    )

    # Low asymmetry -> block reason returned
    bad_state = {}
    reason = meta_labeling_block_reason(
        bad_state,
        "SPY",
        side="BUY",
        entry_price=100.0,
        stop_loss_price=95.0,
        take_profit_price=102.0,  # 0.4 R:R
    )
    assert reason is not None
    assert "insufficient_asymmetry" in reason
