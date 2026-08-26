"""F51 Verdict node — runs the F51Engine on collected data."""

import logging

from langgraph.config import get_stream_writer

logger = logging.getLogger(__name__)


async def node_f51_verdict(state: dict) -> dict:
    """Run F51Engine verdict on collected data trace."""
    writer = get_stream_writer()
    run_id = state.get("run_id", "")

    writer(
        {
            "type": "PIPELINE_STEP",
            "run_id": run_id,
            "step": "f51_verdict",
            "status": "started",
        }
    )

    data = state.get("data") or {}
    ticker = state.get("ticker") or data.get("ticker", "")
    if not ticker:
        writer(
            {
                "type": "PIPELINE_STEP",
                "run_id": run_id,
                "step": "f51_verdict",
                "status": "skipped",
            }
        )
        return {"f51_verdict": {}}

    try:
        from ...f51_adapter import F51HubAdapter

        adapter = F51HubAdapter()
        trace = dict(data)
        trace.setdefault("ticker", ticker)
        trace.setdefault("user_message", state.get("message") or "")
        verdict = adapter.run_on_trace(trace, domain="trading")

        writer(
            {
                "type": "F51_VERDICT",
                "confidence": verdict.get("confidence"),
                "decision_score": verdict.get("decision_score"),
                "score_type": verdict.get("score_type"),
                "calibration_status": verdict.get("calibration_status"),
                "evidence_status": verdict.get("evidence_status"),
                "passed": verdict.get("passed"),
                "factors": verdict.get("factors"),
                "hub_risk_score": verdict.get("hub_risk", {}).get("risk_score"),
            }
        )

        # Optional CrisisMath integration
        try:
            from ...math.crisis import crisis_aggregate

            crisis_result = crisis_aggregate(
                {
                    "observations": data.get("macro_observations", []),
                    "market_series": data.get("market_series"),
                    "country": data.get("market", data.get("country")),
                },
                models=[
                    "bis_credit_gap",
                    "debt_service_ratio",
                    "shiller_valuation",
                    "markov_regime",
                    "hawkes_stress",
                    "lppls_bubble",
                ],
            )
            verdict["crisis"] = crisis_result
            if (crisis_result.get("models_ok") or 0) > 0:
                writer(
                    {
                        "type": "CRISIS_MATH",
                        "systemic_risk": crisis_result.get("aggregate_score"),
                        "regime": crisis_result.get("regime"),
                        "alert": crisis_result.get("alert_level"),
                    }
                )
            else:
                writer(
                    {
                        "type": "CRISIS_MATH",
                        "status": "insufficient_data",
                        "detail": crisis_result.get("status") or crisis_result.get("reason"),
                    }
                )
        except Exception as crisis_exc:
            logger.warning("crisis_math_unavailable", exc_info=True)
            verdict["crisis"] = {
                "status": "error",
                "error": str(crisis_exc),
            }
            writer(
                {
                    "type": "CRISIS_MATH",
                    "status": "error",
                    "detail": str(crisis_exc),
                }
            )

        writer(
            {
                "type": "PIPELINE_STEP",
                "run_id": run_id,
                "step": "f51_verdict",
                "status": "completed",
            }
        )
        return {"f51_verdict": verdict}

    except Exception as exc:  # noqa: BLE001 — catch amplo deliberado: falha do F51 vira erro rastreado no state, não derruba o pipeline
        writer(
            {
                "type": "ERROR",
                "run_id": run_id,
                "detail": f"f51_verdict: {exc}",
            }
        )
        writer(
            {
                "type": "PIPELINE_STEP",
                "run_id": run_id,
                "step": "f51_verdict",
                "status": "error",
            }
        )
        return {
            "f51_verdict": {},
            "errors": state.get("errors", []) + [f"f51:{exc}"],
        }
