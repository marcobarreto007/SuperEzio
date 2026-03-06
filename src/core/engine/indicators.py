"""Technical indicator functions operating on plain lists of close prices.

Canonical implementations. Import from here rather than redefining locally.
"""

from __future__ import annotations

import numpy as np


def calc_sma(closes: list, period: int) -> list:
    arr = np.array(closes, dtype=float)
    sma = np.full_like(arr, np.nan)
    for i in range(period - 1, len(arr)):
        sma[i] = np.mean(arr[i - period + 1 : i + 1])
    return [None if np.isnan(v) else round(float(v), 4) for v in sma]


def calc_ema(closes: list, period: int) -> list:
    arr = np.array(closes, dtype=float)
    ema = np.full_like(arr, np.nan)
    if len(arr) < period:
        return [None] * len(arr)
    ema[period - 1] = np.mean(arr[:period])
    k = 2.0 / (period + 1)
    for i in range(period, len(arr)):
        ema[i] = arr[i] * k + ema[i - 1] * (1 - k)
    return [None if np.isnan(v) else round(float(v), 4) for v in ema]


def calc_rsi(closes: list, period: int = 14) -> list:
    arr = np.array(closes, dtype=float)
    deltas = np.diff(arr)
    rsi = [None] * len(arr)
    if len(deltas) < period:
        return rsi
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])
    for i in range(period, len(deltas)):
        if avg_loss == 0:
            rsi[i + 1] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi[i + 1] = round(100 - 100 / (1 + rs), 2)
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    rsi[period] = (
        100.0 if avg_loss == 0 else round(100 - 100 / (1 + avg_gain / avg_loss), 2)
    )
    return rsi


def calc_macd(closes: list) -> dict[str, list]:
    ema12 = calc_ema(closes, 12)
    ema26 = calc_ema(closes, 26)
    macd_line = [
        round(a - b, 4) if a is not None and b is not None else None
        for a, b in zip(ema12, ema26)
    ]
    valid = [v for v in macd_line if v is not None]
    signal = [None] * len(macd_line)
    if len(valid) >= 9:
        start_idx = next(i for i, v in enumerate(macd_line) if v is not None)
        sig_vals = calc_ema(valid, 9)
        for j, sv in enumerate(sig_vals):
            if sv is not None:
                signal[start_idx + j] = sv
    histogram = [
        round(m - s, 4) if m is not None and s is not None else None
        for m, s in zip(macd_line, signal)
    ]
    return {"macd": macd_line, "signal": signal, "histogram": histogram}


def calc_bollinger(
    closes: list, period: int = 20, std_dev: float = 2.0
) -> dict[str, list]:
    middle = calc_sma(closes, period)
    arr = np.array(closes, dtype=float)
    upper = [None] * len(arr)
    lower = [None] * len(arr)
    for i in range(period - 1, len(arr)):
        window = arr[i - period + 1 : i + 1]
        sd = float(np.std(window, ddof=(len(window) > 1)))
        mid_val = middle[i]
        if mid_val is not None:
            upper[i] = round(mid_val + sd * std_dev, 4)
            lower[i] = round(mid_val - sd * std_dev, 4)
    return {"upper": upper, "middle": middle, "lower": lower}
