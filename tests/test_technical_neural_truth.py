"""Scientific-integrity tests for the causal neural price expert."""

from __future__ import annotations

import hashlib
import json
import math
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest
from hypothesis import given, settings, strategies as st

from experts.technical_neural.expert import TechnicalNeuralExpert

AS_OF = datetime(2026, 7, 19, tzinfo=timezone.utc)


def _predictable_candles(length: int = 360) -> list[dict[str, object]]:
    returns = (-0.018, 0.0, 0.018)
    price = 100.0
    candles: list[dict[str, object]] = []
    for index in range(length):
        log_return = returns[index % len(returns)]
        open_price = price
        price *= math.exp(log_return)
        candles.append(
            {
                "datetime": (AS_OF - timedelta(days=length - 1 - index)).isoformat(),
                "open": open_price,
                "high": max(open_price, price) * 1.002,
                "low": min(open_price, price) * 0.998,
                "close": price,
                "volume": 1_000_000 + index * 10_000 + (index % 3) * 250_000,
            }
        )
    return candles


@pytest.fixture(scope="module")
def qualified_model(tmp_path_factory: pytest.TempPathFactory) -> dict[str, object]:
    artifact_dir = tmp_path_factory.mktemp("technical-neural")
    candles = _predictable_candles()
    expert = TechnicalNeuralExpert(artifact_dir=artifact_dir)
    result = expert.evaluate("TRUTH", candles, now=AS_OF)
    assert result["status"] == "ready", result
    return {
        "artifact_dir": artifact_dir,
        "candles": candles,
        "expert": expert,
        "result": result,
    }


def test_ready_result_is_calibrated_three_class_simplex(qualified_model: dict[str, object]) -> None:
    result = qualified_model["result"]
    assert isinstance(result, dict)
    probabilities = result["direction_prob"]
    assert set(probabilities) == {"down", "sideways", "up"}
    assert all(0.0 <= value <= 1.0 for value in probabilities.values())
    assert sum(probabilities.values()) == pytest.approx(1.0, abs=1e-12)
    assert result["calibration_status"] == "calibrated"
    assert result["skill_status"] == "qualified"
    assert result["decision"] in {"DOWN", "SIDEWAYS", "UP"}
    assert set(result["prediction_set"]).issubset({"DOWN", "SIDEWAYS", "UP"})
    assert result["conformal"]["method"] == "split_conformal_inverse_probability"
    assert result["conformal"]["marginal_coverage_target"] == pytest.approx(0.9)
    assert result["conformal"]["calibration_samples"] >= 12


def test_scaler_is_fit_on_train_partition_only(qualified_model: dict[str, object]) -> None:
    expert = qualified_model["expert"]
    candles = qualified_model["candles"]
    artifact_dir = qualified_model["artifact_dir"]
    assert isinstance(expert, TechnicalNeuralExpert)
    assert isinstance(candles, list)
    assert isinstance(artifact_dir, Path)

    prepared = expert._prepare_with_horizon(candles)
    split = expert._chronological_split(len(prepared.features))
    expected_train_mean = prepared.features[split.train].mean(axis=0)
    all_data_mean = prepared.features.mean(axis=0)
    with np.load(artifact_dir / "TRUTH_h1.npz", allow_pickle=False) as payload:
        persisted_mean = payload["scaler_mean"]
    assert np.allclose(persisted_mean, expected_train_mean)
    assert not np.allclose(persisted_mean, all_data_mean)


def test_chronological_partitions_have_horizon_gaps() -> None:
    expert = TechnicalNeuralExpert(horizon_bars=3)
    split = expert._chronological_split(300)
    windows = (split.train, split.validation, split.calibration, split.test)
    for earlier, later in zip(windows, windows[1:]):
        assert earlier[-1] < later[0]
        assert later[0] - earlier[-1] - 1 == expert.horizon_bars


def test_features_are_prefix_causal() -> None:
    expert = TechnicalNeuralExpert()
    original = _predictable_candles()
    changed_future = [dict(candle) for candle in original]
    cutoff = 200
    for candle in changed_future[cutoff + 1 :]:
        candle["open"] = float(candle["open"]) * 1.7
        candle["high"] = float(candle["high"]) * 1.7
        candle["low"] = float(candle["low"]) * 1.7
        candle["close"] = float(candle["close"]) * 1.7
        candle["volume"] = float(candle["volume"]) * 9.0
    base = expert._prepare_with_horizon(original)
    mutated = expert._prepare_with_horizon(changed_future)
    # Feature row zero is candle 20; row 180 is the cutoff candle itself.
    assert np.array_equal(base.features[: cutoff - 19], mutated.features[: cutoff - 19])


def test_sort_and_identical_dedup_are_order_invariant() -> None:
    expert = TechnicalNeuralExpert()
    candles = _predictable_candles(80)
    scrambled = list(reversed(candles)) + [dict(candles[15]), dict(candles[45])]
    chronological = expert._prepare_with_horizon(candles)
    deduplicated = expert._prepare_with_horizon(scrambled)
    assert chronological.input_hash == deduplicated.input_hash
    assert np.array_equal(chronological.features, deduplicated.features)
    assert np.array_equal(chronological.forward_returns, deduplicated.forward_returns)


def test_conflicting_duplicate_timestamp_fails_closed() -> None:
    candles = _predictable_candles(180)
    conflict = dict(candles[50])
    conflict["volume"] = float(conflict["volume"]) * 1.1
    result = TechnicalNeuralExpert().evaluate("DUP", candles + [conflict], now=AS_OF)
    assert result["status"] == "insufficient_data"
    assert result["decision"] == "ABSTAIN"
    assert result["direction_prob"] == {}
    assert result["reason_codes"] == ["CONFLICTING_DUPLICATE_TIMESTAMP"]


def test_restart_reloads_identical_prediction(qualified_model: dict[str, object]) -> None:
    artifact_dir = qualified_model["artifact_dir"]
    candles = qualified_model["candles"]
    original = qualified_model["result"]
    assert isinstance(artifact_dir, Path)
    assert isinstance(candles, list)
    assert isinstance(original, dict)
    restarted = TechnicalNeuralExpert(artifact_dir=artifact_dir).evaluate(
        "TRUTH", list(reversed(candles)), now=AS_OF
    )
    assert restarted["loaded_from_artifact"] is True
    assert restarted["model_id"] == original["model_id"]
    assert restarted["artifact_hash"] == original["artifact_hash"]
    assert restarted["direction_prob"] == original["direction_prob"]


def test_artifact_manifest_hash_matches_safe_npz(qualified_model: dict[str, object]) -> None:
    artifact_dir = qualified_model["artifact_dir"]
    assert isinstance(artifact_dir, Path)
    manifest = json.loads((artifact_dir / "TRUTH_h1.json").read_text(encoding="utf-8"))
    payload = artifact_dir / manifest["npz_file"]
    assert manifest["artifact_version"] == 2
    assert manifest["npz_sha256"] == hashlib.sha256(payload.read_bytes()).hexdigest()
    with np.load(payload, allow_pickle=False) as arrays:
        assert arrays["classes"].tolist() == [0, 1, 2]


def test_corrupt_artifact_fails_closed(
    qualified_model: dict[str, object], tmp_path: Path
) -> None:
    source_dir = qualified_model["artifact_dir"]
    candles = qualified_model["candles"]
    assert isinstance(source_dir, Path)
    assert isinstance(candles, list)
    shutil.copy2(source_dir / "TRUTH_h1.json", tmp_path / "TRUTH_h1.json")
    shutil.copy2(source_dir / "TRUTH_h1.npz", tmp_path / "TRUTH_h1.npz")
    with (tmp_path / "TRUTH_h1.npz").open("ab") as file_handle:
        file_handle.write(b"corruption")
    result = TechnicalNeuralExpert(artifact_dir=tmp_path).evaluate(
        "TRUTH", candles, now=AS_OF
    )
    assert result["status"] == "error"
    assert result["decision"] == "ABSTAIN"
    assert result["direction_prob"] == {}
    assert result["reason_codes"] == ["ARTIFACT_INVALID"]


def test_stale_candles_fail_closed(tmp_path: Path) -> None:
    candles = _predictable_candles()
    result = TechnicalNeuralExpert(artifact_dir=tmp_path).evaluate(
        "STALE", candles, now=AS_OF + timedelta(days=8)
    )
    assert result["status"] == "stale"
    assert result["decision"] == "ABSTAIN"
    assert result["direction_prob"] == {}
    assert result["reason_codes"] == ["STALE_CANDLES"]


def test_baseline_gate_abstains_when_predictions_have_no_skill(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def uniform_predict(
        _coefs: list[np.ndarray], _intercepts: list[np.ndarray], features: np.ndarray
    ) -> np.ndarray:
        return np.full((len(features), 3), 1.0 / 3.0, dtype=np.float64)

    monkeypatch.setattr(TechnicalNeuralExpert, "_manual_predict", staticmethod(uniform_predict))
    result = TechnicalNeuralExpert(artifact_dir=tmp_path).evaluate(
        "NOSKILL", _predictable_candles(), now=AS_OF
    )
    assert result["status"] == "abstain"
    assert result["decision"] == "ABSTAIN"
    assert result["direction_prob"] == {}
    assert result["reason_codes"] == ["VALIDATION_BASELINE_NOT_BEATEN"]


@given(
    st.lists(st.floats(min_value=-20, max_value=20, allow_nan=False), min_size=3, max_size=3),
    st.floats(min_value=0.05, max_value=20.0, allow_nan=False),
)
@settings(max_examples=50, deadline=None)
def test_temperature_scaling_preserves_simplex(logits: list[float], temperature: float) -> None:
    raw_logits = np.asarray([logits], dtype=np.float64)
    raw_logits -= raw_logits.max(axis=1, keepdims=True)
    raw = np.exp(raw_logits)
    raw /= raw.sum(axis=1, keepdims=True)
    scaled = TechnicalNeuralExpert._temperature_scale(raw, temperature)
    assert np.all(scaled >= 0)
    assert np.all(scaled <= 1)
    assert float(scaled.sum()) == pytest.approx(1.0, abs=1e-12)
