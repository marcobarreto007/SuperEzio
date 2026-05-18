"""
Métricas de risco canônicas.

Importadas de core.mathcore.base e unificadas das duplicatas em:
- core/agent_runtime/financial_suite/logic/risk_calculator.py
- core/mathcore/base.py
"""

from __future__ import annotations
import math
from typing import Sequence
import numpy as np
from .utils import clamp

TRADING_DAYS_YEAR = 252


def log_return(current: float, previous: float) -> float:
    if previous <= 0:
        return 0.0
    return math.log(current / previous)


def simple_return(current: float, previous: float) -> float:
    if previous == 0:
        return 0.0
    return (current - previous) / previous


def annualized_return(daily_returns: Sequence[float]) -> float:
    if not daily_returns:
        return 0.0
    return (sum(daily_returns) / len(daily_returns)) * TRADING_DAYS_YEAR


def volatility(daily_returns: Sequence[float], annualize: bool = True) -> float:
    if len(daily_returns) < 2:
        return 0.0
    std = float(np.std(daily_returns, ddof=1))
    return std * math.sqrt(TRADING_DAYS_YEAR) if annualize else std


def sharpe_ratio(daily_returns: Sequence[float], risk_free_rate: float = 0.0) -> float:
    if len(daily_returns) < 2:
        return 0.0
    excess = [r - risk_free_rate / TRADING_DAYS_YEAR for r in daily_returns]
    mean_excess = sum(excess) / len(excess)
    std_excess = float(np.std(excess, ddof=1))
    if std_excess == 0:
        return 0.0
    return (mean_excess / std_excess) * math.sqrt(TRADING_DAYS_YEAR)


def sortino_ratio(daily_returns: Sequence[float], risk_free_rate: float = 0.0) -> float:
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
    if max_dd >= 0 or max_dd == 0:
        return 0.0
    return annual_return / abs(max_dd)


def beta(asset_returns: Sequence[float], market_returns: Sequence[float]) -> float:
    if len(asset_returns) != len(market_returns) or len(asset_returns) < 2:
        return 1.0
    cov = np.cov(asset_returns, market_returns)[0][1]
    var_market = np.var(market_returns, ddof=1)
    if var_market == 0:
        return 1.0
    return float(cov / var_market)


def alpha(annual_return: float, beta: float, market_return: float, risk_free: float = 0.0) -> float:
    return annual_return - (risk_free + beta * (market_return - risk_free))


def var_historic(returns: Sequence[float], confidence: float = 0.95) -> float:
    if not returns:
        return 0.0
    sorted_r = sorted(returns)
    idx = int((1.0 - confidence) * len(sorted_r))
    return sorted_r[max(0, idx)]


def cvar_historic(returns: Sequence[float], confidence: float = 0.95) -> float:
    if not returns:
        return 0.0
    var = var_historic(returns, confidence)
    tail = [r for r in returns if r <= var]
    return sum(tail) / len(tail) if tail else var


def kelly_fraction(win_prob: float, win_loss_ratio: float) -> float:
    if win_loss_ratio <= 0:
        return 0.0
    q = 1.0 - win_prob
    f = (win_prob * win_loss_ratio - q) / win_loss_ratio
    return clamp(f, 0.0, 1.0)


def kelly_position_size(
    win_prob: float, win_loss_ratio: float, capital: float, max_fraction: float = 0.25
) -> float:
    f = kelly_fraction(win_prob, win_loss_ratio)
    return capital * min(f, max_fraction)


def profit_factor(gross_profit: float, gross_loss: float) -> float:
    if gross_loss == 0:
        return float("inf") if gross_profit > 0 else 0.0
    return gross_profit / abs(gross_loss)


def expectancy(win_rate: float, avg_win: float, avg_loss: float) -> float:
    return (win_rate * avg_win) - ((1.0 - win_rate) * abs(avg_loss))


def risk_of_ruin(
    win_rate: float, avg_win: float, avg_loss: float, capital_units: int = 100
) -> float:
    if avg_win <= 0 or avg_loss >= 0:
        return 1.0
    edge = expectancy(win_rate, avg_win, avg_loss)
    if edge <= 0:
        return 1.0
    q = 1.0 - win_rate
    p = win_rate
    if p == q:
        return 1.0 - (capital_units / (2 * capital_units))
    ratio = q / p
    return (ratio**capital_units - ratio ** (2 * capital_units)) / (
        1 - ratio ** (2 * capital_units)
    )
