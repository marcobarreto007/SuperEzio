"""
Indicadores técnicos canônicos.

Oferece suporte a cálculos escalares (retornando o valor mais recente)
e cálculos em séries (retornando uma lista de mesma dimensão que os preços).
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

# ===========================================================================
# 1. Cálculos Escalares (Para Decision Engine / Experts)
# ===========================================================================


def sma(prices: Sequence[float], period: int) -> float | None:
    """Média móvel simples."""
    if len(prices) < period:
        return None
    return sum(prices[-period:]) / period


def ema(prices: Sequence[float], period: int) -> float | None:
    """Média móvel exponencial."""
    series = _ema_series(prices, period)
    return series[-1] if series and series[-1] is not None else None


def rsi(prices: Sequence[float], period: int = 14) -> float | None:
    """Latest causal Wilder RSI value."""
    series = _rsi_series(prices, period)
    return series[-1] if series and series[-1] is not None else None


def macd(prices: Sequence[float]) -> dict[str, float | None]:
    """MACD padrão (12, 26, 9)."""
    series = _macd_series(prices)
    macd_value = series["macd"][-1] if series["macd"] else None
    signal_value = series["signal"][-1] if series["signal"] else None
    histogram = (
        macd_value - signal_value if macd_value is not None and signal_value is not None else None
    )
    return {"macd": macd_value, "signal": signal_value, "histogram": histogram}


def bollinger(
    prices: Sequence[float], period: int = 20, std_dev: float = 2.0
) -> dict[str, float | None]:
    """Bollinger Bands."""
    mid = sma(prices, period)
    if mid is None:
        return {"upper": None, "middle": None, "lower": None}
    band = np.std(prices[-period:], ddof=1) if len(prices) >= period else 0.0
    return {"upper": mid + std_dev * band, "middle": mid, "lower": mid - std_dev * band}


def vwap(prices: Sequence[float], volumes: Sequence[float]) -> float | None:
    """Volume Weighted Average Price."""
    if len(prices) != len(volumes) or not prices:
        return None
    total_vol = sum(volumes)
    if total_vol == 0:
        return None
    return sum(p * v for p, v in zip(prices, volumes)) / total_vol


def vwap_deviation(current_price: float, vwap_value: float | None) -> float:
    """Desvio percentual do preço em relação ao VWAP."""
    if vwap_value is None or vwap_value == 0:
        return 0.0
    return (current_price - vwap_value) / vwap_value


# ===========================================================================
# 2. Cálculos em Séries (Para API / Endpoints de Gráficos)
# ===========================================================================


def calc_sma(closes: list, period: int) -> list:
    """Média Móvel Simples retornada como série."""
    arr = np.array(closes, dtype=float)
    sma_vals = np.full_like(arr, np.nan)
    for i in range(period - 1, len(arr)):
        sma_vals[i] = np.mean(arr[i - period + 1 : i + 1])
    return [None if np.isnan(v) else round(float(v), 4) for v in sma_vals]


def calc_ema(closes: list, period: int) -> list:
    """Média Móvel Exponencial retornada como série."""
    return [None if value is None else round(value, 4) for value in _ema_series(closes, period)]


def calc_rsi(closes: list, period: int = 14) -> list:
    """Wilder RSI retornado como série."""
    return [None if value is None else round(value, 2) for value in _rsi_series(closes, period)]


def calc_macd(closes: list) -> dict[str, list]:
    """MACD retornado como séries (macd, signal, histogram)."""
    raw = _macd_series(closes)
    return {
        name: [None if value is None else round(value, 4) for value in values]
        for name, values in raw.items()
    }


def _ema_series(values: Sequence[float], period: int) -> list[float | None]:
    """SMA-seeded EMA without rounding intermediate state."""
    if period <= 0:
        raise ValueError("period must be positive")
    arr = [float(value) for value in values]
    result: list[float | None] = [None] * len(arr)
    if len(arr) < period:
        return result
    current = sum(arr[:period]) / period
    result[period - 1] = current
    alpha = 2.0 / (period + 1.0)
    for index in range(period, len(arr)):
        current = alpha * arr[index] + (1.0 - alpha) * current
        result[index] = current
    return result


def _rsi_value(avg_gain: float, avg_loss: float) -> float:
    if avg_gain == 0.0 and avg_loss == 0.0:
        return 50.0
    if avg_loss == 0.0:
        return 100.0
    if avg_gain == 0.0:
        return 0.0
    return 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)


def _rsi_series(values: Sequence[float], period: int) -> list[float | None]:
    """Causal Wilder smoothing; every prefix is independent of later observations."""
    if period <= 0:
        raise ValueError("period must be positive")
    arr = [float(value) for value in values]
    result: list[float | None] = [None] * len(arr)
    if len(arr) < period + 1:
        return result

    deltas = [arr[index] - arr[index - 1] for index in range(1, len(arr))]
    gains = [max(delta, 0.0) for delta in deltas]
    losses = [max(-delta, 0.0) for delta in deltas]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    result[period] = _rsi_value(avg_gain, avg_loss)

    for delta_index in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[delta_index]) / period
        avg_loss = (avg_loss * (period - 1) + losses[delta_index]) / period
        result[delta_index + 1] = _rsi_value(avg_gain, avg_loss)
    return result


def _macd_series(values: Sequence[float]) -> dict[str, list[float | None]]:
    """Full-precision 12/26 MACD with a genuine 9-period EMA signal."""
    ema12 = _ema_series(values, 12)
    ema26 = _ema_series(values, 26)
    macd_line = [
        fast - slow if fast is not None and slow is not None else None
        for fast, slow in zip(ema12, ema26)
    ]
    first_valid = next((i for i, value in enumerate(macd_line) if value is not None), None)
    signal: list[float | None] = [None] * len(macd_line)
    if first_valid is not None:
        valid_macd = [value for value in macd_line[first_valid:] if value is not None]
        signal_tail = _ema_series(valid_macd, 9)
        signal[first_valid:] = signal_tail
    histogram = [
        line - sig if line is not None and sig is not None else None
        for line, sig in zip(macd_line, signal)
    ]
    return {"macd": macd_line, "signal": signal, "histogram": histogram}


def calc_bollinger(closes: list, period: int = 20, std_dev: float = 2.0) -> dict[str, list]:
    """Bollinger Bands retornadas como série."""
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
