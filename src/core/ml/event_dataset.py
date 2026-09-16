"""Causal daily-bar research samples and purged chronological partitions.

Every eligible close is an exploratory long candidate, NOT a validated primary
strategy. Entry uses the next observed bar's open (a research fill assumption,
not a promise that a LIMIT order fills). Costs are round-trip basis points.
Label 1 requires the upper barrier first AND positive return after costs.
Daily OHLC cannot resolve intrabar ordering: simultaneous touches lose first.
No forward-filled prices, inferred calendar bars, or future-derived features.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

FEATURE_COLUMNS = ["ret_1", "ret_5", "ret_20", "vol_20", "volume_ratio_20", "range_pct"]
OHLC_RELATIVE_TOLERANCE = 1e-12
SAMPLE_COLUMNS = [
    "decision_time",
    "entry_time",
    "label_end",
    "symbol",
    *FEATURE_COLUMNS,
    "label",
    "net_return",
    "exit_reason",
]


def _validated_bars(bars: pd.DataFrame) -> pd.DataFrame:
    required = ["symbol", "date", "open", "high", "low", "close", "volume"]
    missing = set(required).difference(bars.columns)
    if missing:
        raise ValueError(f"Missing bar columns: {sorted(missing)}")
    frame = bars[required].copy()
    if frame["symbol"].isna().any():
        raise ValueError("Null symbol")
    frame["symbol"] = frame["symbol"].astype(str).str.strip()
    if frame["symbol"].eq("").any():
        raise ValueError("Empty symbol")
    frame["date"] = pd.to_datetime(frame["date"], utc=True, errors="raise").dt.normalize()
    if frame["date"].isna().any():
        raise ValueError("Null date")
    numeric = required[2:]
    frame[numeric] = frame[numeric].apply(pd.to_numeric, errors="raise")
    if not np.isfinite(frame[numeric].to_numpy(dtype=float)).all():
        raise ValueError("Nonfinite OHLCV")
    if (frame[["open", "high", "low", "close"]] <= 0).any().any():
        raise ValueError("OHLC must be positive")
    if (frame["volume"] < 0).any():
        raise ValueError("Volume must be nonnegative")
    upper = frame[["open", "close", "low"]].max(axis=1)
    lower = frame[["open", "close", "high"]].min(axis=1)
    # Permit floating-point serialization noise only; never repair source bars.
    if (
        (
            (frame["high"] < upper)
            & ~np.isclose(frame["high"], upper, rtol=OHLC_RELATIVE_TOLERANCE, atol=0)
        )
        | (
            (frame["low"] > lower)
            & ~np.isclose(frame["low"], lower, rtol=OHLC_RELATIVE_TOLERANCE, atol=0)
        )
    ).any():
        raise ValueError("Inconsistent OHLC")
    if frame.duplicated(["symbol", "date"]).any():
        raise ValueError("Duplicate symbol/date")
    return frame.sort_values(["symbol", "date"]).reset_index(drop=True)


def build_samples(
    bars: pd.DataFrame,
    horizon: int = 14,
    stop_pct: float = 0.02,
    profit_multiple: float = 2.5,
    cost_bps: float = 50,
) -> pd.DataFrame:
    """Build triple-barrier outcomes; exclude all partial-horizon candidates.

    Horizon counts observed trading bars starting with the entry bar. Features
    include the decision close but never any entry/future bar. Input must use a
    consistent OHLC adjustment basis and exclude unresolved corporate actions.
    A full horizon must be observable even for an early barrier hit, so inclusion
    near the dataset cutoff cannot depend on the outcome.
    """
    if isinstance(horizon, bool) or not isinstance(horizon, (int, np.integer)) or horizon < 1:
        raise ValueError("horizon must be a positive integer")
    if not np.isfinite([stop_pct, profit_multiple, cost_bps]).all():
        raise ValueError("Parameters must be finite")
    if not 0 < stop_pct < 1 or profit_multiple <= 0 or cost_bps < 0:
        raise ValueError("Invalid stop, profit multiple or costs")
    frame = _validated_bars(bars)
    rows = []
    for symbol, group in frame.groupby("symbol", sort=True):
        group = group.reset_index(drop=True)
        close = group["close"]
        features = pd.DataFrame(
            {
                "ret_1": close.pct_change(fill_method=None),
                "ret_5": close.pct_change(5, fill_method=None),
                "ret_20": close.pct_change(20, fill_method=None),
                "vol_20": close.pct_change(fill_method=None).rolling(20).std(ddof=1),
                "volume_ratio_20": group["volume"] / group["volume"].rolling(20).mean(),
                "range_pct": (group["high"] - group["low"]) / close,
            }
        )
        for index in range(len(group) - 1):
            values = features.iloc[index]
            if not np.isfinite(values.to_numpy()).all():
                continue
            entry = float(group.iloc[index + 1]["open"])
            stop, take = entry * (1 - stop_pct), entry * (1 + stop_pct * profit_multiple)
            future = group.iloc[index + 1 : index + 1 + horizon]
            if len(future) < horizon:
                continue
            exit_price, end, reason = None, None, None
            for bar in future.itertuples(index=False):
                # An opening gap is observed before any intrabar high/low.
                if bar.open <= stop:
                    exit_price, reason = float(bar.open), "stop_gap"
                elif bar.open >= take:
                    exit_price, reason = take, "profit_target"
                elif bar.low <= stop:
                    exit_price, reason = stop, "stop"
                elif bar.high >= take:
                    exit_price, reason = take, "profit_target"
                if reason is not None:
                    end = bar.date
                    break
            if reason is None:
                last = future.iloc[-1]
                exit_price, end, reason = float(last["close"]), last["date"], "time"
            net_return = exit_price / entry - 1 - cost_bps / 10_000
            rows.append(
                {
                    "decision_time": group.iloc[index]["date"],
                    "entry_time": group.iloc[index + 1]["date"],
                    "label_end": end,
                    "symbol": symbol,
                    **values.to_dict(),
                    "label": int(reason == "profit_target" and net_return > 0),
                    "net_return": net_return,
                    "exit_reason": reason,
                }
            )
    result = pd.DataFrame(rows, columns=SAMPLE_COLUMNS)
    for column in ("decision_time", "entry_time", "label_end"):
        result[column] = pd.to_datetime(result[column], utc=True)
    return result.sort_values(["decision_time", "symbol"]).reset_index(drop=True)


def split_samples(
    samples: pd.DataFrame,
    train_fraction: float = 0.6,
    calibration_fraction: float = 0.2,
    embargo_days: float = 1,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Global date partitions; purge overlapping labels plus calendar embargo.

    The strict boundary is label_end < next partition's first decision_time minus
    embargo. A symbol can never place the same decision date in two partitions.
    """
    if not np.isfinite([train_fraction, calibration_fraction, embargo_days]).all():
        raise ValueError("Split parameters must be finite")
    if (
        train_fraction <= 0
        or calibration_fraction <= 0
        or train_fraction + calibration_fraction >= 1
        or embargo_days < 0
    ):
        raise ValueError("Invalid split fractions or embargo")
    frame = samples.copy()
    for column in ("decision_time", "entry_time", "label_end"):
        frame[column] = pd.to_datetime(frame[column], utc=True, errors="raise")
        if frame[column].isna().any():
            raise ValueError(f"Null {column}")
    if (
        (frame["entry_time"] <= frame["decision_time"]) | (frame["label_end"] < frame["entry_time"])
    ).any():
        raise ValueError("Invalid event time ordering")
    dates = sorted(frame["decision_time"].unique())
    first = int(len(dates) * train_fraction)
    second = int(len(dates) * (train_fraction + calibration_fraction))
    if not 0 < first < second < len(dates):
        raise ValueError("Insufficient decision dates for three partitions")
    boundary1, boundary2 = dates[first], dates[second]
    embargo = pd.Timedelta(days=embargo_days)
    train = frame[(frame["decision_time"] < boundary1) & (frame["label_end"] < boundary1 - embargo)]
    calibration = frame[
        (frame["decision_time"] >= boundary1)
        & (frame["decision_time"] < boundary2)
        & (frame["label_end"] < boundary2 - embargo)
    ]
    test = frame[frame["decision_time"] >= boundary2]
    partitions = tuple(
        part.sort_values(["decision_time", "symbol"]).reset_index(drop=True)
        for part in (train, calibration, test)
    )
    if any(part.empty for part in partitions):
        raise ValueError("Purging leaves an empty partition; more history is required")
    return partitions
