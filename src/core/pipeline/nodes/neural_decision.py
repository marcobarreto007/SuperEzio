"""Causal neural-direction pipeline node with fail-closed integration."""

from __future__ import annotations

import math
from collections import deque
from typing import Any

import numpy as np
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

        candles = _extract_candles(data)
        features = _build_features(data, candles)
        context = _build_context(data, pennylab)
        timeframe = str(state.get("time_horizon") or "14 days")
        safety = NeuralDecisionExpert().predict(ticker, timeframe, features, context)

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

    except Exception as exc:  # noqa: BLE001
        # Fail-closed deliberado: falha do expert vira abstencao, nunca resultado nao calibrado.
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


def _build_features(
    data: dict[str, Any],
    candles: list[Any] | None = None,
) -> dict[str, Any]:
    """Compute the risk snapshot strictly from observed OHLCV candles."""
    raw_candles = candles if candles is not None else _extract_candles(data)
    del data  # compatibility parameter; synthetic technical defaults are forbidden
    if len(raw_candles) < 21:
        return {}
    try:
        from experts.technical_neural.expert import TechnicalNeuralExpert

        by_time: dict[Any, tuple[float, float, float, float, float]] = {}
        for candle in raw_candles:
            if not isinstance(candle, dict):
                return {}
            timestamp = TechnicalNeuralExpert._parse_timestamp(candle)
            values = tuple(float(candle[name]) for name in ("open", "high", "low", "close")) + (
                float(candle.get("volume", 0.0)),
            )
            if not all(math.isfinite(value) for value in values):
                return {}
            previous = by_time.get(timestamp)
            if previous is not None and previous != values:
                return {}
            by_time[timestamp] = values
        ordered = [values for _, values in sorted(by_time.items())]
        if len(ordered) < 21:
            return {}
        matrix = np.asarray(ordered, dtype=np.float64)
        highs = matrix[:, 1]
        lows = matrix[:, 2]
        closes = matrix[:, 3]
        volumes = matrix[:, 4]
        if np.any(closes <= 0) or np.any(volumes < 0):
            return {}
    except (KeyError, TypeError, ValueError):
        return {}

    return_1 = float(closes[-1] / closes[-2] - 1.0)
    return_5 = float(closes[-1] / closes[-6] - 1.0)
    from core.math.indicators import rsi as calculate_rsi

    rsi_value = calculate_rsi(closes.tolist(), period=14)
    if rsi_value is None:
        return {}

    true_ranges = []
    for index in range(max(1, len(closes) - 14), len(closes)):
        true_ranges.append(
            max(
                highs[index] - lows[index],
                abs(highs[index] - closes[index - 1]),
                abs(lows[index] - closes[index - 1]),
            )
        )
    atr_pct = float(np.mean(true_ranges) / closes[-1])

    ema21 = float(closes[0])
    alpha = 2.0 / 22.0
    for close in closes[1:]:
        ema21 = alpha * float(close) + (1.0 - alpha) * ema21
    price_vs_ema21 = float(closes[-1] / ema21 - 1.0)

    volume_window = volumes[-20:]
    volume_std = float(np.std(volume_window, ddof=1))
    volume_zscore = (
        float((volumes[-1] - np.mean(volume_window)) / volume_std) if volume_std > 0.0 else 0.0
    )
    log_window = np.log(closes[-20:])
    trend_slope = float(np.polyfit(np.arange(len(log_window)), log_window, 1)[0] * 10.0)
    realized_volatility = float(np.std(np.diff(log_window), ddof=1))
    if realized_volatility > 0.05:
        volatility_regime = "extreme"
    elif realized_volatility > 0.025:
        volatility_regime = "high"
    elif realized_volatility > 0.01:
        volatility_regime = "normal"
    else:
        volatility_regime = "low"

    liquidity_sweep = bool(volume_zscore > 2.0 and abs(return_1) > max(2 * atr_pct, 0.03))

    return {
        "return_1": max(-1.0, min(1.0, return_1)),
        "return_5": max(-1.0, min(1.0, return_5)),
        "rsi_14": float(rsi_value),
        "atr_pct": max(0.0, min(1.0, atr_pct)),
        "volume_zscore": max(-10.0, min(100.0, volume_zscore)),
        "price_vs_ema_21": max(-1.0, min(1.0, price_vs_ema21)),
        "trend_slope": max(-10.0, min(10.0, trend_slope)),
        "volatility_regime": volatility_regime,
        "liquidity_sweep": liquidity_sweep,
    }


def _build_context(data: dict[str, Any], pennylab: dict[str, Any]) -> dict[str, Any]:
    """Build non-directional integrity context from collected evidence."""
    macro = data.get("macro", {})
    sentiment = data.get("sentiment", {})
    if not isinstance(sentiment, dict):
        sentiment = {}

    if isinstance(macro, dict) and macro:
        if macro.get("data_quality") == "unavailable" or any(
            value.get("error") for value in macro.values() if isinstance(value, dict)
        ):
            macro_risk = "unknown"
        elif any(value not in (None, "", {}, []) for value in macro.values()):
            macro_risk = "neutral"
        else:
            macro_risk = "unknown"
    else:
        macro_risk = "unknown"

    sentiment_label = str(sentiment.get("sentiment_label") or sentiment.get("label") or "").lower()
    if "bullish" in sentiment_label:
        news_sentiment = "bullish"
    elif "bearish" in sentiment_label:
        news_sentiment = "bearish"
    elif "mixed" in sentiment_label:
        news_sentiment = "mixed"
    elif sentiment_label:
        news_sentiment = "neutral"
    else:
        news_sentiment = "unknown"

    scores = pennylab.get("scores", {})
    if not isinstance(scores, dict):
        scores = {}
    required_scores = {"whale_suspicion", "pump_probability", "trap_risk"}
    fraud_evidence_available = required_scores.issubset(scores)
    fraud_risk = float(
        scores.get("whale_suspicion", 0.0) * 0.3
        + scores.get("pump_probability", 0.0) * 0.3
        + scores.get("trap_risk", 0.0) * 0.4
    )
    fraud_risk = round(max(0.0, min(1.0, fraud_risk)), 2)

    quality_map = {
        "complete": 0.90,
        "high": 0.85,
        "provider_or_computed": 0.75,
        "partial": 0.55,
        "degraded": 0.25,
        "timeout": 0.15,
    }
    data_quality = str(data.get("data_quality") or "unknown")
    veracity_score = quality_map.get(data_quality, 0.0)
    evidence_complete = bool(
        fraud_evidence_available
        and data_quality in {"complete", "high", "provider_or_computed", "partial"}
    )
    return {
        "macro_risk": macro_risk,
        "news_sentiment": news_sentiment,
        "fraud_risk": fraud_risk,
        "veracity_score": round(veracity_score, 2),
        "evidence_complete": evidence_complete,
    }
