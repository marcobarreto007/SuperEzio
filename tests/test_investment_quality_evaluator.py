from __future__ import annotations

import numpy as np
import pytest

from scripts.evaluate_investment_quality import (
    DEFAULT_UNIVERSE,
    _strategy_metrics,
    overall_verdict,
)


def _evaluated(
    ticker: str,
    asset_class: str,
    *,
    brier_skill: float = 0.1,
    accuracy_lift: float = 0.05,
    excess_return: float = 0.03,
) -> dict:
    return {
        "ticker": ticker,
        "asset_class": asset_class,
        "status": "evaluated",
        "probabilistic": {
            "brier_skill": brier_skill,
            "balanced_accuracy_lift": accuracy_lift,
        },
        "investment": {"excess_total_return": excess_return},
    }


def test_default_universe_is_diversified_and_has_no_privileged_apple_fixture() -> None:
    symbols = {case.ticker for case in DEFAULT_UNIVERSE}
    classes = {case.asset_class for case in DEFAULT_UNIVERSE}
    assert "AAPL" not in symbols
    assert len(symbols) >= 8
    assert len(classes) >= 6


def test_strategy_uses_future_returns_and_charges_turnover() -> None:
    returns = np.array([0.05, -0.02, 0.03], dtype=np.float64)
    probabilities = np.array(
        [
            [0.1, 0.1, 0.8],
            [0.8, 0.1, 0.1],
            [0.1, 0.1, 0.8],
        ],
        dtype=np.float64,
    )
    result = _strategy_metrics(returns, probabilities, horizon_bars=1, turnover_cost=0.01)
    expected_log_return = (0.05 - 0.01) + (0.0 - 0.01) + (0.03 - 0.01)
    assert result["strategy"]["total_return"] == pytest.approx(np.exp(expected_log_return) - 1)
    assert result["invested_fraction"] == pytest.approx(2 / 3)


def test_abstentions_cannot_be_reported_as_investment_skill() -> None:
    report = overall_verdict(
        [
            {"ticker": "SPY", "asset_class": "equity", "status": "abstain"},
            {"ticker": "TLT", "asset_class": "bond", "status": "abstain"},
        ],
        data_cases=2,
    )
    assert report["verdict"] == "INVESTMENT_SKILL_NOT_PROVEN"
    assert report["evaluated_cases"] == 0
    assert report["qualification_rate"] == 0.0


def test_all_fixed_exploratory_gates_are_required_for_positive_verdict() -> None:
    rows = [
        _evaluated("SPY", "equity"),
        _evaluated("QQQ", "growth"),
        _evaluated("TLT", "bond"),
        _evaluated("GLD", "gold"),
        _evaluated("RY.TO", "canada"),
        _evaluated("BTC-USD", "crypto"),
    ]
    report = overall_verdict(rows, data_cases=12)
    assert report["verdict"] == "EVIDENCE_OF_MULTI_ASSET_SKILL"
    for index in range(4):
        rows[index] = _evaluated(
            rows[index]["ticker"], rows[index]["asset_class"], excess_return=-1.0
        )
    failed = overall_verdict(rows, data_cases=12)
    assert failed["verdict"] == "INVESTMENT_SKILL_NOT_PROVEN"
