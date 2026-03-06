"""
Indicadores técnicos canônicos.

Importados de core.mathcore.base.
"""

from __future__ import annotations
from typing import Sequence
import numpy as np


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
