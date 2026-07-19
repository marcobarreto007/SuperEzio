"""Execution must honor the neural model's abstention and direction."""

from __future__ import annotations

import pytest

from core.trading.execution_policy import evaluate_neural_execution_gate


def _ready(direction: str = "UP") -> dict:
    return {
        "neural_decision": {
            "status": "ready",
            "decision": direction,
            "direction_prob": {"up": 0.7, "down": 0.1, "sideways": 0.2},
            "calibration_status": "calibrated",
            "prediction_set": [direction],
            "model_id": "model-sha256",
            "as_of": "2026-07-19T12:00:00+00:00",
            "horizon": 1,
        }
    }


@pytest.mark.parametrize(
    ("state", "code"),
    [
        ({}, "NEURAL_DECISION_MISSING"),
        ({"neural_decision": {"status": "abstain"}}, "NEURAL_ABSTAIN"),
        ({"neural_decision": {"status": "stale"}}, "NEURAL_STALE"),
        ({"neural_decision": {"status": "insufficient_data"}}, "NEURAL_INSUFFICIENT_DATA"),
    ],
)
def test_non_ready_neural_state_fails_closed(state: dict, code: str) -> None:
    result = evaluate_neural_execution_gate(state, "buy")
    assert result["allowed"] is False
    assert result["code"] == code


def test_uncalibrated_model_cannot_authorize_order() -> None:
    state = _ready()
    state["neural_decision"]["calibration_status"] = "not_calibrated"

    result = evaluate_neural_execution_gate(state, "buy")
    assert result["allowed"] is False
    assert result["code"] == "NEURAL_NOT_CALIBRATED"


@pytest.mark.parametrize(
    "probabilities",
    [
        {"up": 0.8, "down": 0.1},
        {"up": 0.8, "down": 0.3, "sideways": 0.2},
        {"up": float("nan"), "down": 0.5, "sideways": 0.5},
        {"up": -0.1, "down": 0.6, "sideways": 0.5},
    ],
)
def test_invalid_probability_simplex_fails_closed(probabilities: dict[str, float]) -> None:
    state = _ready()
    state["neural_decision"]["direction_prob"] = probabilities

    result = evaluate_neural_execution_gate(state, "buy")
    assert result["allowed"] is False
    assert result["code"] in {"NEURAL_SIMPLEX_INVALID", "NEURAL_SIMPLEX_MISSING"}


def test_model_direction_must_match_order_side() -> None:
    result = evaluate_neural_execution_gate(_ready("DOWN"), "buy")
    assert result["allowed"] is False
    assert result["code"] == "NEURAL_DIRECTION_CONFLICT"


def test_ambiguous_conformal_prediction_set_blocks() -> None:
    state = _ready()
    state["neural_decision"]["prediction_set"] = ["UP", "SIDEWAYS"]

    result = evaluate_neural_execution_gate(state, "buy")
    assert result["allowed"] is False
    assert result["code"] == "NEURAL_PREDICTION_SET_AMBIGUOUS"


def test_missing_conformal_prediction_set_blocks() -> None:
    state = _ready()
    state["neural_decision"].pop("prediction_set")

    result = evaluate_neural_execution_gate(state, "buy")
    assert result["allowed"] is False
    assert result["code"] == "NEURAL_PREDICTION_SET_MISSING"


def test_ready_calibrated_directionally_aligned_model_can_pass() -> None:
    result = evaluate_neural_execution_gate(_ready(), "buy")
    assert result["allowed"] is True
    assert result["model_id"] == "model-sha256"
    assert result["selected_probability"] == pytest.approx(0.7)


@pytest.mark.asyncio
async def test_low_level_submit_blocks_when_neural_decision_is_missing(monkeypatch) -> None:
    from core.pipeline.nodes.tool_executor import _submit_paper_order

    monkeypatch.setenv("SUPEREZIO_ENABLE_PAPER_ORDER_SUBMIT", "1")
    result = await _submit_paper_order(
        {"ticket_allowed": True},
        {"ticker": "AAPL", "action": "buy", "qty": 1, "limit_price": 100.0},
    )
    assert result["submit_paper_order_error"] == (
        "neural_execution_gate:NEURAL_DECISION_MISSING"
    )
