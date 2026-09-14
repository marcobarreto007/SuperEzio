"""Deterministic adaptive constraints shared by every order-entry path."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any


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


def judge_block_reason(state: Mapping[str, Any]) -> str | None:
    """Fail closed when the arbitration judge explicitly vetos/blocks the trade."""
    judge_results = state.get("judge_results") or []
    if not judge_results:
        return None
    for j in judge_results:
        if not isinstance(j, Mapping):
            continue
        parsed = j.get("parsed") if isinstance(j.get("parsed"), Mapping) else {}
        verdict = str(parsed.get("verdict") or j.get("verdict") or "").strip().upper()
        if verdict in {"BLOCK", "VETO", "REJECT", "NEGATIVE"}:
            reason = str(
                parsed.get("reason")
                or parsed.get("recommendation")
                or j.get("error")
                or "judge_veto"
            )
            return f"arbitration judge vetoed order: {reason}"
    return None


def micro_capital_survival_block_reason(
    state: Mapping[str, Any],
    symbol: str,
    *,
    limit_price: float | None = None,
    stop_loss_price: float | None = None,
    order_type: str = "LIMIT",
) -> str | None:
    """Enforce the strict $1,000 CAD micro-capital survival rules (Ezio & MIKE global mandate).

    1. ZERO COMMISSION: Only commission-free instruments (TD 108 ETFs or confirmed zero-commission quota).
    2. STRICT RISK LIMIT: Max risk <= 1.5% of equity ($15 on $1,000 CAD).
    3. NO MARKET ORDERS: Only LIMIT orders permitted to avoid catastrophic slippage.
    """
    clean_type = str(order_type or "LIMIT").strip().upper()
    if clean_type in {"MKT", "MARKET"}:
        return "market_orders_forbidden_under_micro_capital_protocol: limit orders only"

    clean_sym = str(symbol or "").strip().upper()
    if not clean_sym:
        return "missing_symbol_for_survival_validation"

    # Commission check: TD commission-free universe (108 ETFs) or confirmed free quota
    from core.trading.td_universe import is_commission_free

    has_free_quota = bool(
        state.get("td_easy_trade_free_quota") or state.get("commission_free_confirmed")
    )
    if not is_commission_free(clean_sym) and not has_free_quota:
        return (
            f"zero_commission_violation: {clean_sym} is not in the TD commission-free universe; "
            "micro-capital survival protocol requires zero commission"
        )

    # Risk per share check against max risk amount (1.5% of equity = $15 on $1000)
    if limit_price is not None and stop_loss_price is not None:
        risk_per_share = abs(limit_price - stop_loss_price)
        if risk_per_share > 15.0:
            return (
                f"risk_per_share_too_wide: risk per share ${risk_per_share:.2f} exceeds "
                "micro-capital trade risk budget of $15.00 CAD"
            )

    return None


def meta_labeling_block_reason(
    state: Mapping[str, Any],
    symbol: str,
    *,
    side: str = "BUY",
    entry_price: float,
    stop_loss_price: float | None = None,
    take_profit_price: float | None = None,
    threshold: float = 0.55,
) -> str | None:
    """Evaluate candidate trade assertiveness through the López de Prado Meta-Labeler.

    Returns None if trade is approved by the Meta-Labeler (P >= threshold).
    Returns rejection string if trade is rejected / abstained (P < threshold).
    """
    from core.trading.meta_labeling import evaluate_meta_labeling_gate

    result = evaluate_meta_labeling_gate(
        state,
        symbol,
        side=side,
        entry_price=entry_price,
        stop_loss_price=stop_loss_price,
        take_profit_price=take_profit_price,
        threshold=threshold,
    )
    if not result.allowed:
        return result.rejection_reason or f"meta_labeling_abstain:{result.code}"
    return None


def evaluate_neural_execution_gate(state: Mapping[str, Any], action: str) -> dict[str, Any]:
    """Validate that an autonomous order is backed by a usable neural forecast.

    A bounded number is not enough: the model must explicitly be ready,
    calibrated, current, directionally compatible, and expose a valid
    three-class probability simplex.  Non-ready states carry no synthetic
    fallback distribution and fail closed.
    """
    neural = state.get("neural_decision")
    if not isinstance(neural, Mapping) or not neural:
        return {"allowed": False, "code": "NEURAL_DECISION_MISSING"}

    status = str(neural.get("status") or "").strip().lower()
    if status != "ready":
        return {
            "allowed": False,
            "code": f"NEURAL_{status.upper() or 'NOT_READY'}",
            "reason_codes": list(neural.get("reason_codes") or []),
        }

    calibration = str(neural.get("calibration_status") or "").strip().lower()
    if calibration not in {"calibrated", "validated_oos"}:
        return {
            "allowed": False,
            "code": "NEURAL_NOT_CALIBRATED",
            "calibration_status": calibration or "missing",
        }

    model_id = str(neural.get("model_id") or "").strip()
    as_of = str(neural.get("as_of") or "").strip()
    horizon = neural.get("horizon")
    if not model_id or not as_of or horizon in (None, ""):
        return {"allowed": False, "code": "NEURAL_PROVENANCE_INCOMPLETE"}

    raw_probabilities = neural.get("direction_prob")
    if not isinstance(raw_probabilities, Mapping):
        return {"allowed": False, "code": "NEURAL_SIMPLEX_MISSING"}
    try:
        probabilities = {
            label: float(raw_probabilities[label]) for label in ("up", "down", "sideways")
        }
    except (KeyError, TypeError, ValueError):
        return {"allowed": False, "code": "NEURAL_SIMPLEX_INVALID"}
    if any(
        not math.isfinite(value) or value < 0.0 or value > 1.0 for value in probabilities.values()
    ):
        return {"allowed": False, "code": "NEURAL_SIMPLEX_INVALID"}
    if not math.isclose(sum(probabilities.values()), 1.0, abs_tol=1e-6):
        return {"allowed": False, "code": "NEURAL_SIMPLEX_INVALID"}

    decision = str(neural.get("decision") or "ABSTAIN").strip().upper()
    normalized_action = str(action or "").strip().lower()
    required_decision = "UP" if normalized_action in {"buy", "long"} else "DOWN"
    if normalized_action not in {"buy", "long", "sell", "short"}:
        return {"allowed": False, "code": "ORDER_DIRECTION_INVALID"}
    if decision != required_decision:
        return {
            "allowed": False,
            "code": "NEURAL_DIRECTION_CONFLICT",
            "model_decision": decision,
            "required_decision": required_decision,
        }

    prediction_set = neural.get("prediction_set")
    if not isinstance(prediction_set, (list, tuple, set)):
        return {"allowed": False, "code": "NEURAL_PREDICTION_SET_MISSING"}
    normalized_set = {str(label).strip().upper() for label in prediction_set}
    if normalized_set != {required_decision}:
        return {
            "allowed": False,
            "code": "NEURAL_PREDICTION_SET_AMBIGUOUS",
            "prediction_set": sorted(normalized_set),
        }

    return {
        "allowed": True,
        "code": "ALLOW",
        "model_id": model_id,
        "as_of": as_of,
        "horizon": horizon,
        "decision": decision,
        "selected_probability": probabilities[required_decision.lower()],
    }
