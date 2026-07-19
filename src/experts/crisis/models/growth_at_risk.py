"""Growth-at-Risk through exact linear quantile regression and rolling validation."""

from __future__ import annotations

import math

import numpy as np
from scipy.optimize import linprog

from ..contracts.schemas import CrisisInput, SensorResult
from . import BaseCrisisModel


def _pinball_loss(y_true: np.ndarray, y_pred: np.ndarray, quantile: float) -> float:
    residual = np.asarray(y_true, dtype=float) - np.asarray(y_pred, dtype=float)
    return float(np.mean(np.maximum(quantile * residual, (quantile - 1.0) * residual)))


def _quantile_regression(X: np.ndarray, y: np.ndarray, q: float = 0.05) -> np.ndarray:
    """Solve linear quantile regression exactly as a pinball-loss linear program."""
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float)
    if X.ndim != 2 or y.ndim != 1 or len(X) != len(y) or len(y) == 0:
        raise ValueError("X and y have incompatible quantile-regression shapes")
    if not 0.0 < q < 1.0 or not np.isfinite(X).all() or not np.isfinite(y).all():
        raise ValueError("quantile regression requires finite data and 0 < q < 1")

    n_samples, n_features = X.shape
    objective = np.r_[np.zeros(n_features), np.full(n_samples, q), np.full(n_samples, 1.0 - q)]
    # y - X beta = positive_residual - negative_residual
    equality = np.column_stack([X, np.eye(n_samples), -np.eye(n_samples)])
    bounds = [(None, None)] * n_features + [(0.0, None)] * (2 * n_samples)
    result = linprog(
        objective,
        A_eq=equality,
        b_eq=y,
        bounds=bounds,
        method="highs",
    )
    if not result.success or result.x is None:
        raise ValueError(f"quantile regression failed: {result.message}")
    return np.asarray(result.x[:n_features], dtype=float)


def _standardized_design(
    features: np.ndarray,
    mean: np.ndarray | None = None,
    scale: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if mean is None:
        mean = features.mean(axis=0)
    if scale is None:
        scale = features.std(axis=0)
    scale = np.where(scale > 1e-12, scale, 1.0)
    design = np.column_stack([np.ones(len(features)), (features - mean) / scale])
    return design, mean, scale


class GrowthAtRiskModel:
    QUANTILE = 0.05
    MIN_PAIRS = 20
    MIN_ROLLING_FOLDS = 8

    def evaluate(self, input_data: CrisisInput) -> SensorResult:
        observations = input_data.observations
        as_of = observations[-1].date if observations else None
        rows: list[list[float]] = []
        targets: list[float] = []
        for index in range(len(observations) - 1):
            current = observations[index]
            future = observations[index + 1]
            values = (
                current.credit_to_gdp,
                current.debt_service_ratio,
                current.house_price_index,
                future.gdp_growth_yoy,
            )
            if any(value is None for value in values):
                continue
            rows.append([float(value) for value in values[:3]])
            targets.append(float(values[3]))

        if len(rows) < self.MIN_PAIRS:
            return BaseCrisisModel._insufficient_data(
                self.__class__.__name__,
                f"Growth-at-Risk requires {self.MIN_PAIRS} complete predictor/target pairs; "
                f"found {len(rows)}.",
                horizon=f"1 {input_data.frequency} observation ahead",
                sample_size=len(rows),
                as_of=as_of,
            )

        latest = observations[-1]
        latest_values = (
            latest.credit_to_gdp,
            latest.debt_service_ratio,
            latest.house_price_index,
        )
        if any(value is None for value in latest_values):
            return BaseCrisisModel._insufficient_data(
                self.__class__.__name__,
                "Latest observation lacks one or more declared Growth-at-Risk predictors.",
                horizon=f"1 {input_data.frequency} observation ahead",
                sample_size=len(rows),
                as_of=as_of,
            )

        features = np.asarray(rows, dtype=float)
        raw_targets = np.asarray(targets, dtype=float)
        # Public macro feeds commonly encode 2% as either 0.02 or 2.0. Keep the
        # convention explicit and normalize only when the sample clearly uses percent points.
        target_scale = 0.01 if float(np.median(np.abs(raw_targets))) > 0.5 else 1.0
        y = raw_targets * target_scale

        rolling_start = max(12, len(y) // 2)
        rolling_predictions: list[float] = []
        rolling_targets: list[float] = []
        baseline_predictions: list[float] = []
        for test_index in range(rolling_start, len(y)):
            train_features = features[:test_index]
            train_y = y[:test_index]
            design, mean, scale = _standardized_design(train_features)
            try:
                beta = _quantile_regression(design, train_y, self.QUANTILE)
            except ValueError:
                continue
            test_design, _, _ = _standardized_design(
                features[test_index : test_index + 1], mean, scale
            )
            rolling_predictions.append(float(test_design[0] @ beta))
            rolling_targets.append(float(y[test_index]))
            baseline_predictions.append(
                float(np.quantile(train_y, self.QUANTILE, method="inverted_cdf"))
            )

        if len(rolling_predictions) < self.MIN_ROLLING_FOLDS:
            return BaseCrisisModel._insufficient_data(
                self.__class__.__name__,
                "Growth-at-Risk rolling validation produced too few valid folds.",
                horizon=f"1 {input_data.frequency} observation ahead",
                sample_size=len(rows),
                as_of=as_of,
            )

        rolling_y = np.asarray(rolling_targets)
        model_pinball = _pinball_loss(rolling_y, np.asarray(rolling_predictions), self.QUANTILE)
        baseline_pinball = _pinball_loss(rolling_y, np.asarray(baseline_predictions), self.QUANTILE)
        if baseline_pinball <= 1e-12:
            skill = 0.0
        else:
            skill = 1.0 - model_pinball / baseline_pinball

        full_design, feature_mean, feature_scale = _standardized_design(features)
        try:
            beta = _quantile_regression(full_design, y, self.QUANTILE)
        except ValueError as exc:
            return BaseCrisisModel._insufficient_data(
                self.__class__.__name__,
                str(exc),
                horizon=f"1 {input_data.frequency} observation ahead",
                sample_size=len(rows),
                as_of=as_of,
            )
        latest_design, _, _ = _standardized_design(
            np.asarray([[float(value) for value in latest_values]]),
            feature_mean,
            feature_scale,
        )
        forecast = float(latest_design[0] @ beta)
        if not math.isfinite(forecast):
            return BaseCrisisModel._insufficient_data(
                self.__class__.__name__,
                "Growth-at-Risk forecast is non-finite.",
                horizon=f"1 {input_data.frequency} observation ahead",
                sample_size=len(rows),
                as_of=as_of,
            )

        score = min(1.0, max(0.0, -forecast / 0.05))
        fold_support = min(1.0, len(rolling_predictions) / 24.0)
        confidence = min(0.90, 0.20 + 0.35 * fold_support + 0.35 * max(0.0, skill))
        if skill < 0.0:
            confidence *= max(0.25, 1.0 + skill)

        return BaseCrisisModel._result(
            sensor_name=self.__class__.__name__,
            score=score,
            confidence=confidence,
            explanation=(
                f"One-step {self.QUANTILE:.0%} Growth-at-Risk forecast is {forecast:.2%}; "
                f"rolling pinball skill versus historical quantile is {skill:.1%}."
            ),
            method_kind="econometric_model",
            horizon=f"1 {input_data.frequency} observation ahead",
            sample_size=len(rows),
            as_of=as_of,
            calibration_status="rolling_validated",
            details={
                "quantile": self.QUANTILE,
                "predicted_gdp_growth": round(forecast, 8),
                "rolling_folds": len(rolling_predictions),
                "pinball_loss": round(model_pinball, 8),
                "baseline_pinball_loss": round(baseline_pinball, 8),
                "pinball_skill": round(skill, 6),
                "target_input_scale": "percent_points" if target_scale == 0.01 else "fraction",
                "coefficients_standardized": beta.tolist(),
            },
        )
