"""Chronological, calibrated shadow research. Never authorizes a broker order.

Metrics describe overlapping labelled events, not a tradable portfolio or alpha.
The held-out set is evaluated once; no model/threshold search is performed here.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    log_loss,
    roc_auc_score,
)
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

FEATURES = ("ret_1", "ret_5", "ret_20", "vol_20", "volume_ratio_20", "range_pct")
THRESHOLD = 0.55


@dataclass(frozen=True)
class ExperimentConfig:
    horizon: int = 14
    stop_pct: float = 0.02
    profit_multiple: float = 2.5
    cost_bps: float = 50.0
    train_fraction: float = 0.6
    calibration_fraction: float = 0.2
    embargo_days: int = 1

    def __post_init__(self):
        if not isinstance(self.horizon, int) or isinstance(self.horizon, bool) or self.horizon < 1:
            raise ValueError("horizon must be a positive integer")
        if (
            not isinstance(self.embargo_days, int)
            or isinstance(self.embargo_days, bool)
            or self.embargo_days < 0
        ):
            raise ValueError("embargo_days must be a nonnegative integer")
        numbers = [
            self.stop_pct,
            self.profit_multiple,
            self.cost_bps,
            self.train_fraction,
            self.calibration_fraction,
        ]
        if not np.isfinite(numbers).all():
            raise ValueError("configuration must be finite")
        if not 0 < self.stop_pct < 1 or self.profit_multiple <= 0 or self.cost_bps < 0:
            raise ValueError("invalid barrier or cost configuration")
        if (
            self.train_fraction <= 0
            or self.calibration_fraction <= 0
            or self.train_fraction + self.calibration_fraction >= 1
        ):
            raise ValueError("partition fractions must be positive and leave test data")


def _digest(frame: pd.DataFrame) -> str:
    return hashlib.sha256(frame.to_csv(index=False).encode()).hexdigest()


def _partition_summary(frame: pd.DataFrame) -> dict:
    return {
        "rows": len(frame),
        "sha256": _digest(frame),
        "decision_start": str(frame.decision_time.min()) if len(frame) else None,
        "decision_end": str(frame.decision_time.max()) if len(frame) else None,
        "label_end_max": str(frame.label_end.max()) if len(frame) else None,
        "positives": int(frame.label.sum()) if len(frame) else 0,
    }


def _metrics(y: np.ndarray, p: np.ndarray, returns: np.ndarray) -> dict:
    selected = p >= THRESHOLD
    two_classes = len(np.unique(y)) == 2
    return {
        "brier": float(brier_score_loss(y, p)),
        "log_loss": float(log_loss(y, p, labels=[0, 1])),
        "average_precision": float(average_precision_score(y, p)) if two_classes else None,
        "roc_auc": float(roc_auc_score(y, p)) if two_classes else None,
        "ranking_metrics_unavailable_reason": None if two_classes else "single_class_test",
        "threshold": THRESHOLD,
        "selected_events": int(selected.sum()),
        "coverage": float(selected.mean()),
        "selected_precision": float(y[selected].mean()) if selected.any() else None,
        "selected_mean_net_return": float(returns[selected].mean()) if selected.any() else None,
    }


def evaluate_partitions(train, calibration, test, *, config=None, input_sha256=None):
    """Fit on train, calibrate on calibration, report held-out test only.

    Returns (report dict, prediction DataFrame). Empty/single-class fitting data
    returns insufficient_data with no predictions or invented probabilities.
    Invalid chronology/features raises ValueError instead of silently repairing.
    """
    config = config or ExperimentConfig()
    partitions = {"train": train.copy(), "calibration": calibration.copy(), "test": test.copy()}
    for name, frame in partitions.items():
        required = set(FEATURES) | {
            "decision_time",
            "entry_time",
            "label_end",
            "symbol",
            "label",
            "net_return",
        }
        if missing := required - set(frame.columns):
            raise ValueError(f"{name}: missing columns {sorted(missing)}")
        for col in ("decision_time", "entry_time", "label_end"):
            frame[col] = pd.to_datetime(frame[col], utc=True, errors="raise")
            if frame[col].isna().any():
                raise ValueError(f"{name}: missing {col}")
        if not frame.label.isin([0, 1]).all():
            raise ValueError(f"{name}: labels must be binary")
        if not np.isfinite(frame[list(FEATURES) + ["net_return"]].to_numpy(dtype=float)).all():
            raise ValueError(f"{name}: non-finite features or returns")
        if ((frame.entry_time <= frame.decision_time) | (frame.label_end < frame.entry_time)).any():
            raise ValueError(f"{name}: invalid event chronology")
        if frame.duplicated(["symbol", "decision_time"]).any():
            raise ValueError(f"{name}: duplicate events")
    train, calibration, test = partitions.values()
    for left, right in ((train, calibration), (calibration, test)):
        if len(left) and len(right):
            boundary = right.decision_time.min() - pd.Timedelta(days=config.embargo_days)
            if left.label_end.max() >= boundary:
                raise ValueError("partition label overlap or embargo violation")
    report = {
        "schema_version": 1,
        "research_only": True,
        "broker_approval": False,
        "alpha_claim": False,
        "evaluation_unit": "overlapping_events_not_portfolio_returns",
        "limitations": [
            "Event observations overlap and are not independent.",
            "No confidence interval or economic alpha claim is made.",
            "Fixed assumed costs are not observed spreads or executable quotes.",
            "OHLCV features alone do not establish news causality or meta-label a primary signal.",
        ],
        "config": asdict(config),
        "features": list(FEATURES),
        "estimator_choice": "Existing sklearn histogram boosting avoids a new dependency; fixed configuration, no held-out tuning.",
        "input_sha256": input_sha256,
        "partitions": {name: _partition_summary(frame) for name, frame in partitions.items()},
        "versions": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "sklearn": sklearn.__version__,
        },
        "model_config": {
            "boosted": {
                "max_iter": 100,
                "max_leaf_nodes": 7,
                "l2_regularization": 1,
                "random_state": 42,
                "early_stopping": False,
            },
            "logistic": {"C": 1.0, "max_iter": 1000, "random_state": 42},
            "calibrator": "LogisticRegression(C=1,max_iter=1000,random_state=42) on raw probabilities",
        },
    }
    reasons = [f"empty_{name}" for name, frame in partitions.items() if frame.empty]
    reasons += [
        f"single_class_{name}"
        for name in ("train", "calibration")
        if partitions[name].label.nunique() < 2
    ]
    if reasons:
        report.update(status="insufficient_data", reasons=reasons, metrics={})
        return report, pd.DataFrame()
    x_train, y_train = train[list(FEATURES)], train.label.to_numpy()
    models = {
        "boosted": HistGradientBoostingClassifier(**report["model_config"]["boosted"]),
        "logistic": make_pipeline(
            StandardScaler(), LogisticRegression(C=1.0, max_iter=1000, random_state=42)
        ),
    }
    probabilities = {
        "train_prevalence": np.full(len(test), y_train.mean()),
        "calibration_prevalence": np.full(len(test), calibration.label.mean()),
    }
    for name, model in models.items():
        model.fit(x_train, y_train)
        cal_p = model.predict_proba(calibration[list(FEATURES)])[:, 1]
        calibrator = LogisticRegression(C=1.0, max_iter=1000, random_state=42)
        calibrator.fit(cal_p.reshape(-1, 1), calibration.label.to_numpy())
        raw_p = model.predict_proba(test[list(FEATURES)])[:, 1]
        probabilities[name] = calibrator.predict_proba(raw_p.reshape(-1, 1))[:, 1]
    predictions = test[
        ["symbol", "decision_time", "entry_time", "label_end", "label", "net_return"]
    ].copy()
    metrics = {}
    for name, p in probabilities.items():
        predictions[f"p_{name}"] = p
        predictions[f"selected_{name}"] = p >= THRESHOLD
        metrics[name] = _metrics(test.label.to_numpy(), p, test.net_return.to_numpy())
    report.update(status="evaluated", metrics=metrics)
    return report, predictions


def run_experiment(bars, *, config=None, input_sha256=None):
    """Build causal samples and chronological purged partitions from OHLCV bars."""
    from core.ml.event_dataset import build_samples, split_samples

    config = config or ExperimentConfig()
    samples = build_samples(
        bars,
        horizon=config.horizon,
        stop_pct=config.stop_pct,
        profit_multiple=config.profit_multiple,
        cost_bps=config.cost_bps,
    )
    partitions = split_samples(
        samples,
        train_fraction=config.train_fraction,
        calibration_fraction=config.calibration_fraction,
        embargo_days=config.embargo_days,
    )
    report, predictions = evaluate_partitions(*partitions, config=config, input_sha256=input_sha256)
    report["dataset_rows"] = len(bars)
    report["sample_rows"] = len(samples)
    report["purged_sample_rows"] = len(samples) - sum(len(part) for part in partitions)
    return report, predictions


def _atomic_write(path: Path, data: bytes):
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def write_artifacts(report, predictions, output):
    """Atomically replace each artifact; report written last records CSV digest.

    Readers must compare its digest; a crash between replacements is detectable.
    """
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    csv = predictions.to_csv(index=False).encode()
    report = dict(report, predictions_sha256=hashlib.sha256(csv).hexdigest())
    _atomic_write(output / "predictions.csv", csv)
    _atomic_write(output / "report.json", json.dumps(report, indent=2, allow_nan=False).encode())
