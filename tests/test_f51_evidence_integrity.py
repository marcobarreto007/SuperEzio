"""Regression tests for evidence integrity in the operational F51 adapter."""

from __future__ import annotations

import pytest

from core.f51_adapter.adapter import F51HubAdapter
from f51.graph import F51Engine


def test_empty_trace_has_no_fabricated_market_observations() -> None:
    features = F51HubAdapter.extract_features({"ticker": "EMPTY"})

    assert features == {"missing_data_ratio": 1.0, "data_points": 0}


def test_rsi_does_not_fabricate_a_daily_return() -> None:
    features = F51HubAdapter.extract_features(
        {"technicals": {"price": 10.0, "rsi_14": 85.0, "volume": 1_000}}
    )

    assert features["price"] == 10.0
    assert features["rsi_14"] == 85.0
    assert "daily_return" not in features
    assert "avg_volume" not in features
    assert "volume_z_score" not in features


def test_candle_features_are_causal_observations() -> None:
    features = F51HubAdapter.extract_features(
        {
            "ohlcv": [
                {"close": 100.0, "volume": 100.0},
                {"close": 101.0, "volume": 110.0},
                {"close": 102.0, "volume": 120.0},
            ]
        }
    )

    assert features["price"] == 102.0
    assert features["daily_return"] == pytest.approx(102.0 / 101.0 - 1.0)
    assert features["avg_volume"] == 105.0
    assert features["volume_z_score"] == pytest.approx(2.1213203435596424)


def test_more_real_observations_reduce_missingness() -> None:
    empty = F51HubAdapter.extract_features({})
    observed = F51HubAdapter.extract_features(
        {
            "ohlcv": [
                {"close": 100.0, "volume": 100.0},
                {"close": 101.0, "volume": 110.0},
                {"close": 102.0, "volume": 120.0},
            ],
            "technicals": {"rsi_14": 55.0},
            "risk": {"annual_volatility": 0.25},
            "sentiment": {"sentiment_score": 0.0},
        }
    )

    assert observed["missing_data_ratio"] < empty["missing_data_ratio"]


def test_empty_trace_never_passes_and_score_is_not_probability() -> None:
    result = F51HubAdapter().run_on_trace({"ticker": "EMPTY"})

    assert result["passed"] is False
    assert result["evidence_status"] == "insufficient"
    assert result["score_type"] == "uncalibrated_decision_score"
    assert result["calibration_status"] == "not_calibrated"
    assert "NO_INDEPENDENT_CLAIMS" in result["reason_codes"]
    assert "INSUFFICIENT_MARKET_EVIDENCE" in result["reason_codes"]


def test_one_verified_claim_is_not_enough_for_operational_approval() -> None:
    result = F51HubAdapter().run_on_trace(
        {
            "ticker": "TEST",
            "ohlcv": [
                {"close": 100.0, "volume": 100.0},
                {"close": 101.0, "volume": 110.0},
                {"close": 102.0, "volume": 120.0},
            ],
            "technicals": {"rsi_14": 55.0},
            "claims": [{"field": "price", "value": 102.0, "source": "provider_a"}],
            "independent_ground_truth": {"price": 102.0},
        }
    )

    assert result["passed"] is False
    assert "INSUFFICIENT_INDEPENDENT_VERIFICATION" in result["reason_codes"]


def test_observed_features_cannot_verify_themselves() -> None:
    result = F51HubAdapter().run_on_trace(
        {
            "ticker": "TEST",
            "technicals": {"price": 42.0, "rsi_14": 60.0},
            "risk": {"annual_volatility": 0.2},
        }
    )

    assert result["passed"] is False
    assert result["veracity_explicit"]["verified"] == 0


def test_default_engine_fails_closed_without_veracity_evidence() -> None:
    result = F51Engine().run(
        {
            "features": {
                "price": 100.0,
                "rsi_14": 55.0,
                "annual_volatility": 0.2,
                "sharpe_ratio": 1.0,
                "var_95": -0.02,
                "sentiment_score": 0.0,
                "market_cap": 1_000_000_000.0,
            }
        },
        domain="trading",
    )

    assert result["passed"] is False
    assert result["reason_codes"] == ["VERACITY_NOT_ESTABLISHED"]
    assert result["score_type"] == "uncalibrated_decision_score"
