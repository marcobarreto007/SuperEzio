import pytest

from core.audit.decision_trace import DecisionTraceLogger
from core.pipeline.nodes.guardrail_hub import GuardrailHub


@pytest.mark.asyncio
async def test_guardrail_hub_runs_30_registered_checks(tmp_path):
    trace = DecisionTraceLogger(output_dir=tmp_path)
    hub = GuardrailHub(trace_logger=trace)

    state = {
        "run_id": "guardrail-hub-test",
        "message": "AAPL 14 dias",
        "ticker": "AAPL",
        "data": {
            "ticker": "AAPL",
            "price": {"current": 150.0},
            "volume": 5_000_000,
            "avg_daily_dollar_volume": 750_000_000,
            "risk": "trend reversal",
            "invalidation": "close below support",
        },
        "f51_verdict": {"passed": True, "confidence": 0.9},
        "sdca_firewall": {"decision": "ALLOW", "confidence": 0.8},
        "math_report": {
            "modules": {
                "crisis_aggregate": {
                    "values": {
                        "models_ok": 3,
                        "models_run": 12,
                        "aggregate_score": 0.2,
                        "regime": "normal",
                    }
                }
            }
        },
    }

    result = await hub.run_all(state)

    assert result["total_guardrails"] == 30
    assert len(result["results"]) == 30
    assert result["summary"]["decision_counts"]["ALLOW"] >= 1
    assert result["blame_report"]["summary"]["total_events"] >= 60


@pytest.mark.asyncio
async def test_guardrail_hub_surfaces_sdca_block(tmp_path):
    trace = DecisionTraceLogger(output_dir=tmp_path)
    hub = GuardrailHub(trace_logger=trace)

    result = await hub.run_all(
        {
            "run_id": "guardrail-block-test",
            "message": "buy this now guaranteed",
            "ticker": "RISK",
            "sdca_firewall": {
                "decision": "BLOCK",
                "confidence": 0.91,
                "human_summary": "Pattern requires block.",
            },
        }
    )

    assert result["summary"]["ready"] is False
    assert "sdca_firewall" in result["summary"]["blocking_guardrails"]
    assert result["blame_report"]["blockers"]
