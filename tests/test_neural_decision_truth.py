"""Fail-closed contract tests for the neural decision integration."""

from __future__ import annotations

import asyncio
import uuid

import src.core.pipeline.nodes.neural_decision as neural_node
from experts.neural_decision import NeuralDecisionExpert


def _valid_payload() -> tuple[dict[str, object], dict[str, object]]:
    return (
        {
            "return_1": 0.002,
            "return_5": -0.01,
            "rsi_14": 55.0,
            "atr_pct": 0.018,
            "volume_zscore": 1.2,
            "price_vs_ema_21": 0.006,
            "trend_slope": 0.08,
            "volatility_regime": "normal",
            "liquidity_sweep": False,
        },
        {
            "macro_risk": "neutral",
            "news_sentiment": "neutral",
            "fraud_risk": 0.1,
            "veracity_score": 0.9,
        },
    )


def test_snapshot_expert_never_fabricates_direction_probabilities() -> None:
    features, context = _valid_payload()
    result = NeuralDecisionExpert().predict("AAPL", "1d", features, context)
    assert result["status"] == "abstain"
    assert result["decision"] == "ABSTAIN"
    assert result["direction_prob"] == {}
    assert result["calibration_status"] == "unavailable"
    assert "DIRECTION_MODEL_REQUIRED" in result["reason_codes"]


def test_pipeline_without_candles_is_insufficient_and_never_buy(
    monkeypatch,
) -> None:
    events: list[dict[str, object]] = []
    monkeypatch.setattr(neural_node, "get_stream_writer", lambda: events.append)
    result = asyncio.run(
        neural_node.node_neural_decision(
            {
                "run_id": f"truth-{uuid.uuid4()}",
                "ticker": "AAPL",
                "time_horizon": "14 days",
                "data": {},
            }
        )
    )["neural_decision"]
    assert result["status"] == "insufficient_data"
    assert result["decision"] == "ABSTAIN"
    assert result["direction_prob"] == {}
    assert result["decision"] != "BUY"
    assert result["reason_codes"] == ["NO_CANDLES"]
