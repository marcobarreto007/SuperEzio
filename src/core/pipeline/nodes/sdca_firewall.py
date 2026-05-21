"""SDCA-Lite pipeline node — defensive decision firewall."""

from __future__ import annotations

from typing import Any

from langgraph.config import get_stream_writer

from core.risk_firewall import DecisionCandidate, evaluate_decision_with_sdca


def route_after_sdca_firewall(state: dict[str, Any]) -> str:
    """Hard-stop blocked candidates; let REVIEW/ALLOW continue to explanation."""

    if state.get("sdca_blocked"):
        return "respond_blocked"
    return "rag_forensics"


def _amount_from_state(state: dict[str, Any]) -> float | None:
    entities = state.get("entities") or {}
    for source in (entities, state.get("filters") or {}):
        for key in ("amount_cad", "amount", "capital", "position_size"):
            raw = source.get(key)
            if raw in (None, ""):
                continue
            try:
                return float(raw)
            except (TypeError, ValueError):
                continue
    return None


def _build_candidate(state: dict[str, Any]) -> DecisionCandidate:
    data = state.get("data") or {}
    neural = state.get("neural_decision") or {}
    pennylab = state.get("pennylab") or state.get("pennylab_result") or {}
    f51 = state.get("f51_verdict") or {}

    risk_context = {
        "route": state.get("route"),
        "intent": state.get("intent"),
        "time_horizon": state.get("time_horizon"),
        "data_quality": data.get("data_quality"),
        "neural_uncertainty": neural.get("uncertainty"),
        "drawdown_risk": neural.get("drawdown_risk"),
        "neural_veto": neural.get("veto"),
        "pennylab_decision": pennylab.get("decision"),
        "pennylab_scores": pennylab.get("scores", {}),
        "f51_passed": f51.get("passed"),
        "f51_confidence": f51.get("confidence"),
    }
    raw_signals = {
        "technicals": data.get("technicals", {}),
        "risk": data.get("risk", {}),
        "sentiment": data.get("sentiment", {}),
        "macro": data.get("macro", {}),
        "pennylab": pennylab,
        "neural_decision": neural,
    }
    return DecisionCandidate(
        id=str(state.get("run_id") or "pipeline-candidate"),
        source="superezio_pipeline",
        asset=state.get("ticker") or None,
        action=str(state.get("action") or "analyze"),
        thesis=str(state.get("message") or ""),
        amount_cad=_amount_from_state(state),
        risk_context=risk_context,
        raw_signals=raw_signals,
        timestamp=None,
    )


async def node_sdca_firewall(state: dict[str, Any]) -> dict[str, Any]:
    """Attach SDCA firewall evidence — runs for ALL routes (ghost tokens work on text)."""

    writer = get_stream_writer()
    run_id = state.get("run_id", "")
    ticker = state.get("ticker", "")
    message = state.get("message", "")

    if not message:
        writer(
            {
                "type": "PIPELINE_STEP",
                "run_id": run_id,
                "step": "sdca_firewall",
                "status": "skipped",
            }
        )
        return {}

    writer(
        {
            "type": "PIPELINE_STEP",
            "run_id": run_id,
            "step": "sdca_firewall",
            "status": "started",
            "ticker": ticker,
        }
    )

    try:
        decision = evaluate_decision_with_sdca(_build_candidate(state))
        payload = decision.model_dump(mode="json")
        writer(
            {
                "type": "SDCA_FIREWALL",
                "decision": payload["decision"],
                "confidence": payload["confidence"],
                "uncertainty": payload["uncertainty"],
                "ghost_tokens": payload["ghost_tokens"],
                "matched_experiences": payload["matched_experiences"],
                "consequence_score": payload["consequence_score"],
                "human_summary": payload["human_summary"],
            }
        )
        writer(
            {
                "type": "PIPELINE_STEP",
                "run_id": run_id,
                "step": "sdca_firewall",
                "status": "completed",
            }
        )
        update: dict[str, Any] = {"sdca_firewall": payload}
        # SDCA firewall hard-blocks only for real trading decisions (ticker
        # present). For non-trading routes (no ticker, general, market_scan),
        # the firewall still runs ghost-token detection and emits evidence,
        # but delegates the final call to the CEO model.
        if decision.decision == "BLOCK" and ticker:
            update["sdca_blocked"] = True
            update["action"] = "blocked_defensive"
        elif decision.decision == "REVIEW":
            update["sdca_review_required"] = True
        return update
    except Exception as exc:
        writer({"type": "ERROR", "run_id": run_id, "detail": f"sdca_firewall: {exc}"})
        writer(
            {
                "type": "PIPELINE_STEP",
                "run_id": run_id,
                "step": "sdca_firewall",
                "status": "error",
            }
        )
        return {
            "sdca_firewall": {"error": str(exc)[:200]},
            "errors": state.get("errors", []) + [f"sdca_firewall:{exc}"],
        }
