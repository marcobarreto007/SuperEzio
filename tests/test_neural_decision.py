"""
Robust Unit Tests for NeuralDecisionExpert and its FastAPI Endpoint.
Contains 20 diverse synthetic test cases validating contracts, regimes,
calibrations, and endpoint integration.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from experts.neural_decision import NeuralDecisionExpert
from agent_server.main import app


# ── HELPER: Base Valid Payload Generator ──
def get_valid_payload() -> dict:
    return {
        "symbol": "BTCUSDT",
        "timeframe": "1h",
        "features": {
            "return_1": 0.0021,
            "return_5": -0.011,
            "rsi_14": 42.5,
            "atr_pct": 0.018,
            "volume_zscore": 2.4,
            "price_vs_ema_21": -0.006,
            "trend_slope": -0.12,
            "volatility_regime": "high",
            "liquidity_sweep": True,
        },
        "context": {
            "macro_risk": "neutral",
            "news_sentiment": "neutral",
            "fraud_risk": 0.12,
            "veracity_score": 0.77,
        },
    }


# ── TEST GROUP 1: Feature Contract Validation (10 Synthetic Cases) ──


def test_contract_valid_payload():
    """Case 1: Fully compliant valid payload must pass with no errors."""
    payload = get_valid_payload()
    expert = NeuralDecisionExpert()
    errors = expert.validate_input(
        payload["symbol"], payload["timeframe"], payload["features"], payload["context"]
    )
    assert len(errors) == 0, f"Expected 0 errors, got: {errors}"


def test_contract_missing_symbol():
    """Case 2: Missing or invalid symbol."""
    payload = get_valid_payload()
    expert = NeuralDecisionExpert()
    errors = expert.validate_input(
        "", payload["timeframe"], payload["features"], payload["context"]
    )
    assert "symbol" in "".join(errors).lower()


def test_contract_missing_timeframe():
    """Case 3: Missing or invalid timeframe."""
    payload = get_valid_payload()
    expert = NeuralDecisionExpert()
    errors = expert.validate_input(payload["symbol"], "", payload["features"], payload["context"])
    assert "timeframe" in "".join(errors).lower()


def test_contract_missing_features_dict():
    """Case 4: Non-dict features object."""
    payload = get_valid_payload()
    expert = NeuralDecisionExpert()
    errors = expert.validate_input(
        payload["symbol"], payload["timeframe"], "not-a-dict", payload["context"]
    )
    assert "features" in "".join(errors).lower()


def test_contract_missing_required_feature():
    """Case 5: Missing a specific mandatory feature (rsi_14)."""
    payload = get_valid_payload()
    payload["features"].pop("rsi_14")
    expert = NeuralDecisionExpert()
    errors = expert.validate_input(
        payload["symbol"], payload["timeframe"], payload["features"], payload["context"]
    )
    assert any("rsi_14" in err for err in errors)


def test_contract_wrong_feature_type():
    """Case 6: Feature rsi_14 with invalid string type (should be float)."""
    payload = get_valid_payload()
    payload["features"]["rsi_14"] = "high"
    expert = NeuralDecisionExpert()
    errors = expert.validate_input(
        payload["symbol"], payload["timeframe"], payload["features"], payload["context"]
    )
    assert any(
        "rsi_14" in err and "type" in err.lower() or "must be float/int" in err for err in errors
    )


def test_contract_feature_out_of_bounds():
    """Case 7: Feature return_1 exceeding bounds (> 1.0)."""
    payload = get_valid_payload()
    payload["features"]["return_1"] = 5.0
    expert = NeuralDecisionExpert()
    errors = expert.validate_input(
        payload["symbol"], payload["timeframe"], payload["features"], payload["context"]
    )
    assert any("return_1" in err and "above maximum" in err for err in errors)


def test_contract_invalid_enum_feature():
    """Case 8: Volatility regime string not in enum options."""
    payload = get_valid_payload()
    payload["features"]["volatility_regime"] = "super-hyper-crazy"
    expert = NeuralDecisionExpert()
    errors = expert.validate_input(
        payload["symbol"], payload["timeframe"], payload["features"], payload["context"]
    )
    assert any("volatility_regime" in err and "enum" in err for err in errors)


def test_contract_missing_required_context():
    """Case 9: Missing macro_risk context field."""
    payload = get_valid_payload()
    payload["context"].pop("macro_risk")
    expert = NeuralDecisionExpert()
    errors = expert.validate_input(
        payload["symbol"], payload["timeframe"], payload["features"], payload["context"]
    )
    assert any("macro_risk" in err for err in errors)


def test_contract_invalid_enum_context():
    """Case 10: news_sentiment not in allowed enum options."""
    payload = get_valid_payload()
    payload["context"]["news_sentiment"] = "sky-rocketing"
    expert = NeuralDecisionExpert()
    errors = expert.validate_input(
        payload["symbol"], payload["timeframe"], payload["features"], payload["context"]
    )
    assert any("news_sentiment" in err and "enum" in err for err in errors)


# ── TEST GROUP 2: Expert Predictions & Calibrations (5 Synthetic Cases) ──


def test_predict_trend_real():
    """Case 11: Real trend setup must trigger alerta_forte recommendation and low uncertainty."""
    payload = get_valid_payload()
    payload["features"]["rsi_14"] = 72.0
    payload["features"]["volume_zscore"] = 2.5
    payload["features"]["trend_slope"] = 0.25
    payload["features"]["volatility_regime"] = "normal"
    payload["context"]["fraud_risk"] = 0.05
    payload["context"]["veracity_score"] = 0.95

    expert = NeuralDecisionExpert()
    res = expert.predict(
        payload["symbol"], payload["timeframe"], payload["features"], payload["context"]
    )
    assert res["regime"] == "trend_real"
    assert res["recommendation"] == "alerta_forte"
    assert res["veto"] is False
    assert res["uncertainty"] < 0.40


def test_predict_pump_artificial_veto():
    """Case 12: High fraud risk must trigger veto_block and extreme uncertainty/drawdown risk."""
    payload = get_valid_payload()
    payload["context"]["fraud_risk"] = 0.85
    payload["context"]["veracity_score"] = 0.90

    expert = NeuralDecisionExpert()
    res = expert.predict(
        payload["symbol"], payload["timeframe"], payload["features"], payload["context"]
    )
    assert res["regime"] == "pump_artificial"
    assert res["recommendation"] == "veto_block"
    assert res["veto"] is True
    assert res["uncertainty"] > 0.50
    assert res["drawdown_risk"] >= 0.85


def test_predict_veracity_gap_veto():
    """Case 13: Low veracity score triggers uncertainty expansion and safety veto."""
    payload = get_valid_payload()
    payload["context"]["veracity_score"] = 0.35  # massive data veracity mismatch!
    payload["context"]["fraud_risk"] = 0.10

    expert = NeuralDecisionExpert()
    res = expert.predict(
        payload["symbol"], payload["timeframe"], payload["features"], payload["context"]
    )
    assert res["veto"] is True
    assert res["recommendation"] == "veto_block"
    assert res["uncertainty"] > 0.40  # uncertainty expands to protect the user


def test_predict_liquidity_hunt():
    """Case 14: Extreme volume spikes and return changes trigger liquidity_hunt regime."""
    payload = get_valid_payload()
    payload["features"]["volume_zscore"] = 4.5
    payload["features"]["return_1"] = 0.08
    payload["context"]["fraud_risk"] = 0.10
    payload["context"]["veracity_score"] = 0.90

    expert = NeuralDecisionExpert()
    res = expert.predict(
        payload["symbol"], payload["timeframe"], payload["features"], payload["context"]
    )
    assert res["regime"] == "liquidity_hunt"
    assert res["drawdown_risk"] >= 0.70


def test_predict_no_edge():
    """Case 15: Neutral features result in no_edge regime and observe recommendation."""
    payload = get_valid_payload()
    payload["features"]["trend_slope"] = 0.01
    payload["features"]["volume_zscore"] = 0.5
    payload["features"]["volatility_regime"] = "normal"
    payload["context"]["fraud_risk"] = 0.05
    payload["context"]["veracity_score"] = 0.95

    expert = NeuralDecisionExpert()
    res = expert.predict(
        payload["symbol"], payload["timeframe"], payload["features"], payload["context"]
    )
    assert res["regime"] == "no_edge"
    assert res["recommendation"] == "observar"
    assert res["veto"] is False


# ── TEST GROUP 3: FastAPI Endpoint Integration (5 Synthetic Cases) ──


def test_api_endpoint_success():
    """Case 16: Sending a valid payload to the endpoint returns 200 with structured decision."""
    client = TestClient(app)
    payload = get_valid_payload()
    response = client.post("/experts/neural-decision/predict", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["expert"] == "NeuralDecisionExpert"
    assert "direction_prob" in data
    assert "uncertainty" in data
    assert "recommendation" in data


def test_api_endpoint_missing_features():
    """Case 17: Sending payload with missing features returns 400 Bad Request with details."""
    client = TestClient(app)
    payload = get_valid_payload()
    payload["features"].pop("rsi_14")

    response = client.post("/experts/neural-decision/predict", json=payload)
    assert response.status_code == 400
    data = response.json()
    assert "error" in data["detail"]
    assert any("rsi_14" in err for err in data["detail"]["validation_errors"])


def test_api_endpoint_wrong_type():
    """Case 18: Sending payload with wrong type returns 400 Bad Request."""
    client = TestClient(app)
    payload = get_valid_payload()
    payload["features"]["rsi_14"] = "overbought"

    response = client.post("/experts/neural-decision/predict", json=payload)
    assert response.status_code == 400
    data = response.json()
    assert "validation_errors" in data["detail"]


def test_api_endpoint_out_of_bounds():
    """Case 19: Sending payload with out-of-bounds values returns 400."""
    client = TestClient(app)
    payload = get_valid_payload()
    payload["features"]["return_1"] = -2.5

    response = client.post("/experts/neural-decision/predict", json=payload)
    assert response.status_code == 400
    data = response.json()
    assert any("return_1" in err for err in data["detail"]["validation_errors"])


def test_api_endpoint_empty_payload():
    """Case 20: Sending empty payload returns 400 Bad Request."""
    client = TestClient(app)
    response = client.post("/experts/neural-decision/predict", json={})
    assert response.status_code == 400
    data = response.json()
    assert "symbol" in "".join(data["detail"]["validation_errors"]).lower()
