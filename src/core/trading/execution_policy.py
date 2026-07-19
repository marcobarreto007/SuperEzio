"""Deterministic adaptive constraints shared by every order-entry path."""

from __future__ import annotations

from typing import Any, Mapping


def adaptive_sizing_config(state: Mapping[str, Any]) -> dict[str, float]:
    """Allow adaptive state to tighten, never loosen, execution ceilings."""
    adaptive = state.get("adaptive_config") or {}
    try:
        requested_position = float(adaptive.get("max_position_pct", 0.10))
    except (AttributeError, TypeError, ValueError):
        requested_position = 0.10
    try:
        requested_stop = float(adaptive.get("stop_loss_pct", 0.05))
    except (AttributeError, TypeError, ValueError):
        requested_stop = 0.05
    return {
        "max_position_pct": max(0.0, min(0.10, requested_position)),
        "default_stop_pct": max(0.01, min(0.50, requested_stop)),
    }


def expert_consensus_block_reason(state: Mapping[str, Any]) -> str | None:
    """Fail closed when learned negative consensus has meaningful coverage."""
    consensus = state.get("expert_consensus") or {}
    try:
        coverage = float(consensus.get("weight_coverage", 0.0) or 0.0)
        score = float(consensus.get("score", 0.0) or 0.0)
    except (AttributeError, TypeError, ValueError):
        return None
    if consensus.get("decision") == "BLOCK" and coverage >= 0.30:
        return f"learned expert consensus blocked order: score={score:.3f}, coverage={coverage:.3f}"
    return None
