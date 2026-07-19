from __future__ import annotations

from copy import deepcopy

import pytest

from core.trading.outcome_learning import (
    DEFAULT_EXPERT_WEIGHTS,
    OutcomeConflictError,
    OutcomeLearningEngine,
    get_effective_expert_weights,
)


def _closed_trade(**overrides):
    trade = {
        "trade_id": "trade-001",
        "ticker": "AAPL",
        "direction": "long",
        "entry_price": 100.0,
        "exit_price": 110.0,
        "shares": 10,
        "pnl_amount": 100.0,
        "entry_date": "2026-07-18T12:00:00+00:00",
        "exit_date": "2026-07-19T12:00:00+00:00",
        "outcome": "win",
        "confidence_at_entry": 80.0,
        "prediction_probability_at_entry": 0.8,
        "prediction_class_at_entry": "UP",
        "calibration_status": "calibrated",
        "model_id": "neural-test-v1",
        "risk_at_entry": 50.0,
        "expert_predictions": {
            "crisis": {"direction": "UP", "confidence": 0.7},
            "fundamental": {"direction": "UP", "confidence": 0.9},
        },
    }
    trade.update(overrides)
    return trade


def test_closed_outcome_updates_reward_and_weights_once(tmp_path):
    engine = OutcomeLearningEngine(tmp_path / "learning.sqlite3")

    first = engine.process_trade(_closed_trade())
    replay = engine.process_trade(_closed_trade())

    assert first.processed is True
    assert replay.processed is False
    assert first.reward["total_reward"] > 0
    assert replay.reward == first.reward
    assert replay.normalized_weights == first.normalized_weights
    assert sum(first.normalized_weights.values()) == pytest.approx(1.0)


def test_same_outcome_version_with_changed_payload_is_conflict(tmp_path):
    engine = OutcomeLearningEngine(tmp_path / "learning.sqlite3")
    original = _closed_trade()
    changed = deepcopy(original)
    changed["pnl_amount"] = 999.0

    engine.process_trade(original)
    with pytest.raises(OutcomeConflictError):
        engine.process_trade(changed)


@pytest.mark.parametrize(
    "change",
    [
        {"outcome": None},
        {"outcome": "pending"},
        {"exit_price": None},
        {"exit_date": None},
    ],
)
def test_non_terminal_trade_never_learns(tmp_path, change):
    engine = OutcomeLearningEngine(tmp_path / "learning.sqlite3")
    with pytest.raises(ValueError):
        engine.process_trade(_closed_trade(**change))


def test_loss_reduces_losing_expert_relative_to_winner(tmp_path):
    engine = OutcomeLearningEngine(tmp_path / "learning.sqlite3")
    engine.process_trade(
        _closed_trade(
            expert_predictions={"fundamental_value": {"direction": "UP", "confidence": 0.8}}
        )
    )
    engine.process_trade(
        _closed_trade(
            trade_id="trade-002",
            outcome="loss",
            exit_price=90.0,
            pnl_amount=-100.0,
            expert_predictions={"macro_risk": {"direction": "UP", "confidence": 0.8}},
        )
    )

    weights = engine.get_normalized_weights()
    assert weights["fundamental_value"] > weights["macro_risk"]


def test_reward_uses_ex_ante_risk_not_realized_price_move(tmp_path):
    engine = OutcomeLearningEngine(tmp_path / "learning.sqlite3")
    result = engine.process_trade(_closed_trade(risk_at_entry=200.0, pnl_amount=100.0))
    assert result.reward["risk_adjusted_reward"] == pytest.approx(0.5)


def test_effective_weights_use_priors_before_any_outcome(tmp_path):
    weights = get_effective_expert_weights(tmp_path / "missing.sqlite3")
    assert weights == DEFAULT_EXPERT_WEIGHTS


def test_effective_weights_blend_learned_reliability_and_remain_normalized(tmp_path):
    db_path = tmp_path / "learning.sqlite3"
    engine = OutcomeLearningEngine(db_path)
    engine.process_trade(
        _closed_trade(
            expert_predictions={
                "fundamental_value": {"direction": "UP", "confidence": 0.9},
                "macro_risk": {"direction": "UP", "confidence": 0.7},
            }
        )
    )
    engine.process_trade(
        _closed_trade(
            trade_id="trade-002",
            outcome="loss",
            exit_price=90.0,
            pnl_amount=-100.0,
            expert_predictions={"macro_risk": {"direction": "UP", "confidence": 0.7}},
        )
    )

    weights = get_effective_expert_weights(db_path)
    assert sum(weights.values()) == pytest.approx(1.0)
    assert weights["fundamental_value"] > DEFAULT_EXPERT_WEIGHTS["fundamental_value"]
    assert weights["macro_risk"] < DEFAULT_EXPERT_WEIGHTS["macro_risk"]


def test_role_aliases_update_the_canonical_pipeline_role(tmp_path):
    engine = OutcomeLearningEngine(tmp_path / "learning.sqlite3")
    engine.process_trade(
        _closed_trade(
            expert_predictions={"fundamental": {"direction": "UP", "confidence": 0.9}}
        )
    )
    assert engine.get_normalized_weights() == {"fundamental_value": 1.0}


def test_opposite_expert_directions_receive_opposite_credit(tmp_path):
    engine = OutcomeLearningEngine(tmp_path / "learning.sqlite3")
    engine.process_trade(
        _closed_trade(
            expert_predictions={
                "fundamental_value": {"direction": "UP", "confidence": 0.9},
                "macro_risk": {"direction": "DOWN", "confidence": 0.9},
            },
        )
    )
    weights = engine.get_normalized_weights()
    assert weights["fundamental_value"] > weights["macro_risk"]


def test_legacy_confidence_without_direction_does_not_change_weights(tmp_path):
    engine = OutcomeLearningEngine(tmp_path / "learning.sqlite3")
    result = engine.process_trade(
        _closed_trade(expert_predictions={}, expert_attribution={"fundamental": 0.99})
    )
    assert result.normalized_weights == {}


def test_uncalibrated_entry_score_is_not_used_as_probability(tmp_path):
    engine = OutcomeLearningEngine(tmp_path / "learning.sqlite3")
    result = engine.process_trade(
        _closed_trade(
            calibration_status="not_calibrated",
            prediction_probability_at_entry=0.99,
        )
    )
    assert result.reward["confidence_alignment"] == 0.0


def test_price_direction_not_trade_win_drives_expert_credit(tmp_path):
    engine = OutcomeLearningEngine(tmp_path / "learning.sqlite3")
    result = engine.process_trade(
        _closed_trade(
            direction="short",
            outcome="win",
            exit_price=90.0,
            pnl_amount=100.0,
            prediction_class_at_entry="DOWN",
            expert_predictions={
                "fundamental_value": {"direction": "DOWN", "confidence": 0.9},
                "macro_risk": {"direction": "UP", "confidence": 0.9},
            },
        )
    )
    assert result.normalized_weights["fundamental_value"] > result.normalized_weights["macro_risk"]
