"""Leakage and execution ambiguity checks for the offline event dataset."""

import numpy as np
import pandas as pd
import pytest

from core.ml.event_dataset import FEATURE_COLUMNS, build_samples, split_samples


def bars(count=80, symbol="VFV.TO"):
    return pd.DataFrame(
        {
            "symbol": symbol,
            "date": pd.date_range("2025-01-01", periods=count),
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0,
            "volume": 1000.0,
        }
    )


def test_features_do_not_change_when_future_prices_change():
    original = bars()
    changed = original.copy()
    changed.loc[31:, ["open", "high", "low", "close"]] *= 1.5
    before, after = build_samples(original), build_samples(changed)
    cutoff = pd.Timestamp("2025-01-31", tz="UTC")
    left = before.loc[before.decision_time <= cutoff, ["decision_time", *FEATURE_COLUMNS]]
    right = after.loc[after.decision_time <= cutoff, ["decision_time", *FEATURE_COLUMNS]]
    pd.testing.assert_frame_equal(left.reset_index(drop=True), right.reset_index(drop=True))


def test_next_open_entry_and_ambiguous_touch_stop_first():
    data = bars(24)
    data.loc[21, ["open", "high", "low", "close"]] = [200, 211, 195, 200]
    sample = build_samples(data, horizon=2).iloc[0]
    assert sample.entry_time == pd.Timestamp("2025-01-22", tz="UTC")
    assert sample.label_end == sample.entry_time
    assert sample.exit_reason == "stop"
    assert sample.label == 0
    assert sample.net_return == pytest.approx(-0.025)


def test_stop_gap_uses_open_even_if_price_recovers_above_stop():
    data = bars(24)
    data.loc[22, ["open", "high", "low", "close"]] = [90, 100, 89, 99]
    sample = build_samples(data, horizon=3).iloc[0]
    assert sample.exit_reason == "stop_gap"
    assert sample.net_return == pytest.approx(-0.105)
    assert sample.label_end == pd.Timestamp("2025-01-23", tz="UTC")


def test_profit_gap_is_capped_at_target_and_costs_can_remove_positive_label():
    data = bars(24)
    data.loc[22, ["open", "high", "low", "close"]] = [110, 111, 109, 110]
    sample = build_samples(data, horizon=3).iloc[0]
    assert sample.exit_reason == "profit_target"
    assert sample.net_return == pytest.approx(0.045)
    assert sample.label == 1
    assert build_samples(data, horizon=3, cost_bps=600).iloc[0].label == 0


def test_censors_all_unfinished_horizons_even_with_observed_barrier():
    data = bars(22)
    assert build_samples(data, horizon=14).empty
    data.loc[21, "high"] = 106
    assert build_samples(data, horizon=14).empty
    complete = bars(35)
    complete.loc[21, "high"] = 106
    assert build_samples(complete, horizon=14).iloc[0].label == 1


def test_time_exit_positive_return_is_not_profit_target_label():
    data = bars(23)
    data.loc[22, ["open", "high", "low", "close"]] = [100, 102, 99, 102]
    sample = build_samples(data, horizon=2).iloc[0]
    assert sample.exit_reason == "time"
    assert sample.net_return > 0
    assert sample.label == 0


@pytest.mark.parametrize(
    "column,value",
    [
        ("open", 0),
        ("high", 98),
        ("low", 102),
        ("close", np.inf),
        ("volume", -1),
        ("date", None),
        ("symbol", ""),
    ],
)
def test_invalid_bars_rejected(column, value):
    data = bars()
    data.loc[0, column] = value
    with pytest.raises((ValueError, TypeError)):
        build_samples(data)


def test_duplicates_rejected_and_order_deterministic():
    data = pd.concat([bars(symbol="ZZZ"), bars(symbol="AAA")], ignore_index=True)
    pd.testing.assert_frame_equal(
        build_samples(data), build_samples(data.sample(frac=1, random_state=5))
    )
    with pytest.raises(ValueError, match="Duplicate"):
        build_samples(pd.concat([data, data.iloc[[0]]]))


def test_global_partitions_purge_label_overlap_and_embargo():
    data = pd.concat([bars(180, "AAA"), bars(180, "BBB")], ignore_index=True)
    samples = build_samples(data, horizon=5)
    train, calibration, test = split_samples(samples, embargo_days=2)
    assert train.label_end.max() < calibration.decision_time.min() - pd.Timedelta(days=2)
    assert calibration.label_end.max() < test.decision_time.min() - pd.Timedelta(days=2)
    for part in (train, calibration, test):
        assert part.groupby("decision_time").symbol.nunique().eq(2).all()
    assert set(train.decision_time).isdisjoint(test.decision_time)
    assert set(train.decision_time).isdisjoint(calibration.decision_time)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"train_fraction": 0},
        {"calibration_fraction": 0.5},
        {"embargo_days": -1},
        {"embargo_days": np.inf},
    ],
)
def test_bad_split_parameters_rejected(kwargs):
    with pytest.raises(ValueError):
        split_samples(build_samples(bars()), **kwargs)


def test_purging_refuses_too_little_history():
    with pytest.raises(ValueError):
        split_samples(build_samples(bars(40)))


@pytest.mark.parametrize(
    "kwargs",
    [
        {"horizon": 0},
        {"horizon": 1.5},
        {"stop_pct": np.nan},
        {"profit_multiple": np.inf},
        {"cost_bps": -1},
    ],
)
def test_bad_label_parameters_rejected(kwargs):
    with pytest.raises(ValueError):
        build_samples(bars(), **kwargs)


def test_utc_date_normalization():
    data = bars()
    data["date"] = pd.date_range("2025-01-01 20:00", periods=len(data), tz="America/Toronto")
    sample = build_samples(data).iloc[0]
    assert sample.decision_time == pd.Timestamp("2025-01-22", tz="UTC")
    assert sample.entry_time == pd.Timestamp("2025-01-23", tz="UTC")


def test_ohlc_serialization_noise_tolerance_does_not_repair_source():
    data = bars()
    data.loc[0, "high"] = 100 - 1e-13
    original = data.copy(deep=True)
    build_samples(data)
    pd.testing.assert_frame_equal(data, original)
    data.loc[0, "high"] = 100 - 1e-5
    with pytest.raises(ValueError, match="Inconsistent"):
        build_samples(data)
