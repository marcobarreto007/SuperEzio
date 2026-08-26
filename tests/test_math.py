"""Smoke tests — core math functions (puras, deterministicas)."""

import math
from typing import ClassVar

import pytest

from core.math.indicators import (
    bollinger,
    calc_macd,
    calc_rsi,
    ema,
    macd,
    rsi,
    sma,
    vwap,
    vwap_deviation,
)
from core.math.risk import (
    annualized_return,
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
from core.math.utils import clamp, percentile_rank, sigmoid, t_conorm, t_norm, zscore


class TestUtils:
    def test_sigmoid_zero(self):
        assert sigmoid(0.0) == 0.5

    def test_sigmoid_symmetric(self):
        # sigmoid(x) + sigmoid(-x) == 1
        for x in (0.5, 1.0, 2.0, 5.0):
            assert math.isclose(sigmoid(x) + sigmoid(-x), 1.0, rel_tol=1e-9)

    def test_sigmoid_monotonic(self):
        vals = [sigmoid(x) for x in (-5, -2, 0, 2, 5)]
        assert vals == sorted(vals)

    def test_clamp_default(self):
        assert clamp(0.5) == 0.5
        assert clamp(-0.1) == 0.0
        assert clamp(1.5) == 1.0

    def test_clamp_custom(self):
        assert clamp(5, lo=10, hi=20) == 10
        assert clamp(25, lo=10, hi=20) == 20

    def test_t_norm(self):
        assert t_norm(0.5, 0.5) == 0.25
        assert t_norm(1.0, 1.0) == 1.0
        assert t_norm(0.0, 0.5) == 0.0

    def test_t_conorm(self):
        assert t_conorm(0.5, 0.5) == 0.75
        assert t_conorm(0.0, 1.0) == 1.0
        assert t_conorm(0.0, 0.0) == 0.0

    def test_percentile_rank_empty(self):
        assert percentile_rank([], 5.0) == 50.0

    def test_percentile_rank_normal(self):
        result = percentile_rank([1, 2, 3, 4, 5], 3)
        assert 0.0 <= result <= 100.0

    def test_zscore_normal(self):
        assert zscore(10, mean=5, std=2) == 2.5

    def test_zscore_zero_std(self):
        assert zscore(5, mean=5, std=0) == 0.0


class TestIndicators:
    PRICES: ClassVar[list[float]] = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0]

    def test_sma_ok(self):
        result = sma(self.PRICES, period=3)
        assert result == pytest.approx(18.0, rel=0.01)

    def test_sma_insufficient(self):
        assert sma(self.PRICES, period=20) is None

    def test_ema_ok(self):
        result = ema(self.PRICES, period=3)
        assert result is not None
        assert result > 0

    def test_ema_insufficient(self):
        assert ema(self.PRICES, period=20) is None

    def test_rsi_ok(self):
        result = rsi(self.PRICES, period=3)
        assert result is not None
        assert 0 <= result <= 100

    def test_rsi_all_up(self):
        # 10 consecutive up days -> RSI ~100
        result = rsi(list(range(1, 20)), period=3)
        assert result is not None
        assert result > 90

    def test_wilder_rsi_is_prefix_invariant(self):
        prices = [100 + ((i % 7) - 3) * 0.7 + i * 0.05 for i in range(80)]
        full = calc_rsi(prices, period=14)
        for prefix_length in range(15, len(prices) + 1):
            assert calc_rsi(prices[:prefix_length], period=14) == full[:prefix_length]

    def test_wilder_rsi_known_reference_sequence(self):
        prices = [
            44.34,
            44.09,
            44.15,
            43.61,
            44.33,
            44.83,
            45.10,
            45.42,
            45.84,
            46.08,
            45.89,
            46.03,
            45.61,
            46.28,
            46.28,
        ]
        assert calc_rsi(prices, period=14)[-1] == pytest.approx(70.46, abs=0.01)

    def test_macd_ok(self):
        result = macd(self.PRICES)
        assert isinstance(result, dict)
        assert "macd" in result

    def test_macd_signal_is_real_ema9_and_prefix_invariant(self):
        prices = [100 + i * 0.3 + math.sin(i / 3) for i in range(80)]
        full = calc_macd(prices)
        assert full["signal"][32] is None
        assert full["signal"][33] is not None
        first_nine = [value for value in full["macd"] if value is not None][:9]
        assert full["signal"][33] == pytest.approx(sum(first_nine) / 9, abs=1e-4)
        for prefix_length in range(34, len(prices) + 1):
            prefix = calc_macd(prices[:prefix_length])
            for name in ("macd", "signal", "histogram"):
                assert prefix[name] == full[name][:prefix_length]

    def test_scalar_macd_matches_latest_series_values(self):
        prices = [100 + i * 0.2 + math.sin(i / 2) for i in range(60)]
        scalar = macd(prices)
        series = calc_macd(prices)
        assert scalar["macd"] == pytest.approx(series["macd"][-1], abs=1e-4)
        assert scalar["signal"] == pytest.approx(series["signal"][-1], abs=1e-4)
        assert scalar["histogram"] == pytest.approx(series["histogram"][-1], abs=1e-4)

    def test_bollinger_ok(self):
        result = bollinger(self.PRICES)
        assert isinstance(result, dict)
        assert "upper" in result and "lower" in result and "middle" in result

    def test_vwap_ok(self):
        vols = [1000] * len(self.PRICES)
        result = vwap(self.PRICES, vols)
        assert result is not None
        assert result > 0

    def test_vwap_mismatch(self):
        assert vwap(self.PRICES, [1000]) is None

    def test_vwap_deviation(self):
        # Returns fractional deviation (0-1), not percentage
        dev = vwap_deviation(20, 15)
        assert dev >= 0
        assert dev == pytest.approx(0.333, rel=0.1)


class TestRisk:
    RETURNS: ClassVar[list[float]] = [0.01, -0.02, 0.03, 0.01, -0.005, 0.02, -0.01, 0.015, 0.025, -0.015]

    def test_log_return(self):
        assert log_return(110, 100) == pytest.approx(0.0953, rel=0.01)
        assert log_return(100, 0) == 0.0
        assert log_return(100, -1) == 0.0

    def test_simple_return(self):
        assert simple_return(110, 100) == 0.1

    def test_annualized_return(self):
        r = annualized_return(self.RETURNS)
        assert isinstance(r, float)

    def test_volatility(self):
        v = volatility(self.RETURNS, annualize=True)
        assert v > 0

    def test_sharpe_ratio(self):
        sr = sharpe_ratio(self.RETURNS)
        assert isinstance(sr, float)

    def test_sortino_ratio(self):
        sr = sortino_ratio(self.RETURNS)
        assert isinstance(sr, float)

    def test_max_drawdown_empty(self):
        assert max_drawdown([]) == 0.0

    def test_max_drawdown_normal(self):
        # Returns fractional drawdown (negative), e.g. -0.3 = 30% drop
        dd = max_drawdown([100, 90, 80, 95, 70])
        assert dd < 0
        assert dd == pytest.approx(-0.3, rel=0.05)

    def test_var_historic(self):
        v = var_historic(self.RETURNS, confidence=0.95)
        assert v < 0  # VaR should be negative (loss)

    def test_cvar_historic(self):
        v = cvar_historic(self.RETURNS, confidence=0.95)
        assert v < 0

    def test_kelly_fraction(self):
        k = kelly_fraction(win_prob=0.6, win_loss_ratio=1.5)
        assert 0 <= k <= 1

    def test_kelly_position_size(self):
        size = kelly_position_size(0.6, 1.5, capital=100000)
        assert size > 0

    def test_profit_factor(self):
        pf = profit_factor(gross_profit=10000, gross_loss=5000)
        assert pf == 2.0
        assert profit_factor(0, 0) == 0.0

    def test_expectancy(self):
        e = expectancy(win_rate=0.5, avg_win=200, avg_loss=100)
        assert e == 50.0

    def test_risk_of_ruin(self):
        ror = risk_of_ruin(0.5, avg_win=200, avg_loss=100)
        assert 0 <= ror <= 1
