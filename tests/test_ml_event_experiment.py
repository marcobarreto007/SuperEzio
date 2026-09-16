"""Synthetic fixtures test plumbing and isolation only, not financial skill."""

import hashlib
import json

import numpy as np
import pandas as pd
import pytest

from core.ml.event_experiment import (
    FEATURES,
    ExperimentConfig,
    evaluate_partitions,
    write_artifacts,
)


def synthetic_partition(start, n=60):
    dates = pd.date_range(start, periods=n, tz="UTC")
    rng = np.random.default_rng(42)
    frame = pd.DataFrame(rng.normal(size=(n, len(FEATURES))), columns=FEATURES)
    frame["symbol"] = "SYNTHETIC"
    frame["decision_time"] = dates
    frame["entry_time"] = dates + pd.Timedelta(days=1)
    frame["label_end"] = dates + pd.Timedelta(days=2)
    frame["label"] = np.arange(n) % 2
    frame["net_return"] = np.where(frame.label, 0.03, -0.025)
    return frame


def parts():
    return (
        synthetic_partition("2020-01-01"),
        synthetic_partition("2021-01-01"),
        synthetic_partition("2022-01-01"),
    )


def test_synthetic_evaluation_is_deterministic_and_never_authorizes(tmp_path):
    report, predictions = evaluate_partitions(*parts())
    report2, predictions2 = evaluate_partitions(*parts())
    assert report == report2
    pd.testing.assert_frame_equal(predictions, predictions2)
    assert report["research_only"] and not report["broker_approval"]
    assert not report["alpha_claim"]
    assert report["evaluation_unit"] == "overlapping_events_not_portfolio_returns"
    assert set(report["metrics"]) == {
        "boosted",
        "logistic",
        "train_prevalence",
        "calibration_prevalence",
    }
    assert report["metrics"]["train_prevalence"]["selected_events"] == 0
    assert report["metrics"]["train_prevalence"]["selected_precision"] is None
    write_artifacts(report, predictions, tmp_path)
    saved = json.loads((tmp_path / "report.json").read_text())
    assert (
        saved["predictions_sha256"]
        == hashlib.sha256((tmp_path / "predictions.csv").read_bytes()).hexdigest()
    )


def test_test_labels_do_not_change_predictions():
    train, calibration, test = parts()
    _, initial = evaluate_partitions(train, calibration, test)
    test["label"] = 1 - test.label
    test["net_return"] = -999
    _, changed = evaluate_partitions(train, calibration, test)
    pd.testing.assert_frame_equal(initial.filter(like="p_"), changed.filter(like="p_"))


def test_single_class_training_fails_closed():
    train, calibration, test = parts()
    train["label"] = 1
    report, predictions = evaluate_partitions(train, calibration, test)
    assert report["status"] == "insufficient_data"
    assert "single_class_train" in report["reasons"]
    assert not report["metrics"] and predictions.empty


def test_empty_data_has_no_fabricated_metrics():
    train, calibration, test = parts()
    report, predictions = evaluate_partitions(train.iloc[:0], calibration, test)
    assert report["status"] == "insufficient_data"
    assert not report["metrics"] and predictions.empty


def test_purge_violation_is_rejected():
    train, calibration, test = parts()
    train.loc[0, "label_end"] = calibration.decision_time.min()
    with pytest.raises(ValueError, match="overlap or embargo"):
        evaluate_partitions(train, calibration, test)


def test_nonfinite_feature_is_rejected():
    train, calibration, test = parts()
    test.loc[0, FEATURES[0]] = np.inf
    with pytest.raises(ValueError, match="non-finite"):
        evaluate_partitions(train, calibration, test)


def test_single_class_test_has_no_ranking_metrics():
    train, calibration, test = parts()
    test["label"] = 0
    report, _ = evaluate_partitions(train, calibration, test)
    for metrics in report["metrics"].values():
        assert metrics["roc_auc"] is None
        assert metrics["average_precision"] is None
        assert metrics["ranking_metrics_unavailable_reason"] == "single_class_test"


@pytest.mark.parametrize("value", [-1, np.nan, np.inf, 1.5])
def test_invalid_embargo_rejected(value):
    with pytest.raises(ValueError, match="embargo_days"):
        ExperimentConfig(embargo_days=value)
