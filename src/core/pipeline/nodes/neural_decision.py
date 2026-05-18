"""NeuralDecisionExpert pipeline node — directional forecast + regime detection."""

from __future__ import annotations

from collections import deque
from typing import Any

from langgraph.config import get_stream_writer

# Module-level dedup: when collect_experts is triggered by both converging
# branches (pennylab + f51→experts), this node may be invoked twice before
# either execution writes to state. A deque guard catches what the state
# guard misses.
_NEURAL_SEEN: deque[str] = deque(maxlen=64)


async def node_neural_decision(state: dict) -> dict:
    """Run NeuralDecisionExpert on collected data and feed verdict to CEO prompt.

    Extracts features from collected technicals/price data, context from
    macro/sentiment/fraud modules, and produces directional probability,
    expected return, drawdown risk, regime classification, and veto flag.
    """
    writer = get_stream_writer()
    run_id = state.get("run_id", "")
    ticker = state.get("ticker", "")
    route = state.get("route", "general")

    # Module-level guard — catches parallel double-invocation where state
    # hasn't been written yet by the concurrent execution.
    dedup_key = f"neural_{run_id}"
    if dedup_key in _NEURAL_SEEN:
        writer(
            {
                "type": "PIPELINE_STEP",
                "run_id": run_id,
                "step": "neural_decision",
                "status": "skipped_duplicate",
            }
        )
        return {}
    _NEURAL_SEEN.append(dedup_key)

    if route != "ticker_analysis" or not ticker:
        writer(
            {
                "type": "PIPELINE_STEP",
                "run_id": run_id,
                "step": "neural_decision",
                "status": "skipped",
            }
        )
        return {}

    data = state.get("data") or {}
    pennylab = state.get("pennylab") or state.get("pennylab_result") or {}

    writer(
        {
            "type": "PIPELINE_STEP",
            "run_id": run_id,
            "step": "neural_decision",
            "status": "started",
            "ticker": ticker,
        }
    )

    try:
        from experts.neural_decision import NeuralDecisionExpert

        features = _build_features(data)
        context = _build_context(data, pennylab)
        timeframe = state.get("time_horizon") or "14 days"

        expert = NeuralDecisionExpert()
        result = expert.predict(ticker, timeframe, features, context)

        writer(
            {
                "type": "NEURAL_DECISION",
                "symbol": ticker,
                "timeframe": timeframe,
                "direction_prob": result.get("direction_prob"),
                "expected_return": result.get("expected_return"),
                "drawdown_risk": result.get("drawdown_risk"),
                "uncertainty": result.get("uncertainty"),
                "regime": result.get("regime"),
                "recommendation": result.get("recommendation"),
                "veto": result.get("veto"),
            }
        )

        writer(
            {
                "type": "PIPELINE_STEP",
                "run_id": run_id,
                "step": "neural_decision",
                "status": "completed",
            }
        )

        return {"neural_decision": result}

    except Exception as exc:
        writer(
            {
                "type": "ERROR",
                "run_id": run_id,
                "detail": f"neural_decision: {exc}",
            }
        )
        writer(
            {
                "type": "PIPELINE_STEP",
                "run_id": run_id,
                "step": "neural_decision",
                "status": "error",
            }
        )
        return {
            "neural_decision": {"error": str(exc)[:200]},
            "errors": state.get("errors", []) + [f"neural_decision:{exc}"],
        }


def _build_features(data: dict[str, Any]) -> dict[str, Any]:
    """Extract technical features from collected data for NeuralDecisionExpert."""
    technicals = data.get("technicals", {})
    price_data = data.get("price", {})

    price = float(
        technicals.get("price")
        or price_data.get("price")
        or data.get("realtime_price", {}).get("price")
        or 0
    )
    rsi = float(technicals.get("rsi_14", 50.0))
    ema21 = float(technicals.get("ema_20", price))
    bb_upper = float(technicals.get("bb_upper", 0))
    bb_lower = float(technicals.get("bb_lower", 0))
    volume = float(technicals.get("volume", 0))

    # Derived features with safe defaults
    price_vs_ema21 = ((price - ema21) / ema21) if ema21 and ema21 > 0 else 0.0
    price_vs_ema21 = max(-1.0, min(1.0, price_vs_ema21))

    # Bollinger bandwidth as volatility proxy
    if bb_upper and bb_lower and price > 0:
        atr_pct = (bb_upper - bb_lower) / price
    else:
        atr_pct = 0.02
    atr_pct = max(0.0, min(1.0, atr_pct))

    # Volume z-score approximation
    volume_zscore = 0.0
    if volume > 0:
        volume_zscore = min(10.0, max(-10.0, (volume / 10_000_000 - 1.0)))

    # Trend slope from EMA relationship
    ema50 = float(technicals.get("ema_50", ema21))
    trend_slope = ((ema21 - ema50) / ema50) * 10.0 if ema50 > 0 else 0.0
    trend_slope = max(-10.0, min(10.0, trend_slope))

    # Volatility regime from Bollinger bandwidth
    bb_width_pct = ((bb_upper - bb_lower) / price) if price > 0 else 0.02
    if bb_width_pct > 0.15:
        volatility_regime = "extreme"
    elif bb_width_pct > 0.08:
        volatility_regime = "high"
    elif bb_width_pct > 0.03:
        volatility_regime = "normal"
    else:
        volatility_regime = "low"

    # Liquidity sweep detection: big volume + price near extremes
    liquidity_sweep = bool(
        volume_zscore > 2.0 and (price_vs_ema21 > 0.05 or price_vs_ema21 < -0.05)
    )

    # Return proxies: cannot compute from snapshot, use technical signals
    macd = float(technicals.get("macd", 0))
    macd_signal = float(technicals.get("macd_signal", 0))
    return_1 = (macd - macd_signal) / price if price > 0 else 0.0
    return_1 = max(-1.0, min(1.0, return_1 * 5.0))
    return_5 = return_1 * 0.7

    return {
        "return_1": round(return_1, 4),
        "return_5": round(return_5, 4),
        "rsi_14": round(rsi, 1),
        "atr_pct": round(atr_pct, 4),
        "volume_zscore": round(volume_zscore, 2),
        "price_vs_ema_21": round(price_vs_ema21, 4),
        "trend_slope": round(trend_slope, 4),
        "volatility_regime": volatility_regime,
        "liquidity_sweep": liquidity_sweep,
    }


def _build_context(data: dict[str, Any], pennylab: dict[str, Any]) -> dict[str, Any]:
    """Build context dict for NeuralDecisionExpert from macro/sentiment/fraud data."""
    macro = data.get("macro", {})
    sentiment = data.get("sentiment", {})

    # Macro risk: check treasury data quality
    if isinstance(macro, dict):
        if macro.get("data_quality") == "unavailable":
            macro_risk = "unknown"
        elif any(v.get("error") for v in macro.values() if isinstance(v, dict)):
            macro_risk = "unknown"
        else:
            macro_risk = "neutral"
    else:
        macro_risk = "unknown"

    # News sentiment
    sentiment_label = str(sentiment.get("sentiment_label") or sentiment.get("label") or "").lower()
    if "bullish" in sentiment_label:
        news_sentiment = "bullish"
    elif "bearish" in sentiment_label:
        news_sentiment = "bearish"
    elif "mixed" in sentiment_label:
        news_sentiment = "mixed"
    else:
        news_sentiment = "neutral"

    # Fraud risk from PennyLab scores
    scores = pennylab.get("scores", {}) if isinstance(pennylab, dict) else {}
    fraud_risk = float(
        scores.get("whale_suspicion", 0.0) * 0.3
        + scores.get("pump_probability", 0.0) * 0.3
        + scores.get("trap_risk", 0.0) * 0.4
    )
    fraud_risk = round(max(0.0, min(1.0, fraud_risk)), 2)

    # Veracity score from data quality
    quality_map = {"high": 0.85, "partial": 0.55, "degraded": 0.25, "timeout": 0.15}
    data_quality = data.get("data_quality", "partial")
    veracity_score = quality_map.get(str(data_quality), 0.5)

    return {
        "macro_risk": macro_risk,
        "news_sentiment": news_sentiment,
        "fraud_risk": fraud_risk,
        "veracity_score": round(veracity_score, 2),
    }
