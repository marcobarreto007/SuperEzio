"""
SuperEzio Math Core — código matemático canônico e unificado.

Organizado por domínio:
- utils.py       → sigmoid, clamp, t_norm, t_conorm, normalize, zscore
- indicators.py → SMA, EMA, RSI, MACD, Bollinger, VWAP
- risk.py        → VaR, CVaR, Sharpe, Sortino, drawdown, Kelly, beta, alpha
- f51_formulas.py → unified_decision, combined_risk, proxy_reward, heuristic_uncertainty
- gates.py       → VeracityGate, AdversarialCritic
- scoring.py     → PlatinumScorer, RiskEngine
- detectors.py  → SpiderSense, DifficultyEstimator
- crisis.py      → 12 modelos CrisisMath + ensemble + normalization + scoring
"""

from .financial_engine import FinancialEngine
from .indicators import bollinger, ema, macd, rsi, sma, vwap, vwap_deviation
from .penny_momentum import PennyMomentumConfig, simulate_penny_momentum_backtest
from .risk import (
    alpha,
    annualized_return,
    beta,
    calmar_ratio,
    cvar_historic,
    expectancy,
    kelly_fraction,
    kelly_position_size,
    log_return,
    max_drawdown,
    profit_factor,
    risk_of_ruin,
    sharpe_ratio,
    simple_return,
    sortino_ratio,
    var_historic,
    volatility,
)
from .trading_losses import (
    directional_accuracy,
    directional_loss,
    huber_loss,
    multi_horizon_loss,
    quantile_loss,
    sharpe_loss,
)
from .utils import clamp, percentile_rank, sigmoid, t_conorm, t_norm, zscore

__all__ = [
    # utils
    "sigmoid",
    "clamp",
    "t_norm",
    "t_conorm",
    "percentile_rank",
    "zscore",
    # indicators
    "sma",
    "ema",
    "rsi",
    "macd",
    "bollinger",
    "vwap",
    "vwap_deviation",
    # risk
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
    "risk_of_ruin",
    "profit_factor",
    "expectancy",
    "log_return",
    "simple_return",
    "annualized_return",
    "FinancialEngine",
    "PennyMomentumConfig",
    "simulate_penny_momentum_backtest",
    # trading losses
    "directional_loss",
    "sharpe_loss",
    "quantile_loss",
    "multi_horizon_loss",
    "huber_loss",
    "directional_accuracy",
    # F51-dependent modules: import directly from submodules
    # crisis: import from core.math.crisis
]
