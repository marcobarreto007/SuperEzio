"""Pipeline verdict — structured JSON before Bob translates.

This module compiles all pipeline results into a deterministic verdict dict
that the LLM (Bob) MUST follow, not question. Each _extract_* function
pulls only the essential fields (maximum 5-7) from its respective module.
"""

from __future__ import annotations

from typing import Any


def validate_answer_against_verdict(answer: str, verdict: dict) -> dict:
    """Check if Bob's answer references pipeline data.

    Returns ``{"passed": bool, "reason": str, "numbers_referenced": int,
    "modules_referenced": int}``.
    Used as a post-processing guard to catch answers that ignore pipeline
    facts and hallucinate their own numbers instead.
    """
    issues: list[str] = []

    # Check ticker mentioned
    ticker = verdict.get("ticker", "")
    if ticker and ticker.upper() not in answer.upper():
        issues.append(f"Ticker {ticker} not mentioned")

    # Check at least 2 of 4 pipeline numbers appear
    math = verdict.get("math", {})
    numbers_found = 0
    for key in ["rsi", "sharpe", "latest_price", "macd"]:
        val = math.get(key)
        if val is not None:
            try:
                val_str = str(round(float(val), 1)) if isinstance(val, (int, float)) else str(val)
            except (TypeError, ValueError, OverflowError):
                val_str = str(val)
            if val_str in answer:
                numbers_found += 1

    if numbers_found < 2:
        issues.append(f"Only {numbers_found}/4 pipeline numbers referenced")

    # Check module NAMES mentioned (RSI, MACD, F51, SDCA)
    answer_upper = answer.upper() if answer else ""
    required_modules = []
    if math.get("rsi") not in (None, "N/A"):
        required_modules.append("RSI")
    if math.get("macd") not in (None, "N/A"):
        required_modules.append("MACD")
    if verdict.get("f51", {}).get("score") not in (None, "N/A"):
        required_modules.append("F51")
    if verdict.get("sdca", {}).get("decision") not in (None, "N/A"):
        required_modules.append("SDCA")

    modules_found = 0
    missing_modules = []
    for mod in required_modules:
        if mod in answer_upper:
            modules_found += 1
        else:
            missing_modules.append(mod)

    if required_modules and missing_modules:
        issues.append(
            f"Modules not referenced by name: {', '.join(missing_modules)} "
            f"({modules_found}/{len(required_modules)} found)"
        )

    return {
        "passed": len(issues) == 0,
        "reason": "; ".join(issues) if issues else "OK",
        "numbers_referenced": numbers_found,
        "modules_referenced": modules_found,
    }


def build_verdict_dict(state: dict) -> dict:
    """Extract a template-friendly verdict dict from LangGraph state.

    Returns a flatter structure than :func:`build_pipeline_verdict` so the
    RESPONSE TEMPLATE injected into Bob's messages can reference fields
    directly (e.g. ``math.rsi`` instead of ``math.modules.technical_indicators.values.rsi14``).
    """
    math_report = state.get("math_report") or {}
    summary = math_report.get("summary") if isinstance(math_report, dict) else {}
    if not isinstance(summary, dict):
        summary = {}
    modules_data = math_report.get("modules") if isinstance(math_report, dict) else {}
    technicals = {}
    if isinstance(modules_data, dict):
        tech = modules_data.get("technical_indicators") or {}
        if isinstance(tech, dict):
            technicals = tech.get("values") or {}

    f51 = state.get("f51_verdict") or {}

    sdca = state.get("sdca_firewall") or {}

    neural = state.get("neural_decision") or {}

    expert_consensus = state.get("expert_consensus") or {}

    return {
        "ticker": str(state.get("ticker", "") or ""),
        "math": {
            "latest_price": summary.get("latest_price", "N/A"),
            "rsi": technicals.get("rsi14") or technicals.get("rsi") or "N/A",
            "macd": technicals.get("macd") or "N/A",
            "sharpe": summary.get("sharpe", "N/A"),
        },
        "f51": {
            "score": f51.get("decision_score") or f51.get("confidence") or "N/A",
            "passed": f51.get("passed", "N/A"),
        },
        "sdca": {
            "decision": sdca.get("decision", "N/A"),
        },
        "neural": {
            "decision": neural.get("regime") or neural.get("predicted_regime") or "N/A",
        },
        "experts": {
            "consensus": expert_consensus.get("decision", "N/A"),
        },
    }


def build_pipeline_verdict(state: dict) -> dict:
    """Compile all pipeline results into a structured verdict.

    This JSON is the 'official verdict' that Bob must translate, not question.
    """
    return {
        "pipeline_status": "COMPLETE",
        "ticker": state.get("ticker", ""),
        "data_valid": bool(state.get("data")),
        "math": _extract_math(state),
        "f51": _extract_f51(state),
        "sdca": _extract_sdca(state),
        "neural": _extract_neural(state),
        "experts": _extract_experts(state),
        "trinity": _extract_trinity(state),
        "guardrails": _extract_guardrails(state),
        "pennylab": _extract_pennylab(state),
    }


# ---------------------------------------------------------------------------
# Private extractors -- max 5-7 fields per module
# ---------------------------------------------------------------------------


def _extract_math(state: dict) -> dict[str, Any]:
    """Extract essential fields from MathHub report."""
    report = state.get("math_report") or {}
    if not isinstance(report, dict) or not report:
        return {}
    return {
        "ticker": report.get("ticker"),
        "coverage": report.get("coverage"),
        "summary": report.get("summary"),
        "modules": _safe_list(report.get("modules")),
        "numbers": report.get("numbers"),
    }


def _extract_f51(state: dict) -> dict[str, Any]:
    """Extract essential fields from F51 firewall verdict."""
    f51 = state.get("f51_verdict") or {}
    if not isinstance(f51, dict) or not f51:
        return {}
    return {
        "passed": f51.get("passed"),
        "score": f51.get("decision_score") or f51.get("confidence"),
        "error": f51.get("error"),
        "flags": _safe_list(f51.get("flags")),
        "decision": f51.get("decision"),
    }


def _extract_sdca(state: dict) -> dict[str, Any]:
    """Extract essential fields from SDCA firewall."""
    sdca = state.get("sdca_firewall") or {}
    sdca_blocked = state.get("sdca_blocked", False)
    if not isinstance(sdca, dict) or not sdca:
        return {"blocked": sdca_blocked} if sdca_blocked else {}
    return {
        "decision": sdca.get("decision"),
        "risk_score": sdca.get("risk_score"),
        "blocked": sdca_blocked,
        "error": sdca.get("error"),
        "flags": _safe_list(sdca.get("flags")),
    }


def _extract_neural(state: dict) -> dict[str, Any]:
    """Extract essential fields from Neural Decision."""
    neural = state.get("neural_decision") or {}
    if not isinstance(neural, dict) or not neural:
        return {}
    return {
        "regime": neural.get("regime") or neural.get("predicted_regime"),
        "expected_return": neural.get("expected_return"),
        "confidence": neural.get("confidence"),
        "error": neural.get("error"),
        "whale_suspicion": neural.get("whale_suspicion"),
        "pump_probability": neural.get("pump_probability"),
    }


def _extract_experts(state: dict) -> dict[str, Any]:
    """Extract essential fields from Expert Committee."""
    consensus = state.get("expert_consensus") or {}
    results = state.get("expert_results") or []
    if not isinstance(consensus, dict) and not results:
        return {}
    extracted: dict[str, Any] = {}
    if isinstance(consensus, dict) and consensus:
        extracted["decision"] = consensus.get("decision")
        extracted["score"] = consensus.get("score")
        extracted["coverage"] = consensus.get("weight_coverage")
        extracted["variance"] = consensus.get("variance")
    if results:
        extracted["evaluated_count"] = len(results)
        extracted["experts"] = _safe_list(results)[:5]
    return extracted


def _extract_trinity(state: dict) -> dict[str, Any]:
    """Extract essential fields from Trinity deliberation."""
    report = state.get("trinity_report") or ""
    if not isinstance(report, str) or len(report) <= 10:
        return {}
    return {
        "summary": report[:200],
        "length": len(report),
    }


def _extract_guardrails(state: dict) -> dict[str, Any]:
    """Extract essential fields from Guardrail Hub."""
    hub = state.get("guardrail_hub") or {}
    if not isinstance(hub, dict) or not hub:
        return {}
    return {
        "blocking_count": hub.get("blocking_count"),
        "ready": hub.get("ready"),
        "passed": hub.get("passed"),
        "errors": _safe_list(hub.get("errors"))[:3],
        "total_checks": hub.get("total_checks"),
    }


def _extract_pennylab(state: dict) -> dict[str, Any]:
    """Extract essential fields from Pennylab manipulation check."""
    pennylab = state.get("pennylab") or state.get("pennylab_result") or {}
    if not isinstance(pennylab, dict) or not pennylab:
        return {}
    scores = pennylab.get("scores") or {}
    if not isinstance(scores, dict):
        scores = {}
    return {
        "decision": pennylab.get("decision"),
        "whale_suspicion": scores.get("whale_suspicion") or pennylab.get("whale_suspicion"),
        "pump_probability": scores.get("pump_probability") or pennylab.get("pump_probability"),
        "error": pennylab.get("error"),
        "flags": _safe_list(pennylab.get("flags")),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_list(value: Any) -> list[Any]:
    """Return *value* as a list, or an empty list if not a list."""
    return value if isinstance(value, list) else []
