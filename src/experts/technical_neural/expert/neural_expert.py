"""Causal, calibrated three-class price-direction model.

The expert is deliberately fail-closed: a directional distribution is exposed only
after the model beats a train-climatology baseline on a fully out-of-sample test
window.  Missing, stale, ambiguous, or corrupt inputs produce ``ABSTAIN`` without
inventing a neutral probability.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import math
import os
import tempfile
import warnings
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, ClassVar

import numpy as np
from scipy.optimize import minimize_scalar
from sklearn.exceptions import ConvergenceWarning
from sklearn.metrics import balanced_accuracy_score, log_loss
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)

CLASS_NAMES = ("down", "sideways", "up")
CLASS_DECISIONS = ("DOWN", "SIDEWAYS", "UP")
ARTIFACT_VERSION = 3


class CandleValidationError(ValueError):
    """Raised when candle history cannot define one unambiguous time series."""


class ArtifactError(RuntimeError):
    """Raised when a persisted model is invalid or cannot be trusted."""


@dataclass(frozen=True)
class _PreparedData:
    timestamps: tuple[datetime, ...]
    features: np.ndarray
    forward_returns: np.ndarray
    latest_features: np.ndarray
    as_of: datetime
    input_hash: str


@dataclass(frozen=True)
class _Split:
    train: np.ndarray
    validation: np.ndarray
    calibration: np.ndarray
    test: np.ndarray


class TechnicalNeuralExpert:
    """Deterministic causal MLP with isolated calibration and OOS skill gate."""

    FEATURE_NAMES: ClassVar[tuple[str, ...]] = (
        "log_return_1",
        "log_return_3",
        "log_return_5",
        "log_range",
        "rolling_volatility_10",
        "close_vs_sma_10",
        "volume_zscore_20",
        "log_volume_change_1",
    )
    MIN_LABELLED_SAMPLES = 140
    MIN_WINDOW_SAMPLES = 12
    # Eight causal inputs do not justify the former 24x12 network, which failed
    # to converge on every member of the pre-registered real-market universe.
    # Keep capacity proportional to evidence and continue to fail closed on any
    # convergence warning or out-of-sample baseline miss.
    HIDDEN_LAYER_SIZES: ClassVar[tuple[int, ...]] = (8,)
    MODEL_ALPHA = 0.1
    MODEL_MAX_ITER = 1000

    def __init__(
        self,
        *,
        horizon_bars: int = 1,
        artifact_dir: str | Path | None = None,
        max_data_age: timedelta = timedelta(days=7),
        random_state: int = 42,
        conformal_alpha: float = 0.10,
    ) -> None:
        if not isinstance(horizon_bars, int) or horizon_bars < 1:
            raise ValueError("horizon_bars must be a positive integer")
        if not 0.0 < conformal_alpha < 1.0:
            raise ValueError("conformal_alpha must be between zero and one")
        self.horizon_bars = horizon_bars
        self.artifact_dir = Path(artifact_dir or "data/technical_neural_models")
        self.max_data_age = max_data_age
        self.random_state = random_state
        self.conformal_alpha = float(conformal_alpha)

    def evaluate(
        self,
        ticker: str,
        candles_data: list[dict[str, Any]],
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Train or reload a qualified model and infer at the latest candle close."""
        symbol = str(ticker or "").strip().upper()
        if not symbol:
            return self._closed("error", "INVALID_TICKER", ticker="")

        reference_time = self._as_utc(now or datetime.now(timezone.utc))
        try:
            prepared = self._prepare_with_horizon(candles_data)
        except CandleValidationError as exc:
            return self._closed("insufficient_data", str(exc), ticker=symbol)
        except Exception as exc:  # defensive boundary for untrusted provider payloads
            logger.exception("Candle preparation failed for %s", symbol)
            return self._closed(
                "error", "CANDLE_PREPARATION_FAILED", ticker=symbol, detail=str(exc)
            )

        if prepared.as_of > reference_time + timedelta(minutes=5):
            return self._closed(
                "error", "FUTURE_AS_OF", ticker=symbol, as_of=prepared.as_of.isoformat()
            )
        if reference_time - prepared.as_of > self.max_data_age:
            return self._closed(
                "stale", "STALE_CANDLES", ticker=symbol, as_of=prepared.as_of.isoformat()
            )

        try:
            artifact = self._load_artifact(
                symbol, prepared.as_of, prepared.input_hash, reference_time
            )
        except FileNotFoundError:
            artifact = None
        except ArtifactError as exc:
            logger.error("Untrusted technical-neural artifact for %s: %s", symbol, exc)
            return self._closed(
                "error",
                "ARTIFACT_INVALID",
                ticker=symbol,
                as_of=prepared.as_of.isoformat(),
                detail=str(exc),
            )

        if artifact is None:
            result, artifact = self._fit_and_qualify(symbol, prepared)
            if artifact is None:
                return result
            try:
                self._save_artifact(symbol, artifact)
            except OSError as exc:
                logger.exception("Cannot persist technical-neural model for %s", symbol)
                return self._closed(
                    "error",
                    "ARTIFACT_PERSISTENCE_FAILED",
                    ticker=symbol,
                    as_of=prepared.as_of.isoformat(),
                    detail=str(exc),
                )
            loaded_from_artifact = False
        else:
            loaded_from_artifact = True

        try:
            probabilities = self._predict_artifact(artifact, prepared.latest_features)
        except (ArtifactError, ValueError, FloatingPointError) as exc:
            return self._closed(
                "error",
                "MODEL_INFERENCE_FAILED",
                ticker=symbol,
                as_of=prepared.as_of.isoformat(),
                detail=str(exc),
            )

        decision_index = int(np.argmax(probabilities))
        conformal_threshold = float(artifact["conformal_threshold"])
        prediction_set = [
            CLASS_DECISIONS[index]
            for index, probability in enumerate(probabilities)
            if 1.0 - float(probability) <= conformal_threshold
        ]
        entropy = float(-np.sum(probabilities * np.log(np.clip(probabilities, 1e-15, 1.0))))
        confidence = 1.0 - entropy / math.log(3.0)
        class_returns = np.asarray(artifact["class_return_means"], dtype=np.float64)
        expected_return = float(probabilities @ class_returns)
        metrics = artifact["metrics"]

        return {
            "expert": "TechnicalNeuralExpert",
            "source": "technical_neural_causal",
            "ticker": symbol,
            "status": "ready",
            "decision": CLASS_DECISIONS[decision_index],
            "direction_prob": {
                name: float(probabilities[index]) for index, name in enumerate(CLASS_NAMES)
            },
            "calibration_status": "calibrated",
            "prediction_set": prediction_set,
            "conformal": {
                "method": "split_conformal_inverse_probability",
                "alpha": self.conformal_alpha,
                "marginal_coverage_target": 1.0 - self.conformal_alpha,
                "threshold": conformal_threshold,
                "calibration_samples": int(artifact["conformal_calibration_samples"]),
            },
            "skill_status": "qualified",
            "baseline_comparison": metrics,
            "confidence": confidence,
            "uncertainty": 1.0 - confidence,
            "expected_return": expected_return,
            "model_id": artifact["model_id"],
            "model_version": ARTIFACT_VERSION,
            "artifact_hash": artifact["artifact_hash"],
            "as_of": prepared.as_of.isoformat(),
            "horizon": {"bars": self.horizon_bars},
            "reason_codes": [],
            "loaded_from_artifact": loaded_from_artifact,
        }

    def _fit_and_qualify(
        self, symbol: str, prepared: _PreparedData
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        n_samples = len(prepared.forward_returns)
        if n_samples < self.MIN_LABELLED_SAMPLES:
            return (
                self._closed(
                    "insufficient_data",
                    "TOO_FEW_LABELLED_SAMPLES",
                    ticker=symbol,
                    as_of=prepared.as_of.isoformat(),
                    detail=f"need {self.MIN_LABELLED_SAMPLES}, got {n_samples}",
                ),
                None,
            )

        split = self._chronological_split(n_samples)
        train_returns = prepared.forward_returns[split.train]
        movement_threshold = max(1e-5, float(np.std(train_returns, ddof=1)) * 0.25)
        labels = np.where(
            prepared.forward_returns > movement_threshold,
            2,
            np.where(prepared.forward_returns < -movement_threshold, 0, 1),
        ).astype(np.int64)

        train_labels = labels[split.train]
        split_labels = (
            train_labels,
            labels[split.validation],
            labels[split.calibration],
            labels[split.test],
        )
        if any(set(np.unique(window)) != {0, 1, 2} for window in split_labels):
            return (
                self._closed(
                    "abstain",
                    "SPLIT_CLASSES_INCOMPLETE",
                    ticker=symbol,
                    as_of=prepared.as_of.isoformat(),
                ),
                None,
            )

        scaler = StandardScaler()
        train_x = scaler.fit_transform(prepared.features[split.train])
        validation_x = scaler.transform(prepared.features[split.validation])
        calibration_x = scaler.transform(prepared.features[split.calibration])
        test_x = scaler.transform(prepared.features[split.test])

        model = MLPClassifier(
            hidden_layer_sizes=self.HIDDEN_LAYER_SIZES,
            activation="relu",
            solver="lbfgs",
            alpha=self.MODEL_ALPHA,
            max_iter=self.MODEL_MAX_ITER,
            random_state=self.random_state,
            shuffle=False,
        )
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter("always", ConvergenceWarning)
            model.fit(train_x, train_labels)
        if any(issubclass(item.category, ConvergenceWarning) for item in captured):
            return (
                self._closed(
                    "abstain",
                    "MODEL_DID_NOT_CONVERGE",
                    ticker=symbol,
                    as_of=prepared.as_of.isoformat(),
                ),
                None,
            )
        if tuple(int(item) for item in model.classes_) != (0, 1, 2):
            return (
                self._closed(
                    "abstain",
                    "MODEL_CLASSES_INCOMPLETE",
                    ticker=symbol,
                    as_of=prepared.as_of.isoformat(),
                ),
                None,
            )

        train_counts = np.bincount(train_labels, minlength=3).astype(np.float64)
        climatology = (train_counts + 1.0) / (float(train_counts.sum()) + 3.0)

        validation_prob = self._manual_predict(model.coefs_, model.intercepts_, validation_x)
        validation_metrics = self._metrics(labels[split.validation], validation_prob, climatology)
        if not self._finite_metrics(validation_metrics):
            return (
                self._closed(
                    "abstain",
                    "UNSTABLE_VALIDATION_METRICS",
                    ticker=symbol,
                    as_of=prepared.as_of.isoformat(),
                ),
                None,
            )
        validation_model = validation_metrics["model"]
        validation_baseline = validation_metrics["baseline"]
        if (
            validation_model["brier"] >= validation_baseline["brier"]
            or validation_model["log_loss"] >= validation_baseline["log_loss"]
            or validation_model["balanced_accuracy"] <= validation_baseline["balanced_accuracy"]
        ):
            return (
                self._closed(
                    "abstain",
                    "VALIDATION_BASELINE_NOT_BEATEN",
                    ticker=symbol,
                    as_of=prepared.as_of.isoformat(),
                    baseline_comparison={"validation": validation_metrics},
                ),
                None,
            )

        # Temperature is selected on the validation window.  The calibration
        # window remains untouched until split-conformal scores are computed.
        temperature = self._fit_temperature(validation_prob, labels[split.validation])
        if not math.isfinite(temperature) or not 0.05 <= temperature <= 20.0:
            return (
                self._closed(
                    "abstain",
                    "CALIBRATION_UNSTABLE",
                    ticker=symbol,
                    as_of=prepared.as_of.isoformat(),
                ),
                None,
            )

        calibration_raw_prob = self._manual_predict(model.coefs_, model.intercepts_, calibration_x)
        calibration_prob = self._temperature_scale(calibration_raw_prob, temperature)
        conformal_threshold = self._conformal_threshold(
            calibration_prob,
            labels[split.calibration],
            self.conformal_alpha,
        )

        test_raw_prob = self._manual_predict(model.coefs_, model.intercepts_, test_x)
        test_prob = self._temperature_scale(test_raw_prob, temperature)
        test_metrics = self._metrics(labels[split.test], test_prob, climatology)
        if not self._finite_metrics(test_metrics):
            return (
                self._closed(
                    "abstain",
                    "UNSTABLE_TEST_METRICS",
                    ticker=symbol,
                    as_of=prepared.as_of.isoformat(),
                ),
                None,
            )

        model_metrics = test_metrics["model"]
        baseline_metrics = test_metrics["baseline"]
        beats_baseline = (
            model_metrics["brier"] < baseline_metrics["brier"]
            and model_metrics["log_loss"] < baseline_metrics["log_loss"]
            and model_metrics["balanced_accuracy"] > baseline_metrics["balanced_accuracy"]
        )
        if not beats_baseline:
            return (
                self._closed(
                    "abstain",
                    "BASELINE_NOT_BEATEN",
                    ticker=symbol,
                    as_of=prepared.as_of.isoformat(),
                    baseline_comparison={
                        "validation": validation_metrics,
                        "test": test_metrics,
                    },
                ),
                None,
            )

        class_return_means = np.array(
            [
                float(np.mean(train_returns[train_labels == class_index]))
                for class_index in range(3)
            ],
            dtype=np.float64,
        )
        model_id = self._model_id(symbol, prepared.as_of, prepared.input_hash)
        artifact: dict[str, Any] = {
            "model_id": model_id,
            "ticker": symbol,
            "as_of": prepared.as_of.isoformat(),
            "horizon_bars": self.horizon_bars,
            "input_hash": prepared.input_hash,
            "movement_threshold": movement_threshold,
            "temperature": temperature,
            "conformal_alpha": self.conformal_alpha,
            "conformal_threshold": conformal_threshold,
            "conformal_calibration_samples": len(split.calibration),
            "feature_names": list(self.FEATURE_NAMES),
            "scaler_mean": np.asarray(scaler.mean_, dtype=np.float64),
            "scaler_scale": np.asarray(scaler.scale_, dtype=np.float64),
            "coefs": [np.asarray(item, dtype=np.float64) for item in model.coefs_],
            "intercepts": [np.asarray(item, dtype=np.float64) for item in model.intercepts_],
            "classes": np.asarray(model.classes_, dtype=np.int64),
            "climatology": climatology,
            "class_return_means": class_return_means,
            "metrics": {"validation": validation_metrics, "test": test_metrics},
        }
        artifact["artifact_hash"] = "pending"
        return ({"status": "ready"}, artifact)

    @classmethod
    def _prepare(cls, candles_data: list[dict[str, Any]]) -> _PreparedData:
        if not isinstance(candles_data, list) or not candles_data:
            raise CandleValidationError("NO_CANDLES")

        by_time: dict[datetime, tuple[float, float, float, float, float]] = {}
        for raw in candles_data:
            if not isinstance(raw, dict):
                raise CandleValidationError("INVALID_CANDLE_OBJECT")
            timestamp = cls._parse_timestamp(raw)
            try:
                open_price = float(raw["open"])
                high = float(raw["high"])
                low = float(raw["low"])
                close = float(raw["close"])
                volume = float(raw.get("volume", 0.0))
            except (KeyError, TypeError, ValueError) as exc:
                raise CandleValidationError("INVALID_CANDLE_VALUES") from exc
            values = np.array([open_price, high, low, close, volume], dtype=np.float64)
            if not np.all(np.isfinite(values)):
                raise CandleValidationError("NON_FINITE_CANDLE_VALUES")
            if min(open_price, high, low, close) <= 0 or volume < 0:
                raise CandleValidationError("NON_POSITIVE_PRICE_OR_NEGATIVE_VOLUME")
            upper = max(open_price, close, low)
            lower = min(open_price, close, high)
            high_invalid = high < upper and not math.isclose(
                high, upper, rel_tol=1e-12, abs_tol=1e-10
            )
            low_invalid = low > lower and not math.isclose(low, lower, rel_tol=1e-12, abs_tol=1e-10)
            if high_invalid or low_invalid:
                raise CandleValidationError("INCONSISTENT_OHLC")
            candle_tuple = (open_price, high, low, close, volume)
            previous = by_time.get(timestamp)
            if previous is not None and previous != candle_tuple:
                raise CandleValidationError("CONFLICTING_DUPLICATE_TIMESTAMP")
            by_time[timestamp] = candle_tuple

        ordered = sorted(by_time.items(), key=lambda item: item[0])
        if len(ordered) < 30:
            raise CandleValidationError("TOO_FEW_UNIQUE_CANDLES")
        timestamps = tuple(item[0] for item in ordered)
        matrix = np.asarray([item[1] for item in ordered], dtype=np.float64)
        closes = matrix[:, 3]
        highs = matrix[:, 1]
        lows = matrix[:, 2]
        volumes = matrix[:, 4]

        rows: list[list[float]] = []
        row_times: list[datetime] = []
        forward_returns: list[float] = []
        latest_features: np.ndarray | None = None
        latest_feature_time: datetime | None = None
        for index in range(20, len(ordered)):
            feature_row = cls._feature_row(closes, highs, lows, volumes, index)
            if not np.all(np.isfinite(feature_row)):
                continue
            latest_features = feature_row
            latest_feature_time = timestamps[index]
            future_index = index + 1
            if future_index >= len(ordered):
                continue
            rows.append(feature_row.tolist())
            row_times.append(timestamps[index])
            forward_returns.append(float(math.log(closes[future_index] / closes[index])))

        if latest_features is None or latest_feature_time != timestamps[-1]:
            raise CandleValidationError("LATEST_FEATURES_UNAVAILABLE")
        if len(rows) == 0:
            raise CandleValidationError("NO_LABELLED_FEATURES")
        return _PreparedData(
            timestamps=tuple(row_times),
            features=np.asarray(rows, dtype=np.float64),
            forward_returns=np.asarray(forward_returns, dtype=np.float64),
            latest_features=np.asarray(latest_features, dtype=np.float64),
            as_of=timestamps[-1],
            input_hash=cls._input_hash(timestamps, matrix),
        )

    def _prepare_with_horizon(self, candles_data: list[dict[str, Any]]) -> _PreparedData:
        """Compatibility hook retained for tests; use configured horizon for labels."""
        prepared = self._prepare(candles_data)
        if self.horizon_bars == 1:
            return prepared
        # Rebuild only the labels/features whose future endpoint exists.  Feature rows
        # start at candle 20 and remain strictly functions of that candle's prefix.
        normalized = self._normalized_candles(candles_data)
        closes = normalized[:, 4]
        usable = len(normalized) - 20 - self.horizon_bars
        if usable <= 0:
            raise CandleValidationError("NO_LABELLED_FEATURES_FOR_HORIZON")
        returns = np.array(
            [
                math.log(closes[index + self.horizon_bars] / closes[index])
                for index in range(20, 20 + usable)
            ],
            dtype=np.float64,
        )
        return _PreparedData(
            timestamps=prepared.timestamps[:usable],
            features=prepared.features[:usable],
            forward_returns=returns,
            latest_features=prepared.latest_features,
            as_of=prepared.as_of,
            input_hash=prepared.input_hash,
        )

    @classmethod
    def _normalized_candles(cls, candles_data: list[dict[str, Any]]) -> np.ndarray:
        by_time: dict[datetime, tuple[float, float, float, float, float]] = {}
        for raw in candles_data:
            timestamp = cls._parse_timestamp(raw)
            values = tuple(float(raw[name]) for name in ("open", "high", "low", "close"))
            by_time[timestamp] = (*values, float(raw.get("volume", 0.0)))
        return np.asarray(
            [[item[0].timestamp(), *item[1]] for item in sorted(by_time.items())],
            dtype=np.float64,
        )

    @staticmethod
    def _feature_row(
        closes: np.ndarray,
        highs: np.ndarray,
        lows: np.ndarray,
        volumes: np.ndarray,
        index: int,
    ) -> np.ndarray:
        window_10 = closes[index - 9 : index + 1]
        return_window = np.diff(np.log(closes[index - 10 : index + 1]))
        volume_window = volumes[index - 19 : index + 1]
        volume_mean = float(np.mean(volume_window))
        volume_std = float(np.std(volume_window, ddof=1))
        current_volume = float(volumes[index])
        previous_volume = float(volumes[index - 1])
        return np.array(
            [
                math.log(closes[index] / closes[index - 1]),
                math.log(closes[index] / closes[index - 3]),
                math.log(closes[index] / closes[index - 5]),
                math.log(highs[index] / lows[index]),
                float(np.std(return_window, ddof=1)),
                closes[index] / float(np.mean(window_10)) - 1.0,
                (current_volume - volume_mean) / volume_std if volume_std > 0 else 0.0,
                math.log((current_volume + 1.0) / (previous_volume + 1.0)),
            ],
            dtype=np.float64,
        )

    def _chronological_split(self, n_samples: int) -> _Split:
        gap = self.horizon_bars
        available = n_samples - 3 * gap
        if available < self.MIN_WINDOW_SAMPLES * 4:
            raise CandleValidationError("TOO_FEW_SAMPLES_AFTER_GAPS")
        train_size = int(available * 0.55)
        validation_size = int(available * 0.15)
        calibration_size = int(available * 0.15)
        test_size = available - train_size - validation_size - calibration_size
        if min(validation_size, calibration_size, test_size) < self.MIN_WINDOW_SAMPLES:
            raise CandleValidationError("SPLIT_WINDOW_TOO_SMALL")
        train = np.arange(0, train_size)
        validation_start = train[-1] + 1 + gap
        validation = np.arange(validation_start, validation_start + validation_size)
        calibration_start = validation[-1] + 1 + gap
        calibration = np.arange(calibration_start, calibration_start + calibration_size)
        test_start = calibration[-1] + 1 + gap
        test = np.arange(test_start, test_start + test_size)
        if test[-1] >= n_samples:
            raise CandleValidationError("INVALID_CHRONOLOGICAL_SPLIT")
        return _Split(train, validation, calibration, test)

    @staticmethod
    def _manual_predict(
        coefs: list[np.ndarray], intercepts: list[np.ndarray], features: np.ndarray
    ) -> np.ndarray:
        activation = np.asarray(features, dtype=np.float64)
        for weights, bias in zip(coefs[:-1], intercepts[:-1], strict=True):
            activation = np.maximum(activation @ weights + bias, 0.0)
        logits = activation @ coefs[-1] + intercepts[-1]
        logits -= np.max(logits, axis=1, keepdims=True)
        exp_logits = np.exp(logits)
        probabilities = exp_logits / np.sum(exp_logits, axis=1, keepdims=True)
        if probabilities.shape[1] != 3 or not np.all(np.isfinite(probabilities)):
            raise ArtifactError("invalid model output")
        return probabilities

    @staticmethod
    def _temperature_scale(probabilities: np.ndarray, temperature: float) -> np.ndarray:
        log_prob = np.log(np.clip(probabilities, 1e-15, 1.0)) / temperature
        log_prob -= np.max(log_prob, axis=1, keepdims=True)
        scaled = np.exp(log_prob)
        return scaled / np.sum(scaled, axis=1, keepdims=True)

    def _fit_temperature(self, probabilities: np.ndarray, labels: np.ndarray) -> float:
        def objective(log_temperature: float) -> float:
            temperature = math.exp(log_temperature)
            scaled = self._temperature_scale(probabilities, temperature)
            return float(log_loss(labels, scaled, labels=[0, 1, 2]))

        optimum = minimize_scalar(
            objective,
            method="bounded",
            bounds=(math.log(0.05), math.log(20.0)),
            options={"xatol": 1e-8, "maxiter": 200},
        )
        if not optimum.success:
            raise ArtifactError("temperature optimization failed")
        return float(math.exp(optimum.x))

    @staticmethod
    def _conformal_threshold(
        probabilities: np.ndarray,
        labels: np.ndarray,
        alpha: float,
    ) -> float:
        """Finite-sample split-conformal quantile for inverse-probability scores."""
        if len(labels) == 0 or probabilities.shape != (len(labels), 3):
            raise ArtifactError("invalid conformal calibration window")
        scores = 1.0 - probabilities[np.arange(len(labels)), labels]
        if not np.all(np.isfinite(scores)):
            raise ArtifactError("non-finite conformal scores")
        rank = math.ceil((len(scores) + 1) * (1.0 - alpha))
        rank = min(max(rank, 1), len(scores))
        return float(np.sort(scores)[rank - 1])

    @staticmethod
    def _metrics(
        labels: np.ndarray, probabilities: np.ndarray, climatology: np.ndarray
    ) -> dict[str, dict[str, float]]:
        truth = np.eye(3, dtype=np.float64)[labels]
        baseline_prob = np.tile(climatology, (len(labels), 1))

        def calculate(prob: np.ndarray) -> dict[str, float]:
            predictions = np.argmax(prob, axis=1)
            return {
                "brier": float(np.mean(np.sum((prob - truth) ** 2, axis=1))),
                "log_loss": float(log_loss(labels, prob, labels=[0, 1, 2])),
                "balanced_accuracy": float(balanced_accuracy_score(labels, predictions)),
            }

        return {"model": calculate(probabilities), "baseline": calculate(baseline_prob)}

    @staticmethod
    def _finite_metrics(metrics: dict[str, dict[str, float]]) -> bool:
        return all(math.isfinite(value) for group in metrics.values() for value in group.values())

    def _predict_artifact(
        self, artifact: dict[str, Any], latest_features: np.ndarray
    ) -> np.ndarray:
        mean = np.asarray(artifact["scaler_mean"], dtype=np.float64)
        scale = np.asarray(artifact["scaler_scale"], dtype=np.float64)
        if mean.shape != (len(self.FEATURE_NAMES),) or scale.shape != mean.shape:
            raise ArtifactError("invalid scaler shape")
        if np.any(scale <= 0) or not np.all(np.isfinite(scale)):
            raise ArtifactError("invalid scaler scale")
        normalized = ((latest_features - mean) / scale).reshape(1, -1)
        raw = self._manual_predict(artifact["coefs"], artifact["intercepts"], normalized)
        calibrated = self._temperature_scale(raw, float(artifact["temperature"]))[0]
        if not np.all(calibrated >= 0) or not math.isclose(
            float(np.sum(calibrated)), 1.0, rel_tol=0.0, abs_tol=1e-12
        ):
            raise ArtifactError("probability simplex invalid")
        return calibrated

    def _artifact_paths(self, symbol: str) -> tuple[Path, Path]:
        safe_symbol = "".join(
            character for character in symbol if character.isalnum() or character in "-_"
        )
        if not safe_symbol:
            raise ArtifactError("unsafe symbol")
        stem = f"{safe_symbol}_h{self.horizon_bars}"
        return self.artifact_dir / f"{stem}.json", self.artifact_dir / f"{stem}.npz"

    def _save_artifact(self, symbol: str, artifact: dict[str, Any]) -> None:
        manifest_path, npz_path = self._artifact_paths(symbol)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        arrays: dict[str, np.ndarray] = {
            "scaler_mean": artifact["scaler_mean"],
            "scaler_scale": artifact["scaler_scale"],
            "classes": artifact["classes"],
            "climatology": artifact["climatology"],
            "class_return_means": artifact["class_return_means"],
        }
        for index, weights in enumerate(artifact["coefs"]):
            arrays[f"coef_{index}"] = weights
        for index, bias in enumerate(artifact["intercepts"]):
            arrays[f"intercept_{index}"] = bias

        temp_npz: Path | None = None
        temp_manifest: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=manifest_path.parent,
                prefix=f".{npz_path.stem}.",
                suffix=".tmp",
                delete=False,
            ) as file_handle:
                temp_npz = Path(file_handle.name)
                np.savez_compressed(file_handle, **arrays)
                file_handle.flush()
                os.fsync(file_handle.fileno())
            payload_hash = self._sha256(temp_npz)
            manifest = {
                "artifact_version": ARTIFACT_VERSION,
                "model_id": artifact["model_id"],
                "ticker": symbol,
                "as_of": artifact["as_of"],
                "horizon_bars": self.horizon_bars,
                "input_hash": artifact["input_hash"],
                "feature_names": list(self.FEATURE_NAMES),
                "hidden_layer_sizes": list(self.HIDDEN_LAYER_SIZES),
                "model_alpha": self.MODEL_ALPHA,
                "model_max_iter": self.MODEL_MAX_ITER,
                "movement_threshold": artifact["movement_threshold"],
                "temperature": artifact["temperature"],
                "conformal_alpha": artifact["conformal_alpha"],
                "conformal_threshold": artifact["conformal_threshold"],
                "conformal_calibration_samples": artifact["conformal_calibration_samples"],
                "metrics": artifact["metrics"],
                "npz_file": npz_path.name,
                "npz_sha256": payload_hash,
                "layer_count": len(artifact["coefs"]),
            }
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                dir=manifest_path.parent,
                prefix=f".{manifest_path.stem}.",
                suffix=".tmp",
                delete=False,
            ) as file_handle:
                temp_manifest = Path(file_handle.name)
                json.dump(
                    manifest,
                    file_handle,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                )
                file_handle.write("\n")
                file_handle.flush()
                os.fsync(file_handle.fileno())
            os.replace(temp_npz, npz_path)
            temp_npz = None
            os.replace(temp_manifest, manifest_path)
            temp_manifest = None
            artifact["artifact_hash"] = payload_hash
        finally:
            for temporary in (temp_npz, temp_manifest):
                if temporary is not None:
                    temporary.unlink(missing_ok=True)

    def _load_artifact(
        self,
        symbol: str,
        expected_as_of: datetime,
        expected_input_hash: str,
        reference_time: datetime,
    ) -> dict[str, Any] | None:
        manifest_path, expected_npz_path = self._artifact_paths(symbol)
        if not manifest_path.exists():
            raise FileNotFoundError(manifest_path)
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ArtifactError("manifest cannot be decoded") from exc
        if not isinstance(manifest, dict):
            raise ArtifactError("manifest root must be an object")
        required = {
            "artifact_version",
            "model_id",
            "ticker",
            "as_of",
            "horizon_bars",
            "input_hash",
            "feature_names",
            "temperature",
            "conformal_alpha",
            "conformal_threshold",
            "conformal_calibration_samples",
            "metrics",
            "npz_file",
            "npz_sha256",
            "layer_count",
        }
        if not required.issubset(manifest):
            raise ArtifactError("manifest fields missing")
        if manifest["artifact_version"] != ARTIFACT_VERSION:
            raise ArtifactError("unsupported artifact version")
        if manifest["ticker"] != symbol or manifest["horizon_bars"] != self.horizon_bars:
            raise ArtifactError("artifact identity mismatch")
        if not math.isclose(
            float(manifest["conformal_alpha"]),
            self.conformal_alpha,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ArtifactError("conformal contract mismatch")
        if manifest["feature_names"] != list(self.FEATURE_NAMES):
            raise ArtifactError("feature contract mismatch")
        if manifest["npz_file"] != expected_npz_path.name:
            raise ArtifactError("unsafe payload path")
        artifact_as_of = self._parse_datetime(manifest["as_of"])
        if artifact_as_of != expected_as_of:
            return None
        if manifest["input_hash"] != expected_input_hash:
            return None
        expected_model_id = self._model_id(symbol, artifact_as_of, expected_input_hash)
        if manifest["model_id"] != expected_model_id:
            raise ArtifactError("model identity mismatch")
        if reference_time - artifact_as_of > self.max_data_age:
            raise ArtifactError("artifact is stale")
        if not expected_npz_path.is_file():
            raise ArtifactError("payload missing")
        actual_hash = self._sha256(expected_npz_path)
        if not hmac.compare_digest(actual_hash, str(manifest["npz_sha256"])):
            raise ArtifactError("payload hash mismatch")
        try:
            with np.load(expected_npz_path, allow_pickle=False) as payload:
                arrays = {name: np.asarray(payload[name]) for name in payload.files}
        except (OSError, ValueError, KeyError) as exc:
            raise ArtifactError("payload cannot be loaded safely") from exc

        layer_count = int(manifest["layer_count"])
        if layer_count < 2:
            raise ArtifactError("invalid layer count")
        try:
            coefs = [arrays[f"coef_{index}"] for index in range(layer_count)]
            intercepts = [arrays[f"intercept_{index}"] for index in range(layer_count)]
            scaler_mean = arrays["scaler_mean"]
            scaler_scale = arrays["scaler_scale"]
            classes = arrays["classes"]
            climatology = arrays["climatology"]
            class_return_means = arrays["class_return_means"]
        except KeyError as exc:
            raise ArtifactError("payload arrays missing") from exc
        if not np.array_equal(classes, np.array([0, 1, 2])):
            raise ArtifactError("class mapping mismatch")
        artifact: dict[str, Any] = {
            "model_id": manifest["model_id"],
            "ticker": symbol,
            "as_of": manifest["as_of"],
            "horizon_bars": self.horizon_bars,
            "temperature": float(manifest["temperature"]),
            "conformal_alpha": float(manifest["conformal_alpha"]),
            "conformal_threshold": float(manifest["conformal_threshold"]),
            "conformal_calibration_samples": int(manifest["conformal_calibration_samples"]),
            "metrics": manifest["metrics"],
            "scaler_mean": scaler_mean,
            "scaler_scale": scaler_scale,
            "coefs": coefs,
            "intercepts": intercepts,
            "classes": classes,
            "climatology": climatology,
            "class_return_means": class_return_means,
            "artifact_hash": actual_hash,
        }
        # Validate architecture and numeric content before trusting inference.
        if not all(np.all(np.isfinite(array)) for array in arrays.values()):
            raise ArtifactError("payload contains non-finite values")
        if not 0.0 <= artifact["conformal_threshold"] <= 1.0:
            raise ArtifactError("invalid conformal threshold")
        if artifact["conformal_calibration_samples"] < self.MIN_WINDOW_SAMPLES:
            raise ArtifactError("conformal calibration window too small")
        try:
            self._predict_artifact(artifact, np.zeros(len(self.FEATURE_NAMES), dtype=np.float64))
        except (ArtifactError, ValueError, FloatingPointError, OverflowError) as exc:
            raise ArtifactError("payload architecture is invalid") from exc
        return artifact

    def _model_id(self, symbol: str, as_of: datetime, input_hash: str) -> str:
        identity = (
            f"technical-neural-v{ARTIFACT_VERSION}|{symbol}|h{self.horizon_bars}|"
            f"alpha={self.conformal_alpha:.12g}|"
            f"{as_of.isoformat()}|{input_hash}|{'|'.join(self.FEATURE_NAMES)}"
        )
        return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]

    @staticmethod
    def _input_hash(timestamps: tuple[datetime, ...], matrix: np.ndarray) -> str:
        digest = hashlib.sha256()
        for timestamp in timestamps:
            digest.update(timestamp.isoformat().encode("ascii"))
            digest.update(b"\0")
        digest.update(np.asarray(matrix, dtype="<f8").tobytes(order="C"))
        return digest.hexdigest()

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as file_handle:
            for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @classmethod
    def _parse_timestamp(cls, candle: dict[str, Any]) -> datetime:
        for key in ("datetime", "time", "timestamp", "date"):
            if key in candle and candle[key] not in (None, ""):
                return cls._parse_datetime(candle[key])
        raise CandleValidationError("MISSING_CANDLE_TIMESTAMP")

    @staticmethod
    def _parse_datetime(value: Any) -> datetime:
        if isinstance(value, datetime):
            parsed = value
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            numeric = float(value)
            if not math.isfinite(numeric):
                raise CandleValidationError("INVALID_CANDLE_TIMESTAMP")
            if numeric > 10_000_000_000:
                numeric /= 1000.0
            try:
                parsed = datetime.fromtimestamp(numeric, tz=timezone.utc)
            except (OSError, OverflowError, ValueError) as exc:
                raise CandleValidationError("INVALID_CANDLE_TIMESTAMP") from exc
        elif isinstance(value, str):
            text = value.strip().replace("Z", "+00:00")
            try:
                parsed = datetime.fromisoformat(text)
            except ValueError as exc:
                raise CandleValidationError("INVALID_CANDLE_TIMESTAMP") from exc
        else:
            raise CandleValidationError("INVALID_CANDLE_TIMESTAMP")
        return TechnicalNeuralExpert._as_utc(parsed)

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def _closed(
        self,
        status: str,
        reason_code: str,
        *,
        ticker: str,
        as_of: str | None = None,
        detail: str | None = None,
        baseline_comparison: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "expert": "TechnicalNeuralExpert",
            "source": "technical_neural_causal",
            "ticker": ticker,
            "status": status,
            "decision": "ABSTAIN",
            "direction_prob": {},
            "calibration_status": "unavailable",
            "skill_status": "unqualified",
            "model_id": None,
            "as_of": as_of,
            "horizon": {"bars": self.horizon_bars},
            "reason_codes": [reason_code],
            "confidence": 0.0,
            "uncertainty": 1.0,
        }
        if detail:
            result["detail"] = detail[:300]
        if baseline_comparison is not None:
            result["baseline_comparison"] = baseline_comparison
        return result
