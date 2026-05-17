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

from .utils import sigmoid, clamp, t_norm, t_conorm, percentile_rank, zscore
from .indicators import sma, ema, rsi, macd, bollinger, vwap, vwap_deviation
from .financial_engine import FinancialEngine
from .risk import (
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
    risk_of_ruin,
    profit_factor,
    expectancy,
    log_return,
    simple_return,
    annualized_return,
)
from .trading_losses import (
    directional_loss,
    sharpe_loss,
    quantile_loss,
    multi_horizon_loss,
    huber_loss,
    directional_accuracy,
)

# F51-dependent modules are NOT eagerly imported to avoid circular imports.
# Import directly from submodules:
#   from core.math.f51_formulas import FormulaWeights
#   from core.math.gates import VeracityGate
#   from core.math.scoring import PlatinumScorer
#   from core.math.detectors import SpiderSense
#   from core.math.crisis import crisis_evaluate

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
