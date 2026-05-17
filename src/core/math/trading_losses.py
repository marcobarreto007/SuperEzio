"""
Finance-native loss functions for trading models.

Inspired by NeuraLib's approach: losses that capture directional accuracy,
risk-adjusted returns, asymmetric quantile errors, and horizon-weighted forecasts.
Pure Python + numpy — no external ML framework required.
"""

from __future__ import annotations

import math
from typing import Sequence

import numpy as np


# ── Directional Loss ────────────────────────────────────────────────────

def directional_loss(
    y_true: Sequence[float],
    y_pred: Sequence[float],
    wrong_direction_weight: float = 5.0,
) -> float:
    """
    Penalize wrong-direction predictions more heavily than magnitude errors.

    If sign(pred) == sign(true):  loss = (pred - true)^2
    If sign(pred) != sign(true):  loss = wrong_direction_weight * (pred - true)^2

    This forces models to prioritize getting the direction right,
    which is critical for trading decisions.
    """
    if len(y_true) != len(y_pred):
        raise ValueError("y_true and y_pred must have same length")
    if len(y_true) == 0:
        return 0.0

    total = 0.0
    n = len(y_true)
    for t, p in zip(y_true, y_pred):
        err = (p - t) ** 2
        # Same sign (or zero) = correct direction
        if (t >= 0 and p >= 0) or (t <= 0 and p <= 0):
            total += err
        else:
            total += wrong_direction_weight * err
    return total / n


# ── Sharpe Loss (negative Sharpe ratio, minimizable) ─────────────────────

def sharpe_loss(
    returns: Sequence[float],
    annualize: bool = True,
    risk_free_rate: float = 0.0,
    trading_days: int = 252,
    epsilon: float = 1e-8,
) -> float:
    """
    Negative annualized Sharpe ratio — minimizes to maximize risk-adjusted return.

    Returns a value that can be minimized by gradient-based optimizers.
    Standard Sharpe = mean(excess_returns) / std(excess_returns) * sqrt(T).
    This function returns the negative so optimizers can descend.
    """
    if len(returns) < 2:
        return 0.0

    daily_rf = risk_free_rate / trading_days
    excess = [r - daily_rf for r in returns]
    mean_excess = sum(excess) / len(excess)
    std_excess = float(np.std(excess, ddof=1))

    if std_excess < epsilon:
        return 0.0  # risk-free asset

    sharpe = (mean_excess / std_excess)
    if annualize:
        sharpe *= math.sqrt(trading_days)

    return -sharpe  # negative for minimization


# ── Quantile Loss (Pinball Loss) ────────────────────────────────────────

def quantile_loss(
    y_true: Sequence[float],
    y_pred: Sequence[float],
    tau: float = 0.05,
) -> float:
    """
    Pinball / quantile loss for asymmetric prediction errors.

    Used for Value-at-Risk (VaR) and expectile regression.
    tau=0.05 penalizes underestimation more (lower tail, VaR 95%).
    tau=0.95 penalizes overestimation more (upper tail).

    loss = max(tau * error, (tau - 1) * error)
    """
    if len(y_true) != len(y_pred):
        raise ValueError("y_true and y_pred must have same length")
    if len(y_true) == 0:
        return 0.0

    total = 0.0
    for t, p in zip(y_true, y_pred):
        error = t - p
        if error >= 0:
            total += tau * error
        else:
            total += (tau - 1.0) * error
    return total / len(y_true)


# ── Multi-Horizon Weighted Loss ─────────────────────────────────────────

def multi_horizon_loss(
    y_true: float,
    y_pred_horizons: Sequence[float],
    decay: float = 0.85,
    horizon_weights: Sequence[float] | None = None,
) -> float:
    """
    Weighted MSE across forecast horizons with exponential decay.

    Closer horizons get higher weight. Useful for models that predict
    returns at h=1,2,3,... steps ahead.

    If horizon_weights is provided, uses those directly instead of decay.
    """
    if len(y_pred_horizons) == 0:
        return 0.0

    if horizon_weights is not None:
        if len(horizon_weights) != len(y_pred_horizons):
            raise ValueError("horizon_weights must match y_pred_horizons length")
        weights = list(horizon_weights)
    else:
        weights = [decay ** i for i in range(len(y_pred_horizons))]

    total_weight = sum(weights)
    if total_weight == 0:
        return 0.0

    total = sum(
        w * (p - y_true) ** 2 for w, p in zip(weights, y_pred_horizons)
    )
    return total / total_weight


# ── Huber Loss ──────────────────────────────────────────────────────────

def huber_loss(
    y_true: Sequence[float],
    y_pred: Sequence[float],
    delta: float = 1.0,
) -> float:
    """
    Robust Huber loss — quadratic for small errors, linear for large ones.

    Reduces the influence of outliers compared to pure MSE.
    """
    if len(y_true) != len(y_pred):
        raise ValueError("y_true and y_pred must have same length")
    if len(y_true) == 0:
        return 0.0

    total = 0.0
    for t, p in zip(y_true, y_pred):
        err = abs(t - p)
        if err <= delta:
            total += 0.5 * err ** 2
        else:
            total += delta * (err - 0.5 * delta)
    return total / len(y_true)


# ── Directional Accuracy (metric, not loss) ─────────────────────────────

def directional_accuracy(
    y_true: Sequence[float],
    y_pred: Sequence[float],
) -> float:
    """
    Fraction of predictions that match the sign of the true value.

    Returns value in [0, 1]. Higher is better.
    """
    if len(y_true) != len(y_pred):
        raise ValueError("y_true and y_pred must have same length")
    if len(y_true) == 0:
        return 0.0

    correct = sum(
        1 for t, p in zip(y_true, y_pred)
        if (t >= 0 and p >= 0) or (t <= 0 and p <= 0)
    )
    return correct / len(y_true)
