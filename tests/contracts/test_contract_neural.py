"""Contract tests for NeuralDecisionExpert pipeline node."""

import src.core.pipeline.nodes.neural_decision as neural_node
from src.core.pipeline.nodes.neural_decision import (
    _build_context,
    _build_features,
    node_neural_decision,
)


def _noop_writer(_event: dict) -> None:
    return None


# ---------------------------------------------------------------------------
# Feature extraction
# ---------------------------------------------------------------------------


def test_build_features_with_technicals():
    data = {
        "technicals": {
            "price": 150.0,
            "rsi_14": 65.0,
            "ema_20": 145.0,
            "ema_50": 140.0,
            "bb_upper": 160.0,
            "bb_lower": 140.0,
            "volume": 5_000_000,
            "macd": 2.0,
            "macd_signal": 1.5,
        }
    }
    result = _build_features(data)
    assert isinstance(result, dict)
    assert "rsi_14" in result
    assert result["rsi_14"] == 65.0
    assert "return_1" in result
    assert -1.0 <= result["return_1"] <= 1.0
    assert "atr_pct" in result
    assert 0.0 <= result["atr_pct"] <= 1.0
    assert "volatility_regime" in result
    assert result["volatility_regime"] in ("low", "normal", "high", "extreme")
    assert "liquidity_sweep" in result
    assert isinstance(result["liquidity_sweep"], bool)


def test_build_features_empty_data():
    """Empty data must produce safe defaults, not crash."""
    result = _build_features({})
    assert isinstance(result, dict)
    assert result["rsi_14"] == 50.0
    assert result["return_1"] == 0.0
    assert -1.0 <= result["return_1"] <= 1.0


def test_build_features_with_price_fallback():
    """Features should use price from price key when technicals lacks it."""
    data = {
        "price": {"price": 200.0},
        "technicals": {"rsi_14": 55.0},
    }
    result = _build_features(data)
    assert result["rsi_14"] == 55.0
    # price is used internally; verify no crash
    assert "return_1" in result


# ---------------------------------------------------------------------------
# Context building
# ---------------------------------------------------------------------------


def test_build_context_with_macro_and_sentiment():
    data = {
        "macro": {
            "treasury": {"fed_funds": 5.25, "10y": 4.5},
            "data_quality": "partial",
        },
        "sentiment": {"sentiment_label": "bullish"},
    }
    pennylab = {
        "scores": {"whale_suspicion": 0.1, "pump_probability": 0.2, "trap_risk": 0.1}
    }
    result = _build_context(data, pennylab)
    assert isinstance(result, dict)
    assert result["news_sentiment"] == "bullish"
    assert result["macro_risk"] in ("neutral", "unknown", "high")
    assert "fraud_risk" in result
    assert 0.0 <= result["fraud_risk"] <= 1.0
    assert "veracity_score" in result


def test_build_context_empty():
    """Empty data must produce safe defaults."""
    result = _build_context({}, {})
    assert isinstance(result, dict)
    assert result["macro_risk"] == "neutral"
    assert result["news_sentiment"] == "neutral"
    assert result["fraud_risk"] == 0.0


def test_build_context_bearish_sentiment():
    data = {"sentiment": {"label": "bearish"}}
    result = _build_context(data, {})
    assert result["news_sentiment"] == "bearish"


# ---------------------------------------------------------------------------
# Node: no ticker (skip path)
# ---------------------------------------------------------------------------


def test_node_neural_decision_no_ticker():
    """Neural decision must skip when no ticker present."""
    import asyncio

    neural_node.get_stream_writer = lambda: _noop_writer

    async def _run():
        return await node_neural_decision(
            {"message": "no ticker", "route": "market_scan", "run_id": "test-neural-1"}
        )

    result = asyncio.run(_run())
    # Should return empty when no ticker
    assert isinstance(result, dict)
    assert "neural_decision" not in result
    assert "errors" not in result
