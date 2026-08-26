"""Test that MathHub receives OHLCV data from cache-collected data dict.

Regression test for the "0/14 modules skipped with missing_price_series" bug.
Root cause: _try_fast_cache built a data dict WITHOUT the "ohlcv" key, so
MathHub._extract_candles found zero candles and ALL 14 modules were skipped.

Fix: _try_fast_cache now includes "ohlcv" in the returned data dict.
"""

from datetime import UTC, date, timedelta

from core.math.math_hub import MathHub


def _simulate_cache_data():
    """Build a data dict matching what _try_fast_cache now returns.

    Uses a realistic price series with both upward and downward moves so
    Kelly, VaR, and return-based modules can all compute correctly.
    """
    candles = []
    start = date(2026, 1, 1)
    raw_prices = [
        10.00,
        10.05,
        10.12,
        10.08,
        10.15,
        10.22,
        10.18,
        10.25,
        10.30,
        10.28,
        10.35,
        10.40,
        10.32,
        10.38,
        10.45,
        10.50,
        10.42,
        10.48,
        10.55,
        10.60,
        10.52,
        10.58,
        10.65,
        10.70,
        10.62,
        10.68,
        10.75,
        10.80,
        10.72,
        10.78,
    ]
    for i, close in enumerate(raw_prices):
        candles.append(
            {
                "open": close - 0.05,
                "high": close + 0.10,
                "low": close - 0.10,
                "close": close,
                "volume": 100000 + i * 1000,
                "date": (start + timedelta(days=i)).isoformat(),
            }
        )
    # This is the shape _try_fast_cache now returns — includes "ohlcv"
    return {
        "ticker": "AAPL",
        "data": {
            "ticker": "AAPL",
            "price": {"latest": candles[-1]["close"], "source": "learner_24_7_cache"},
            "fundamentals": {"data_quality": "cached"},
            "technicals": {"data_quality": "cached"},
            "risk": {"data_quality": "cached"},
            "ohlcv": candles,  # <-- This was MISSING before the fix
        },
    }


def test_math_hub_with_cache_data_returns_9plus_ok_modules():
    """The cache fix must yield 9+/14 OK modules (same as live ProfessionalCollector)."""
    state = _simulate_cache_data()
    report = MathHub().calculate_all(state)

    assert report["ticker"] == "AAPL"
    assert report["coverage"]["total_modules"] == 14
    assert report["coverage"]["ok_modules"] >= 9, (
        f"Expected >=9 OK modules, got {report['coverage']['ok_modules']}: "
        f"ok={report['coverage']['ok']} skipped={report['coverage']['skipped']}"
    )

    # Core modules that MUST work with OHLCV data
    assert report["modules"]["price_series"]["status"] == "ok"
    assert report["modules"]["technical_indicators"]["status"] == "ok"
    assert report["modules"]["return_metrics"]["status"] == "ok"
    assert report["modules"]["sharpe_sortino"]["status"] == "ok"
    assert report["modules"]["drawdown"]["status"] == "ok"
    assert report["modules"]["var_cvar"]["status"] == "ok"
    assert report["modules"]["return_bootstrap"]["status"] == "ok"

    # Verify actual values are computed (not None/empty)
    numbers = report["numbers"]
    assert numbers["latest_price"] == 10.78
    assert numbers["rsi"] is not None, "RSI must be computed"
    assert numbers["macd"] is not None, "MACD must be computed"
    assert numbers["sharpe"] is not None, "Sharpe must be computed"
    assert numbers["max_drawdown"] is not None, "Max drawdown must be computed"
    assert numbers["var_95"] is not None, "VaR(95%) must be computed"
    assert numbers["volatility"] is not None, "Volatility must be computed"


def test_extract_candles_recognizes_datetime_key():
    """Both yfinance and Finnhub providers use 'datetime' key for timestamps.
    _extract_candles must accept it alongside 'date'/'time'/'timestamp'.
    """
    hub = MathHub()
    candles = hub._extract_candles(
        {
            "ohlcv": [
                {
                    "datetime": "2026-07-20T10:30:00Z",
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.5,
                    "volume": 50000,
                }
            ]
        }
    )
    assert len(candles) == 1
    assert candles[0]["date"] == "2026-07-20T10:30:00Z"
    assert candles[0]["close"] == 100.5


def test_extract_candles_accepts_datetime_object():
    """The yfinance provider stores a datetime object in the 'datetime' key."""
    from datetime import datetime

    hub = MathHub()
    dt = datetime(2026, 7, 20, 10, 30, 0, tzinfo=UTC)
    candles = hub._extract_candles(
        {
            "ohlcv": [
                {
                    "datetime": dt,
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.5,
                    "volume": 50000,
                }
            ]
        }
    )
    assert len(candles) == 1
    # datetime object gets isoformat'd
    assert candles[0]["date"] == "2026-07-20T10:30:00+00:00"
    assert candles[0]["close"] == 100.5
