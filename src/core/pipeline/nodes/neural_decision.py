"""Causal neural-direction pipeline node with fail-closed integration."""

from __future__ import annotations

from collections import deque
from typing import Any

from langgraph.config import get_stream_writer

_NEURAL_SEEN: deque[str] = deque(maxlen=64)


async def node_neural_decision(state: dict[str, Any]) -> dict[str, Any]:
    """Run the calibrated candle model and merge non-directional safety flags."""
    writer = get_stream_writer()
    run_id = str(state.get("run_id", ""))
    ticker = str(state.get("ticker", ""))

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

    if not ticker:
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
    if not isinstance(data, dict):
        data = {}
    pennylab = state.get("pennylab") or state.get("pennylab_result") or {}
    if not isinstance(pennylab, dict):
        pennylab = {}

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
        timeframe = str(state.get("time_horizon") or "14 days")
        safety = NeuralDecisionExpert().predict(ticker, timeframe, features, context)
        candles = _extract_candles(data)

        if not candles:
            result = _closed_neural_result(ticker, "insufficient_data", "NO_CANDLES")
        else:
            from experts.technical_neural.expert import TechnicalNeuralExpert

            result = TechnicalNeuralExpert().evaluate(ticker, candles)

        # The risk copilot may veto a qualified forecast.  It is never allowed
        # to create or overwrite the model's calibrated probability simplex.
        result["regime"] = safety.get("regime")
        result["recommendation"] = safety.get("recommendation")
        result["veto"] = bool(safety.get("veto", True))
        result["drawdown_risk"] = safety.get("drawdown_risk")
        result["safety_uncertainty"] = safety.get("uncertainty")
        result["safety_reason"] = safety.get("reason")
        if result["veto"] and result.get("status") == "ready":
            result["status"] = "abstain"
            result["decision"] = "ABSTAIN"
            reason_codes = list(result.get("reason_codes") or [])
            if "SAFETY_VETO" not in reason_codes:
                reason_codes.append("SAFETY_VETO")
            result["reason_codes"] = reason_codes

        writer(
            {
                "type": "NEURAL_DECISION",
                "symbol": ticker,
                "timeframe": timeframe,
                "status": result.get("status"),
                "decision": result.get("decision"),
                "direction_prob": result.get("direction_prob"),
                "model_id": result.get("model_id"),
                "as_of": result.get("as_of"),
                "horizon": result.get("horizon"),
                "reason_codes": result.get("reason_codes"),
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
        writer({"type": "ERROR", "run_id": run_id, "detail": f"neural_decision: {exc}"})
        writer(
            {
                "type": "PIPELINE_STEP",
                "run_id": run_id,
                "step": "neural_decision",
                "status": "error",
            }
        )
        return {
            "neural_decision": {
                **_closed_neural_result(ticker, "error", "NEURAL_PIPELINE_ERROR"),
                "error": str(exc)[:200],
            },
            "errors": state.get("errors", []) + [f"neural_decision:{exc}"],
        }


def _extract_candles(data: dict[str, Any]) -> list[Any]:
    """Extract provider candles without treating malformed containers as data."""
    candidates: Any = data.get("candles") or data.get("ohlcv") or []
    price_data = data.get("price")
    if isinstance(price_data, dict):
        nested = price_data.get("candles") or price_data.get("ohlcv") or []
        if nested:
            candidates = nested
    if not isinstance(candidates, list):
        return []
    return list(candidates)


def _closed_neural_result(ticker: str, status: str, reason_code: str) -> dict[str, Any]:
    """Stable fail-closed result; empty probabilities mean none were estimated."""
    return {
        "expert": "TechnicalNeuralExpert",
        "source": "technical_neural_causal",
        "ticker": ticker,
        "status": status,
        "decision": "ABSTAIN",
        "direction_prob": {},
        "calibration_status": "unavailable",
        "skill_status": "unqualified",
        "model_id": None,
        "as_of": None,
        "horizon": {"bars": 1},
        "reason_codes": [reason_code],
        "confidence": 0.0,
        "uncertainty": 1.0,
    }


def _build_features(data: dict[str, Any]) -> dict[str, Any]:
    """Extract descriptive snapshot features for the risk copilot."""
    technicals = data.get("technicals", {})
    price_data = data.get("price", {})
    if not isinstance(technicals, dict):
        technicals = {}
    if not isinstance(price_data, dict):
        price_data = {}
    realtime_price = data.get("realtime_price", {})
    if not isinstance(realtime_price, dict):
        realtime_price = {}

    price = float(technicals.get("price") or price_data.get("price") or realtime_price.get("price") or 0)
    rsi = float(technicals.get("rsi_14", 50.0))
    ema21 = float(technicals.get("ema_20", price))
    bb_upper = float(technicals.get("bb_upper", 0))
    bb_lower = float(technicals.get("bb_lower", 0))
    volume = float(technicals.get("volume", 0))

    price_vs_ema21 = ((price - ema21) / ema21) if ema21 > 0 else 0.0
    price_vs_ema21 = max(-1.0, min(1.0, price_vs_ema21))

    atr_pct = (bb_upper - bb_lower) / price if bb_upper and bb_lower and price > 0 else 0.02
    atr_pct = max(0.0, min(1.0, atr_pct))

    volume_zscore = 0.0
    if volume > 0:
        volume_zscore = min(10.0, max(-10.0, volume / 10_000_000 - 1.0))

    ema50 = float(technicals.get("ema_50", ema21))
    trend_slope = ((ema21 - ema50) / ema50) * 10.0 if ema50 > 0 else 0.0
    trend_slope = max(-10.0, min(10.0, trend_slope))

    bb_width_pct = (bb_upper - bb_lower) / price if price > 0 else 0.02
    if bb_width_pct > 0.15:
        volatility_regime = "extreme"
    elif bb_width_pct > 0.08:
        volatility_regime = "high"
    elif bb_width_pct > 0.03:
        volatility_regime = "normal"
    else:
        volatility_regime = "low"

    liquidity_sweep = bool(
        volume_zscore > 2.0 and (price_vs_ema21 > 0.05 or price_vs_ema21 < -0.05)
    )
    macd = float(technicals.get("macd", 0))
    macd_signal = float(technicals.get("macd_signal", 0))
    return_1 = (macd - macd_signal) / price if price > 0 else 0.0
    return_1 = max(-1.0, min(1.0, return_1 * 5.0))

    return {
        "return_1": round(return_1, 4),
        "return_5": round(return_1 * 0.7, 4),
        "rsi_14": round(rsi, 1),
        "atr_pct": round(atr_pct, 4),
        "volume_zscore": round(volume_zscore, 2),
        "price_vs_ema_21": round(price_vs_ema21, 4),
        "trend_slope": round(trend_slope, 4),
        "volatility_regime": volatility_regime,
        "liquidity_sweep": liquidity_sweep,
    }


def _build_context(data: dict[str, Any], pennylab: dict[str, Any]) -> dict[str, Any]:
    """Build non-directional integrity context from collected evidence."""
    macro = data.get("macro", {})
    sentiment = data.get("sentiment", {})
    if not isinstance(sentiment, dict):
        sentiment = {}

    if isinstance(macro, dict):
        if macro.get("data_quality") == "unavailable":
            macro_risk = "unknown"
        elif any(value.get("error") for value in macro.values() if isinstance(value, dict)):
            macro_risk = "unknown"
        else:
            macro_risk = "neutral"
    else:
        macro_risk = "unknown"

    sentiment_label = str(sentiment.get("sentiment_label") or sentiment.get("label") or "").lower()
    if "bullish" in sentiment_label:
        news_sentiment = "bullish"
    elif "bearish" in sentiment_label:
        news_sentiment = "bearish"
    elif "mixed" in sentiment_label:
        news_sentiment = "mixed"
    else:
        news_sentiment = "neutral"

    scores = pennylab.get("scores", {})
    if not isinstance(scores, dict):
        scores = {}
    fraud_risk = float(
        scores.get("whale_suspicion", 0.0) * 0.3
        + scores.get("pump_probability", 0.0) * 0.3
        + scores.get("trap_risk", 0.0) * 0.4
    )
    fraud_risk = round(max(0.0, min(1.0, fraud_risk)), 2)

    quality_map = {"high": 0.85, "partial": 0.55, "degraded": 0.25, "timeout": 0.15}
    veracity_score = quality_map.get(str(data.get("data_quality", "partial")), 0.5)
    return {
        "macro_risk": macro_risk,
        "news_sentiment": news_sentiment,
        "fraud_risk": fraud_risk,
        "veracity_score": round(veracity_score, 2),
    }
