"""
Normalization utilities for CrisisMathExpert.

percentile_rank importado de core.math.utils.
clamp mantido local com range 0-100 (convenção do crisis).
"""

from core.math.utils import percentile_rank as _mathcore_percentile_rank


def clamp(value: float, min_value: float = 0.0, max_value: float = 100.0) -> float:
    return max(min_value, min(value, max_value))


def minmax_score(value: float, low: float, high: float, invert: bool = False) -> float:
    if high <= low:
        return 100.0 if not invert else 0.0
    score = ((value - low) / (high - low)) * 100.0
    score = clamp(score)
    return 100.0 - score if invert else score


def zscore_to_risk(z: float) -> float:
    # 0 -> 50, +2 -> ~90, -2 -> ~10
    from scipy.stats import norm

    try:
        pct = norm.cdf(z)
        return clamp(pct * 100.0)
    except ImportError:
        # Fallback if scipy not available
        val = 50 + (z * 20)
        return clamp(val)


def percentile_rank(values: list[float], current: float) -> float:
    """Wrapper que adapta a assinatura do mathcore para o crisis."""
    if not values:
        return 50.0
    return _mathcore_percentile_rank(values, current)
