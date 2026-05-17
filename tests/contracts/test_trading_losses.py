"""Contract tests for core.math.trading_losses — finance-native loss functions."""

import math

import pytest


# ── directional_loss ────────────────────────────────────────────────────

def test_directional_loss_perfect_same_sign():
    from core.math.trading_losses import directional_loss

    y_true = [1.0, 2.0, 3.0]
    y_pred = [1.1, 2.1, 3.1]
    loss = directional_loss(y_true, y_pred)
    assert loss > 0
    assert loss < 0.02  # small magnitude error, correct direction


def test_directional_loss_wrong_direction_heavier():
    from core.math.trading_losses import directional_loss

    # Same magnitude error, opposite sign -> much higher loss
    same_sign = directional_loss([1.0], [1.5], wrong_direction_weight=5.0)
    opposite_sign = directional_loss([1.0], [-1.5], wrong_direction_weight=5.0)
    assert opposite_sign > same_sign * 4  # wrong direction penalty


def test_directional_loss_zero_inputs():
    from core.math.trading_losses import directional_loss

    # Zero is same direction as zero (both >= 0)
    loss = directional_loss([0.0], [0.0])
    assert loss == 0.0


def test_directional_loss_empty():
    from core.math.trading_losses import directional_loss

    assert directional_loss([], []) == 0.0


def test_directional_loss_mismatched_length():
    from core.math.trading_losses import directional_loss

    with pytest.raises(ValueError):
        directional_loss([1.0, 2.0], [1.0])


# ── sharpe_loss ─────────────────────────────────────────────────────────

def test_sharpe_loss_positive_returns():
    from core.math.trading_losses import sharpe_loss

    # Positive returns with slight variation -> positive Sharpe -> negative loss
    returns = [0.01 + i * 0.0001 for i in range(100)]
    loss = sharpe_loss(returns, annualize=False)
    assert loss < 0  # negative because Sharpe is positive


def test_sharpe_loss_zero_volatility():
    from core.math.trading_losses import sharpe_loss

    # Flat returns -> zero Sharpe -> zero loss
    returns = [0.0] * 100
    loss = sharpe_loss(returns)
    assert loss == 0.0


def test_sharpe_loss_negative_returns():
    from core.math.trading_losses import sharpe_loss

    # Negative returns with variation -> negative Sharpe -> positive loss
    returns = [-0.01 + i * 0.0001 for i in range(100)]
    loss = sharpe_loss(returns, annualize=False)
    assert loss > 0  # positive because Sharpe is negative


def test_sharpe_loss_insufficient_data():
    from core.math.trading_losses import sharpe_loss

    assert sharpe_loss([]) == 0.0
    assert sharpe_loss([0.01]) == 0.0


# ── quantile_loss ───────────────────────────────────────────────────────

def test_quantile_loss_lower_tail():
    from core.math.trading_losses import quantile_loss

    # tau=0.05 (VaR lower tail): overestimation is dangerous
    # (predicting the tail is less bad than it really is)
    pred_low = quantile_loss([1.0], [0.8], tau=0.05)   # pred too low (conservative)
    pred_high = quantile_loss([1.0], [1.2], tau=0.05)   # pred too high (dangerous)
    assert pred_high > pred_low  # overestimation penalized more


def test_quantile_loss_upper_tail():
    from core.math.trading_losses import quantile_loss

    # tau=0.95 (upper tail): underestimation is more penalized
    pred_high = quantile_loss([1.0], [1.2], tau=0.95)   # pred too high
    pred_low = quantile_loss([1.0], [0.8], tau=0.95)     # pred too low
    assert pred_low > pred_high  # underestimation penalized more


def test_quantile_loss_perfect():
    from core.math.trading_losses import quantile_loss

    assert quantile_loss([1.0], [1.0], tau=0.5) == 0.0


def test_quantile_loss_empty():
    from core.math.trading_losses import quantile_loss

    assert quantile_loss([], []) == 0.0


# ── multi_horizon_loss ──────────────────────────────────────────────────

def test_multi_horizon_loss_decay():
    from core.math.trading_losses import multi_horizon_loss

    # Near horizon (index 0) has higher weight than far horizon
    loss = multi_horizon_loss(
        y_true=1.0, y_pred_horizons=[1.5, 1.5, 1.5], decay=0.85
    )
    assert loss > 0


def test_multi_horizon_loss_custom_weights():
    from core.math.trading_losses import multi_horizon_loss

    loss = multi_horizon_loss(
        y_true=1.0,
        y_pred_horizons=[1.2, 1.4, 1.6],
        horizon_weights=[0.6, 0.3, 0.1],
    )
    assert loss > 0


def test_multi_horizon_loss_perfect():
    from core.math.trading_losses import multi_horizon_loss

    loss = multi_horizon_loss(
        y_true=1.0, y_pred_horizons=[1.0, 1.0, 1.0]
    )
    assert loss == 0.0


def test_multi_horizon_loss_empty():
    from core.math.trading_losses import multi_horizon_loss

    assert multi_horizon_loss(1.0, []) == 0.0


# ── huber_loss ──────────────────────────────────────────────────────────

def test_huber_loss_small_error_quadratic():
    from core.math.trading_losses import huber_loss

    # Small error (< delta=1.0): quadratic behavior
    loss = huber_loss([0.0], [0.1], delta=1.0)
    expected = 0.5 * 0.1**2  # 0.005
    assert abs(loss - expected) < 1e-10


def test_huber_loss_large_error_linear():
    from core.math.trading_losses import huber_loss

    # Large error (> delta=1.0): linear behavior
    loss = huber_loss([0.0], [3.0], delta=1.0)
    expected = 1.0 * (3.0 - 0.5)  # 2.5
    assert abs(loss - expected) < 1e-10


def test_huber_loss_equals_mse_when_small():
    from core.math.trading_losses import huber_loss

    # When all errors < delta, huber = 0.5 * MSE
    mse = sum((p - t) ** 2 for t, p in zip([1.0, 2.0], [1.1, 2.1])) / 2
    huber = huber_loss([1.0, 2.0], [1.1, 2.1], delta=10.0)
    assert abs(huber - 0.5 * mse) < 1e-10


def test_huber_loss_empty():
    from core.math.trading_losses import huber_loss

    assert huber_loss([], []) == 0.0


# ── directional_accuracy ────────────────────────────────────────────────

def test_directional_accuracy_perfect():
    from core.math.trading_losses import directional_accuracy

    assert directional_accuracy([1.0, 2.0], [0.5, 3.0]) == 1.0


def test_directional_accuracy_half():
    from core.math.trading_losses import directional_accuracy

    acc = directional_accuracy([1.0, -1.0], [1.0, 1.0])  # second is wrong
    assert acc == 0.5


def test_directional_accuracy_zero():
    from core.math.trading_losses import directional_accuracy

    # Zero predictions match zero and positive targets
    acc = directional_accuracy([0.0, 0.0], [0.0, 0.0])
    assert acc == 1.0


# ── Integration: losses work together ───────────────────────────────────

def test_pipeline_realistic_scenario():
    """Simulate a realistic trading model evaluation."""
    from core.math.trading_losses import (
        directional_accuracy,
        directional_loss,
        huber_loss,
        quantile_loss,
        sharpe_loss,
    )

    # 20 days of daily return predictions vs actual
    y_true = [0.005, -0.003, 0.002, 0.008, -0.001] * 4
    y_pred = [0.004, -0.002, 0.003, 0.006, 0.001] * 4

    # All metrics should produce finite numbers
    d_loss = directional_loss(y_true, y_pred)
    s_loss = sharpe_loss(y_pred)
    q_loss = quantile_loss(y_true, y_pred, tau=0.05)
    h_loss = huber_loss(y_true, y_pred)
    d_acc = directional_accuracy(y_true, y_pred)

    assert math.isfinite(d_loss)
    assert math.isfinite(s_loss)
    assert math.isfinite(q_loss)
    assert math.isfinite(h_loss)
    assert 0.0 <= d_acc <= 1.0
    assert d_loss > 0  # imperfect predictions
