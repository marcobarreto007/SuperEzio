"""Tests verifying truth in financial_engine.py indicators — no fabricated defaults."""

from unittest.mock import patch

from core.math.financial_engine import (
    FinancialEngine,
    _compute_bollinger,
    _compute_ema,
    _compute_macd,
    _compute_rsi,
    _compute_stoch,
)


def test_compute_rsi_insufficient_data_returns_none():
    """RSI with fewer than 15 data points must return None, NEVER 50.0."""
    assert _compute_rsi([], 14) is None
    assert _compute_rsi([10.0], 14) is None
    assert _compute_rsi([10.0, 11.0, 12.0], 14) is None


def test_compute_ema_insufficient_data_returns_none():
    """EMA with insufficient data points must return None, NEVER 0.0."""
    assert _compute_ema([], 20) is None
    assert _compute_ema([10.0], 20) is None


def test_compute_macd_insufficient_data_returns_none_tuple():
    """MACD with insufficient data points must return (None, None), NEVER (0.0, 0.0)."""
    line, signal = _compute_macd([10.0, 11.0, 12.0])
    assert line is None
    assert signal is None


def test_compute_bollinger_insufficient_data_returns_none_tuple():
    """Bollinger with fewer than period data points must return (None, None), NEVER (0.0, 0.0)."""
    upper, lower = _compute_bollinger([10.0, 11.0], 20)
    assert upper is None
    assert lower is None


def test_compute_stoch_insufficient_data_returns_none_tuple():
    """Stochastic with fewer than period data points must return (None, None), NEVER (50.0, 50.0)."""
    k, d = _compute_stoch([10.0, 11.0], [9.0, 10.0], [9.5, 10.5], 14)
    assert k is None
    assert d is None


def test_compute_stoch_flat_price_returns_none_tuple():
    """Stochastic when high == low (zero variance) must return (None, None), NEVER 50.0."""
    highs = [10.0] * 15
    lows = [10.0] * 15
    closes = [10.0] * 15
    k, d = _compute_stoch(highs, lows, closes, 14)
    assert k is None
    assert d is None


def test_compute_indicators_sufficient_data_returns_real_floats():
    """When sufficient real data is present, indicators compute real non-None values."""
    import numpy as np

    # 100 prices with variation
    np.random.seed(42)
    prices = [round(float(p), 2) for p in (100.0 + np.cumsum(np.random.randn(60)))]
    highs = [p + 1.0 for p in prices]
    lows = [p - 1.0 for p in prices]

    rsi_val = _compute_rsi(prices, 14)
    assert rsi_val is not None
    assert 0.0 <= rsi_val <= 100.0

    ema_val = _compute_ema(prices, 20)
    assert ema_val is not None
    assert ema_val > 0

    macd_val, signal_val = _compute_macd(prices)
    assert macd_val is not None
    assert signal_val is not None

    upper, lower = _compute_bollinger(prices, 20)
    assert upper is not None and lower is not None
    assert upper > lower

    k, d = _compute_stoch(highs, lows, prices, 14)
    assert k is not None and d is not None
    assert 0.0 <= k <= 100.0


def test_get_market_data_short_history_propagates_none_indicators():
    """FinancialEngine.get_market_data with short candle history returns None for indicators."""
    engine = FinancialEngine()
    short_candles = [
        {
            "time": "2026-09-10",
            "open": 10.0,
            "high": 11.0,
            "low": 9.0,
            "close": 10.5,
            "volume": 1000,
        },
        {
            "time": "2026-09-11",
            "open": 10.5,
            "high": 12.0,
            "low": 10.0,
            "close": 11.5,
            "volume": 1200,
        },
    ]

    with patch("data.data_hub.hub.get_candles", return_value={"candles": short_candles}):
        result = engine.get_market_data("TEST")

    assert result["symbol"] == "TEST"
    assert result["price"] == 11.5
    assert result["rsi_14"] is None
    assert result["macd"] is None
    assert result["macd_signal"] is None
    assert result["ema_20"] is None
    assert result["ema_50"] is None
    assert result["bb_upper"] is None
    assert result["bb_lower"] is None
    assert result["stoch_k"] is None
    assert result["stoch_d"] is None
