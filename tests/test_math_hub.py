from datetime import date, timedelta

import pytest

from core.math.math_hub import MathHub
from core.pipeline.prompts.math_prompt import format_math_context
from experts.crisis.quantum_expert import StationaryBlockBootstrap


def _sample_state():
    candles = []
    start = date(2026, 1, 1)
    for i in range(30):
        close = 10.0 + i * 0.2
        candles.append(
            {
                "open": close - 0.1,
                "high": close + 0.2,
                "low": close - 0.2,
                "close": close,
                "volume": 100000 + i * 1000,
                "date": (start + timedelta(days=i)).isoformat(),
            }
        )
    return {
        "run_id": "math-hub-test",
        "ticker": "AAPL",
        "data": {
            "ticker": "AAPL",
            "price": {"current": candles[-1]["close"]},
            "ohlcv": candles,
            "profile": {
                "free_cash_flow": 10_000_000,
                "shares_outstanding": 1_000_000,
            },
        },
    }


def test_math_hub_calculates_report_with_coverage():
    report = MathHub().calculate_all(_sample_state())

    assert report["ticker"] == "AAPL"
    assert report["coverage"]["total_modules"] == 14
    assert report["coverage"]["ok_modules"] >= 8
    assert report["modules"]["technical_indicators"]["status"] == "ok"
    assert report["modules"]["var_cvar"]["status"] == "ok"
    assert report["modules"]["return_bootstrap"]["status"] == "ok"
    assert report["modules"]["return_bootstrap"]["values"]["method"] == (
        "stationary_block_bootstrap"
    )
    assert report["modules"]["f51_unified"] == {
        "status": "skipped",
        "reason": "f51_verdict_not_available_at_pre_expert_math_stage",
        "phase": "pre_experts",
    }
    assert report["modules"]["price_series"]["values"]["start_date"] == "2026-01-01"
    assert report["modules"]["price_series"]["values"]["end_date"] == "2026-01-30"
    assert report["summary"]["latest_price"] == 15.8


def test_math_hub_preserves_iso_timestamp_for_penny_integration():
    candles = MathHub()._extract_candles(
        {
            "ohlcv": [
                {
                    "timestamp": "2026-07-19T14:30:00Z",
                    "open": 2.0,
                    "high": 2.1,
                    "low": 1.9,
                    "close": 2.05,
                    "volume": 1_000_000,
                }
            ]
        }
    )

    assert candles[0]["date"] == "2026-07-19T14:30:00Z"


def test_math_hub_labels_f51_heuristic_as_decision_score_not_confidence():
    state = _sample_state()
    state["f51_verdict"] = {
        "decision_score": 0.71,
        "confidence": 0.71,
        "score_type": "uncalibrated_decision_score",
        "calibration_status": "not_calibrated",
    }

    report = MathHub().calculate_all(state)

    assert report["summary"]["f51_decision_score"] == pytest.approx(0.71)
    assert report["numbers"]["f51_decision_score"] == pytest.approx(0.71)
    assert "f51_confidence" not in report["summary"]
    assert "f51_confidence" not in report["numbers"]


def test_math_hub_never_invents_dates_for_penny_backtest():
    state = _sample_state()
    for candle in state["data"]["ohlcv"]:
        candle.pop("date")

    report = MathHub().calculate_all(state)

    assert report["modules"]["penny_momentum"] == {
        "status": "insufficient_data",
        "reason": "candles_missing_iso_dates",
    }


def test_stationary_bootstrap_is_deterministic_and_uses_observed_returns():
    returns = [0.01, -0.02, 0.015, -0.005, 0.008, -0.012] * 5
    bootstrap = StationaryBlockBootstrap(n_scenarios=500, horizon=10)

    first = bootstrap.run_simulation(returns)
    second = bootstrap.run_simulation(returns)
    changed = bootstrap.run_simulation([value * 2 for value in returns])

    assert first == second
    assert first["input_source"] == "observed_simple_returns"
    assert first["block_length_distribution"] == "geometric"
    assert first["n_observations"] == len(returns)
    assert first["expected_cumulative_return"] != pytest.approx(
        changed["expected_cumulative_return"]
    )


def test_math_hub_renders_numeric_prompt():
    report = MathHub().calculate_all(_sample_state())
    prompt = MathHub.to_deepseek_prompt(report)

    assert "[MATH_CONTEXT]" in prompt
    assert "Ticker: AAPL" in prompt
    assert "Sharpe=" in prompt
    assert "VaR_95=" in prompt
    assert "[/MATH_CONTEXT]" in prompt
    assert len(prompt.splitlines()) <= 8


def test_format_math_context_is_compact_and_hides_crisis_details():
    prompt = format_math_context(
        {
            "ticker": "AAPL",
            "summary": {
                "latest_price": 215.30,
                "return_annualized": -0.011,
                "volatility_annualized": 0.029,
                "sharpe": -39.24,
                "max_drawdown": -0.039,
                "var_95": -0.0031,
                "kelly_fraction": None,
                "crisis_score": 0.2,
            },
            "modules": {
                "technical_indicators": {
                    "status": "ok",
                    "values": {"vwap": 210.956, "rsi14": None, "macd": None},
                },
                "crisis_aggregate": {
                    "status": "ok",
                    "values": {
                        "regime": "normal",
                        "aggregate_score": 0.2,
                        "model_scores": [{"name": "hidden"}],
                    },
                },
            },
        }
    )

    lines = prompt.splitlines()
    assert lines[0] == "[MATH_CONTEXT]"
    assert lines[-1] == "[/MATH_CONTEXT]"
    assert len(lines) <= 8
    assert "Price: $215.30" in prompt
    assert "annualized=-1.1%" in prompt
    assert "volatility=2.9%" in prompt
    assert "VaR_95=-$0.67" in prompt
    assert "Kelly=N/A" in prompt
    assert "regime=NORMAL | score=20/100 (low risk)" in prompt
    assert "VWAP=$210.96" in prompt
    assert "model_scores" not in prompt
    assert "{" not in prompt


def test_dcf_reads_fundamentals_when_profile_missing():
    state = _sample_state()
    state["data"].pop("profile")
    state["data"]["fundamentals"] = {
        "free_cash_flow": 12_000_000,
        "shares_outstanding": 2_000_000,
    }
    report = MathHub().calculate_all(state)
    assert report["modules"]["dcf_proxy"]["status"] == "ok"
    assert report["modules"]["dcf_proxy"]["values"]["dcf_value_per_share"]


def test_crisis_uses_candle_dates_instead_of_skipping():
    report = MathHub().calculate_all(_sample_state())
    status = report["modules"]["crisis_aggregate"]["status"]
    assert status in {"ok", "insufficient_data"}
    if status == "insufficient_data":
        values = report["modules"]["crisis_aggregate"].get("values") or {}
        assert values.get("models_run", 0) >= 1
