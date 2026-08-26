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
    "FinancialEngine",
    "PennyMomentumConfig",
    "alpha",
    "annualized_return",
    "beta",
    "bollinger",
    "calmar_ratio",
    "clamp",
    "cvar_historic",
    "directional_accuracy",
    # trading losses
    "directional_loss",
    "ema",
    "expectancy",
    "huber_loss",
    "kelly_fraction",
    "kelly_position_size",
    "log_return",
    "macd",
    "max_drawdown",
    "multi_horizon_loss",
    "percentile_rank",
    "profit_factor",
    "quantile_loss",
    "risk_of_ruin",
    "rsi",
    "sharpe_loss",
    "sharpe_ratio",
    # utils
    "sigmoid",
    "simple_return",
    "simulate_penny_momentum_backtest",
    # indicators
    "sma",
    "sortino_ratio",
    "t_conorm",
    "t_norm",
    "var_historic",
    # risk
    "volatility",
    "vwap",
    "vwap_deviation",
    "zscore",
    # F51-dependent modules: import directly from submodules
    # crisis: import from core.math.crisis
]
