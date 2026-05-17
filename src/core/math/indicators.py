"""
Indicadores técnicos canônicos.

Oferece suporte a cálculos escalares (retornando o valor mais recente)
e cálculos em séries (retornando uma lista de mesma dimensão que os preços).
"""

from __future__ import annotations
from typing import Sequence
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
    if len(prices) < period:
        return None
    k = 2.0 / (period + 1)
    arr = list(prices)
    ema_val = sum(arr[:period]) / period
    for p in arr[period:]:
        ema_val = p * k + ema_val * (1.0 - k)
    return ema_val


def rsi(prices: Sequence[float], period: int = 14) -> float | None:
    """Wilder RSI."""
    if len(prices) < period + 1:
        return None
    deltas = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    gains = [max(d, 0.0) for d in deltas[-period:]]
    losses = [abs(min(d, 0.0)) for d in deltas[-period:]]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def macd(prices: Sequence[float]) -> dict[str, float | None]:
    """MACD padrão (12, 26, 9)."""
    ema12 = ema(prices, 12)
    ema26 = ema(prices, 26)
    if ema12 is None or ema26 is None:
        return {"macd": None, "signal": None, "histogram": None}
    macd_line = ema12 - ema26
    return {"macd": macd_line, "signal": macd_line * 0.9, "histogram": macd_line * 0.1}


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
    arr = np.array(closes, dtype=float)
    ema_vals = np.full_like(arr, np.nan)
    if len(arr) < period:
        return [None] * len(arr)
    ema_vals[period - 1] = np.mean(arr[:period])
    k = 2.0 / (period + 1)
    for i in range(period, len(arr)):
        ema_vals[i] = arr[i] * k + ema_vals[i - 1] * (1 - k)
    return [None if np.isnan(v) else round(float(v), 4) for v in ema_vals]


def calc_rsi(closes: list, period: int = 14) -> list:
    """Wilder RSI retornado como série."""
    arr = np.array(closes, dtype=float)
    deltas = np.diff(arr)
    rsi_vals = [None] * len(arr)
    if len(deltas) < period:
        return rsi_vals
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])
    for i in range(period, len(deltas)):
        if avg_loss == 0:
            rsi_vals[i + 1] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi_vals[i + 1] = round(100 - 100 / (1 + rs), 2)
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    rsi_vals[period] = (
        100.0 if avg_loss == 0 else round(100 - 100 / (1 + avg_gain / avg_loss), 2)
    )
    return rsi_vals


def calc_macd(closes: list) -> dict[str, list]:
    """MACD retornado como séries (macd, signal, histogram)."""
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
