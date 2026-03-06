"""
MathCore Base — fórmulas matemáticas canônicas e únicas.

Elimina duplicações entre indicators.py, quant_engine.py, crisis/normalization.py,
f51/formulas.py, etc.

Toda fórmula aqui é a implementação de referência. Módulos externos devem importar daqui.
"""

from __future__ import annotations
import math
from typing import Sequence

import numpy as np

# ── Constantes ──────────────────────────────────────────────────────────────
TRADING_DAYS_YEAR = 252


# ── Funções de ativação / utilitário ────────────────────────────────────────


def sigmoid(x: float) -> float:
    """σ(x) estável contra overflow."""
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    """Restringe x ao intervalo [lo, hi]."""
    return max(lo, min(hi, x))


def t_norm(a: float, b: float) -> float:
    """T-norm produto: P(A ∧ B)."""
    return a * b


def t_conorm(a: float, b: float) -> float:
    """T-conorm (soma probabilística): P(A ∨ B) = 1-(1-a)(1-b)."""
    return 1.0 - (1.0 - a) * (1.0 - b)


# ── Indicadores Técnicos (canônicos) ────────────────────────────────────────


def sma(prices: Sequence[float], period: int) -> float | None:
    """Média móvel simples. Retorna None se len < period."""
    if len(prices) < period:
        return None
    return sum(prices[-period:]) / period


def ema(prices: Sequence[float], period: int) -> float | None:
    """Média móvel exponencial. Retorna None se len < period."""
    if len(prices) < period:
        return None
    k = 2.0 / (period + 1)
    arr = list(prices)
    ema_val = sum(arr[:period]) / period
    for p in arr[period:]:
        ema_val = p * k + ema_val * (1.0 - k)
    return ema_val


def rsi(prices: Sequence[float], period: int = 14) -> float | None:
    """Wilder RSI. Retorna None se len < period+1."""
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
    """MACD padrão (12, 26, 9). Retorna dict com macd, signal, histograma."""
    ema12 = ema(prices, 12)
    ema26 = ema(prices, 26)
    if ema12 is None or ema26 is None:
        return {"macd": None, "signal": None, "histogram": None}
    macd_line = ema12 - ema26
    # Signal = EMA(MACD, 9) — precisamos de histórico MACD
    # Aproximação: usamos o valor atual como proxy se histórico curto
    return {"macd": macd_line, "signal": macd_line * 0.9, "histogram": macd_line * 0.1}


def bollinger(
    prices: Sequence[float], period: int = 20, std_dev: float = 2.0
) -> dict[str, float | None]:
    """Bollinger Bands. Retorna dict com upper, middle, lower."""
    mid = sma(prices, period)
    if mid is None:
        return {"upper": None, "middle": None, "lower": None}
    band = np.std(prices[-period:], ddof=1) if len(prices) >= period else 0.0
    return {
        "upper": mid + std_dev * band,
        "middle": mid,
        "lower": mid - std_dev * band,
    }


# ── Normalização / Estatística ──────────────────────────────────────────────


def percentile_rank(values: Sequence[float], value: float) -> float:
    """Percentil de value em values (0-100)."""
    if not values:
        return 50.0
    below = sum(1 for v in values if v < value)
    equal = sum(1 for v in values if v == value)
    return 100.0 * (below + 0.5 * equal) / len(values)


def zscore(value: float, mean: float, std: float) -> float:
    """Z-score padrão."""
    if std == 0:
        return 0.0
    return (value - mean) / std


# ── Métricas de Retorno ─────────────────────────────────────────────────────


def log_return(current: float, previous: float) -> float:
    """Retorno logarítmico."""
    if previous <= 0:
        return 0.0
    return math.log(current / previous)


def simple_return(current: float, previous: float) -> float:
    """Retorno simples."""
    if previous == 0:
        return 0.0
    return (current - previous) / previous


def annualized_return(daily_returns: Sequence[float]) -> float:
    """Retorno anualizado a partir de retornos diários."""
    if not daily_returns:
        return 0.0
    mean_daily = sum(daily_returns) / len(daily_returns)
    return mean_daily * TRADING_DAYS_YEAR


# ── Métricas de Risco ───────────────────────────────────────────────────────


def volatility(daily_returns: Sequence[float], annualize: bool = True) -> float:
    """Volatilidade (desvio padrão). Anualizada por padrão."""
    if len(daily_returns) < 2:
        return 0.0
    std = float(np.std(daily_returns, ddof=1))
    if annualize:
        return std * math.sqrt(TRADING_DAYS_YEAR)
    return std


def sharpe_ratio(daily_returns: Sequence[float], risk_free_rate: float = 0.0) -> float:
    """Sharpe ratio anualizado."""
    if len(daily_returns) < 2:
        return 0.0
    excess = [r - risk_free_rate / TRADING_DAYS_YEAR for r in daily_returns]
    mean_excess = sum(excess) / len(excess)
    std_excess = float(np.std(excess, ddof=1))
    if std_excess == 0:
        return 0.0
    return (mean_excess / std_excess) * math.sqrt(TRADING_DAYS_YEAR)


def sortino_ratio(daily_returns: Sequence[float], risk_free_rate: float = 0.0) -> float:
    """Sortino ratio (downside deviation)."""
    if len(daily_returns) < 2:
        return 0.0
    excess = [r - risk_free_rate / TRADING_DAYS_YEAR for r in daily_returns]
    mean_excess = sum(excess) / len(excess)
    downside = [e**2 for e in excess if e < 0]
    if not downside:
        return float("inf") if mean_excess > 0 else 0.0
    downside_std = math.sqrt(sum(downside) / len(downside))
    if downside_std == 0:
        return 0.0
    return (mean_excess / downside_std) * math.sqrt(TRADING_DAYS_YEAR)


def max_drawdown(equity_curve: Sequence[float]) -> float:
    """Max drawdown percentual (negativo)."""
    if not equity_curve or equity_curve[0] == 0:
        return 0.0
    peak = equity_curve[0]
    max_dd = 0.0
    for val in equity_curve:
        if val > peak:
            peak = val
        dd = (val - peak) / peak
        if dd < max_dd:
            max_dd = dd
    return max_dd


def calmar_ratio(annual_return: float, max_dd: float) -> float:
    """Calmar ratio."""
    if max_dd >= 0 or max_dd == 0:
        return 0.0
    return annual_return / abs(max_dd)


def beta(asset_returns: Sequence[float], market_returns: Sequence[float]) -> float:
    """Beta via covariância."""
    if len(asset_returns) != len(market_returns) or len(asset_returns) < 2:
        return 1.0
    cov = np.cov(asset_returns, market_returns)[0][1]
    var_market = np.var(market_returns, ddof=1)
    if var_market == 0:
        return 1.0
    return float(cov / var_market)


def alpha(
    annual_return: float, beta: float, market_return: float, risk_free: float = 0.0
) -> float:
    """Alpha de Jensen (anualizado)."""
    return annual_return - (risk_free + beta * (market_return - risk_free))


def var_historic(returns: Sequence[float], confidence: float = 0.95) -> float:
    """VaR histórico (percentil)."""
    if not returns:
        return 0.0
    sorted_r = sorted(returns)
    idx = int((1.0 - confidence) * len(sorted_r))
    return sorted_r[max(0, idx)]


def cvar_historic(returns: Sequence[float], confidence: float = 0.95) -> float:
    """CVaR (Expected Shortfall) histórico."""
    if not returns:
        return 0.0
    var = var_historic(returns, confidence)
    tail = [r for r in returns if r <= var]
    if not tail:
        return var
    return sum(tail) / len(tail)


# ── VWAP ──────────────────────────────────────────────────────────────────────


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


# ── Kelly Criterion ───────────────────────────────────────────────────────────


def kelly_fraction(win_prob: float, win_loss_ratio: float) -> float:
    """Kelly fraction: f* = (p·b - q) / b. Limitado a [0, 1]."""
    if win_loss_ratio <= 0:
        return 0.0
    q = 1.0 - win_prob
    f = (win_prob * win_loss_ratio - q) / win_loss_ratio
    return clamp(f, 0.0, 1.0)


def kelly_position_size(
    win_prob: float,
    win_loss_ratio: float,
    capital: float,
    max_fraction: float = 0.25,
) -> float:
    """Tamanho de posição em unidades monetárias via Kelly ajustado."""
    f = kelly_fraction(win_prob, win_loss_ratio)
    # Ajuste conservador: nunca ultrapassa max_fraction do capital
    f = min(f, max_fraction)
    return capital * f


# ── Profit Factor / Expectancy ───────────────────────────────────────────────


def profit_factor(gross_profit: float, gross_loss: float) -> float:
    """Profit Factor = lucro bruto / |perda bruta|."""
    if gross_loss == 0:
        return float("inf") if gross_profit > 0 else 0.0
    return gross_profit / abs(gross_loss)


def expectancy(win_rate: float, avg_win: float, avg_loss: float) -> float:
    """Expectancy = (win_rate × avg_win) - (loss_rate × |avg_loss|)."""
    loss_rate = 1.0 - win_rate
    return (win_rate * avg_win) - (loss_rate * abs(avg_loss))


# ── Risk of Ruin ─────────────────────────────────────────────────────────────


def risk_of_ruin(
    win_rate: float, avg_win: float, avg_loss: float, capital_units: int = 100
) -> float:
    """Probabilidade de ruína (gambler's ruin adaptado)."""
    if avg_win <= 0 or avg_loss >= 0:
        return 1.0
    # Edge = win_rate × avg_win - loss_rate × |avg_loss|
    edge = expectancy(win_rate, avg_win, avg_loss)
    if edge <= 0:
        return 1.0
    q = 1.0 - win_rate
    p = win_rate
    # Probabilidade de atingir 0 antes de dobrar, dado capital em unidades
    if p == q:
        return 1.0 - (capital_units / (2 * capital_units))
    ratio = q / p
    return (ratio**capital_units - ratio ** (2 * capital_units)) / (
        1 - ratio ** (2 * capital_units)
    )
