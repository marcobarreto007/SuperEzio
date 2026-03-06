"""
MathCore — DEPRECATED. Use `from core.math import ...` instead.

Este módulo existe apenas para compatibilidade reversa.
Todo código novo deve importar de `core.math`.
"""

# Re-export from canonical math package (import leaf modules to avoid circular imports)
from core.math.utils import sigmoid, clamp, t_norm, t_conorm, percentile_rank, zscore
from core.math.indicators import sma, ema, rsi, macd, bollinger, vwap, vwap_deviation
from core.math.risk import (
    log_return,
    simple_return,
    annualized_return,
    volatility,
    sharpe_ratio,
    sortino_ratio,
    max_drawdown,
    calmar_ratio,
    beta,
    alpha,
    var_historic,
    cvar_historic,
    kelly_fraction,
    kelly_position_size,
    profit_factor,
    expectancy,
    risk_of_ruin,
    TRADING_DAYS_YEAR,
)

# Keep base.py importable for backward compat
from . import base  # noqa: F401

__all__ = [
    "sigmoid",
    "clamp",
    "t_norm",
    "t_conorm",
    "percentile_rank",
    "zscore",
    "sma",
    "ema",
    "rsi",
    "macd",
    "bollinger",
    "vwap",
    "vwap_deviation",
    "log_return",
    "simple_return",
    "annualized_return",
    "volatility",
    "sharpe_ratio",
    "sortino_ratio",
    "max_drawdown",
    "calmar_ratio",
    "beta",
    "alpha",
    "var_historic",
    "cvar_historic",
    "kelly_fraction",
    "kelly_position_size",
    "profit_factor",
    "expectancy",
    "risk_of_ruin",
    "TRADING_DAYS_YEAR",
    "base",
]
