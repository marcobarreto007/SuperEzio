"""SDCA-Lite v0.1: F51 Cognitive Risk Firewall."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .experience_memory import retrieve_experiences
from .sdca_contracts import (
    ConsequenceScore,
    DecisionCandidate,
    ExperienceMatch,
    GhostTokenReport,
    RiskFirewallDecision,
    RuminationState,
)

U_THRESH = 0.55
EPSILON = 0.05
MAX_CYCLES = 3


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def _lower(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        return " ".join(f"{k} {_lower(v)}" for k, v in value.items()).lower()
    if isinstance(value, (list, tuple, set)):
        return " ".join(_lower(v) for v in value).lower()
    return str(value).lower()


def _truthy_high(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value >= 0.65
    text = _lower(value).strip()
    # "low" must NOT be here: this helper flags HIGH-risk textual signals
    # (flow_toxicity, spread, fomo, leverage, latency, stale_signal, ...).
    # A field reporting "low" (e.g. flow_toxicity=low, leverage=low) is the
    # opposite of high risk and was being misclassified as high-risk by this
    # set (docs/audit/phase5_f51_sdca_neural.md, finding 5.5).
    return text in {"high", "true", "yes", "wide", "unstable", "stale", "degraded"}


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _has_any(blob: str, terms: Iterable[str]) -> bool:
    return any(term in blob for term in terms)


def _report(expert_name: str, tokens: list[str], evidence: dict[str, Any]) -> GhostTokenReport:
    unique_tokens = sorted(dict.fromkeys(tokens))
    if not unique_tokens:
        uncertainty = 0.14
    else:
        uncertainty = _clamp(0.28 + (0.13 * len(unique_tokens)) + (0.04 * len(evidence)))
    return GhostTokenReport(
        expert_name=expert_name,
        ghost_tokens=unique_tokens,
        uncertainty=round(uncertainty, 3),
        evidence=evidence,
    )


def _macro_risk(candidate: DecisionCandidate) -> GhostTokenReport:
    blob = _lower({"risk_context": candidate.risk_context, "raw_signals": candidate.raw_signals})
    tokens: list[str] = []
    evidence: dict[str, Any] = {}

    if _has_any(blob, ("macro high", "macro_risk high", "uncertain", "cpi surprise", "fed shock")):
        tokens.append("macro_uncertainty_high")
        evidence["macro_context"] = "high_or_uncertain"
    if _has_any(blob, ("rate shock", "rates high", "interest_rate_shock", "yield spike")):
        tokens.append("rate_shock_possible")
        evidence["rates"] = "shock_possible"
    if _has_any(blob, ("liquidity_regime unstable", "liquidity low", "liquidity tight")):
        tokens.append("liquidity_regime_unstable")
        evidence["liquidity_regime"] = "unstable"
    if _has_any(blob, ("correlation_breakdown", "correlation breakdown", "correlation high")):
        tokens.append("correlation_breakdown")
        evidence["correlation"] = "breakdown_possible"

    return _report("MacroRiskGhostExpert", tokens, evidence)


def _flow_risk(candidate: DecisionCandidate) -> GhostTokenReport:
    blob = _lower({"action": candidate.action, "thesis": candidate.thesis, **candidate.raw_signals})
    signals = candidate.raw_signals
    tokens: list[str] = []
    evidence: dict[str, Any] = {}

    if _truthy_high(signals.get("flow_toxicity")) or _has_any(blob, ("whale", "toxic flow")):
        tokens.append("flow_toxicity_high")
        evidence["flow_toxicity"] = signals.get("flow_toxicity", "text_match")
    if _has_any(blob, ("liquidity trap", "thin book", "fake volume")):
        tokens.append("liquidity_trap_possible")
        evidence["liquidity_trap"] = "possible"
    spread = signals.get("spread")
    if _truthy_high(spread) or _num(spread) >= 0.03:
        tokens.append("spread_expansion")
        evidence["spread"] = spread
    if (
        _num(signals.get("price_change_2h")) >= 5.0 and _truthy_high(signals.get("social_hype"))
    ) or _has_any(blob, ("fake breakout", "breakout now", "breakout chase")):
        tokens.append("fake_breakout_possible")
        evidence["breakout"] = {
            "price_change_2h": signals.get("price_change_2h"),
            "social_hype": signals.get("social_hype"),
        }

    return _report("FlowRiskGhostExpert", tokens, evidence)


def _human_risk(candidate: DecisionCandidate) -> GhostTokenReport:
    blob = _lower(
        {
            "action": candidate.action,
            "thesis": candidate.thesis,
            "risk_context": candidate.risk_context,
        }
    )
    ctx = candidate.risk_context
    tokens: list[str] = []
    evidence: dict[str, Any] = {}

    if _truthy_high(ctx.get("fomo")) or _has_any(
        blob, ("fomo", "agora", "right now", "subiu forte")
    ):
        tokens.append("fomo_pattern_detected")
        evidence["fomo"] = ctx.get("fomo", "text_match")
    if _truthy_high(ctx.get("revenge_trade")) or _has_any(
        blob, ("recover losses", "make it back", "revenge")
    ):
        tokens.append("revenge_trade_pattern")
        evidence["revenge_trade"] = ctx.get("revenge_trade", "text_match")
    if _truthy_high(ctx.get("leverage")) or "leveraged" in blob or "alavanc" in blob:
        tokens.append("leverage_impulse")
        evidence["leverage"] = ctx.get("leverage", "action_match")
    if _truthy_high(ctx.get("overconfidence")) or _has_any(
        blob, ("sure thing", "can't lose", "all in", "certeza")
    ):
        tokens.append("overconfidence_detected")
        evidence["overconfidence"] = ctx.get("overconfidence", "text_match")

    return _report("HumanRiskGhostExpert", tokens, evidence)


def _infra_risk(candidate: DecisionCandidate) -> GhostTokenReport:
    blob = _lower({"risk_context": candidate.risk_context, "raw_signals": candidate.raw_signals})
    ctx = candidate.risk_context
    signals = candidate.raw_signals
    tokens: list[str] = []
    evidence: dict[str, Any] = {}

    latency = ctx.get("latency", signals.get("latency"))
    if _truthy_high(latency) or _num(latency) >= 1000:
        tokens.append("api_latency_rising")
        evidence["latency"] = latency
    quality = ctx.get("data_quality", signals.get("data_quality"))
    if _lower(quality) in {"low", "degraded", "poor", "unavailable"}:
        tokens.append("data_quality_low")
        evidence["data_quality"] = quality
    slippage = ctx.get("slippage", signals.get("slippage"))
    if _truthy_high(slippage) or "slippage" in blob or _truthy_high(signals.get("spread")):
        tokens.append("execution_slippage_risk")
        evidence["slippage"] = slippage or signals.get("spread", "text_match")
    age = _num(ctx.get("signal_age_seconds", signals.get("signal_age_seconds")), 0.0)
    if _truthy_high(ctx.get("stale_signal")) or _truthy_high(signals.get("stale")) or age >= 900:
        tokens.append("stale_signal_risk")
        evidence["signal_age_seconds"] = age or "stale_flag"

    return _report("InfraRiskGhostExpert", tokens, evidence)


def extract_ghost_tokens(candidate: DecisionCandidate) -> list[GhostTokenReport]:
    """Run deterministic ghost-token experts. No prose, LLM, network, or broker calls."""

    return [
        _macro_risk(candidate),
        _flow_risk(candidate),
        _human_risk(candidate),
        _infra_risk(candidate),
    ]


def _flatten_tokens(reports: Iterable[GhostTokenReport]) -> list[str]:
    tokens: list[str] = []
    for report in reports:
        tokens.extend(report.ghost_tokens)
    return sorted(dict.fromkeys(tokens))


def _initial_uncertainty(reports: list[GhostTokenReport]) -> float:
    tokens = _flatten_tokens(reports)
    if not reports:
        return 0.2
    active = [r.uncertainty for r in reports if r.ghost_tokens]
    if not active:
        return 0.24
    token_pressure = min(0.28, len(tokens) * 0.035)
    return round(_clamp((sum(active) / len(active)) + token_pressure), 3)


def run_rumination(
    initial_uncertainty: float,
    context: dict[str, Any],
    *,
    u_thresh: float = U_THRESH,
    epsilon: float = EPSILON,
    max_cycles: int = MAX_CYCLES,
) -> list[RuminationState]:
    """Bounded heuristic rumination. Never calls external systems."""

    current = _clamp(initial_uncertainty)
    trace: list[RuminationState] = []
    previous: float | None = None

    match_count = int(context.get("experience_count", 0) or 0)
    evidence_strength = _clamp(float(context.get("evidence_strength", 0.0) or 0.0))
    severe_count = int(context.get("severe_count", 0) or 0)

    for cycle in range(1, max(1, max_cycles) + 1):
        if cycle > 1:
            reduction = 0.025 + (0.025 * min(match_count, 3)) + (0.08 * evidence_strength)
            reduction -= 0.015 * severe_count
            reduction = _clamp(reduction, 0.0, 0.16)
            current = _clamp(current - reduction)

        delta_u = None if previous is None else round(previous - current, 4)
        if current <= u_thresh:
            status = "within_threshold"
        elif cycle == max_cycles:
            status = "max_cycles_high_uncertainty"
        elif delta_u is not None and delta_u >= epsilon:
            status = "improving"
        else:
            status = "stalled"

        trace.append(
            RuminationState(
                cycle=cycle,
                uncertainty=round(current, 4),
                delta_u=delta_u,
                status=status,
            )
        )
        if current <= u_thresh:
            break
        previous = current

    return trace


def _amount_pressure(amount_cad: float | None) -> float:
    if amount_cad is None:
        return 0.06
    if amount_cad <= 250:
        return 0.03
    if amount_cad <= 1000:
        return 0.08
    if amount_cad <= 5000:
        return 0.16
    return 0.24


def score_consequence(
    candidate: DecisionCandidate,
    ghost_tokens: list[str],
    experiences: list[ExperienceMatch],
) -> ConsequenceScore:
    """Score candidate utility. Higher utility means safer to allow."""

    severe_tokens = {
        "fomo_pattern_detected",
        "revenge_trade_pattern",
        "leverage_impulse",
        "execution_slippage_risk",
        "data_quality_low",
        "stale_signal_risk",
        "fake_breakout_possible",
        "rate_shock_possible",
    }
    severe_count = len(severe_tokens & set(ghost_tokens))
    experience_pressure = min(0.35, sum(m.weighted_score for m in experiences[:3]) * 0.20)
    token_pressure = min(0.42, len(ghost_tokens) * 0.055 + severe_count * 0.06)
    amount_pressure = _amount_pressure(candidate.amount_cad)
    pressure = _clamp(token_pressure + experience_pressure + amount_pressure)

    data_low = "data_quality_low" in ghost_tokens
    stale = "stale_signal_risk" in ghost_tokens
    leveraged = "leverage_impulse" in ghost_tokens

    delivery_7d = _clamp(0.88 - (0.10 * severe_count) - (0.18 if leveraged else 0.0))
    revenue_risk = _clamp(0.90 - pressure - (0.10 if leveraged else 0.0))
    chaos_reduction = _clamp(
        0.84 - token_pressure - (0.12 if "fomo_pattern_detected" in ghost_tokens else 0.0)
    )
    truthfulness = _clamp(0.92 - (0.28 if data_low else 0.0) - (0.22 if stale else 0.0))
    cost_risk = _clamp(0.90 - amount_pressure - (0.08 * severe_count))

    weights = {
        "delivery_7d": 0.15,
        "revenue_risk": 0.30,
        "chaos_reduction": 0.20,
        "truthfulness": 0.20,
        "cost_risk": 0.15,
    }
    utility = (
        delivery_7d * weights["delivery_7d"]
        + revenue_risk * weights["revenue_risk"]
        + chaos_reduction * weights["chaos_reduction"]
        + truthfulness * weights["truthfulness"]
        + cost_risk * weights["cost_risk"]
    )

    return ConsequenceScore(
        delivery_7d=round(delivery_7d, 4),
        revenue_risk=round(revenue_risk, 4),
        chaos_reduction=round(chaos_reduction, 4),
        truthfulness=round(truthfulness, 4),
        cost_risk=round(cost_risk, 4),
        utility=round(_clamp(utility), 4),
    )


def _confidence(decision: str, uncertainty: float, utility: float, ghost_count: int) -> float:
    margin = abs(utility - 0.55)
    if decision == "ALLOW":
        base = 0.72 + margin
    elif decision == "BLOCK":
        base = 0.76 + margin + min(0.10, ghost_count * 0.01)
    else:
        base = 0.62 + min(0.12, margin)
    return round(_clamp(base - (uncertainty * 0.18)), 4)


def _summary(decision: str, ghost_tokens: list[str], utility: float, uncertainty: float) -> str:
    if decision == "ALLOW":
        return (
            "SDCA-Lite ALLOW: candidate utility is sufficient and uncertainty is below the "
            "defensive threshold. No broker action is executed."
        )
    if decision == "BLOCK":
        top = ", ".join(ghost_tokens[:4]) or "latent risk"
        return (
            f"SDCA-Lite BLOCK: latent risk tokens ({top}) push utility to {utility:.2f} "
            f"with uncertainty {uncertainty:.2f}. No broker action is executed."
        )
    return (
        "SDCA-Lite REVIEW: candidate is not clean enough to allow automatically and not "
        "severe enough for a hard block. Human review is required."
    )


def evaluate_decision_with_sdca(candidate: DecisionCandidate) -> RiskFirewallDecision:
    """Evaluate a candidate decision with the F51 Cognitive Risk Firewall."""

    reports = extract_ghost_tokens(candidate)
    ghost_tokens = _flatten_tokens(reports)
    matches = retrieve_experiences(ghost_tokens, candidate, top_k=3)
    initial_uncertainty = _initial_uncertainty(reports)
    severe_count = len(
        {
            "fomo_pattern_detected",
            "leverage_impulse",
            "execution_slippage_risk",
            "data_quality_low",
            "stale_signal_risk",
            "fake_breakout_possible",
        }
        & set(ghost_tokens)
    )
    evidence_strength = _clamp(
        (0.25 if candidate.raw_signals else 0.0)
        + (0.25 if candidate.risk_context else 0.0)
        + min(0.35, len(matches) * 0.10)
    )
    rumination_trace = run_rumination(
        initial_uncertainty,
        {
            "experience_count": len(matches),
            "evidence_strength": evidence_strength,
            "severe_count": severe_count,
        },
    )
    final_uncertainty = (
        rumination_trace[-1].uncertainty if rumination_trace else initial_uncertainty
    )
    consequence = score_consequence(candidate, ghost_tokens, matches)

    if final_uncertainty > 0.78 and severe_count >= 2:
        decision = "BLOCK"
    elif consequence.utility < 0.45:
        decision = "BLOCK"
    elif consequence.utility < 0.65:
        decision = "REVIEW"
    elif final_uncertainty <= U_THRESH:
        decision = "ALLOW"
    else:
        decision = "REVIEW"

    confidence = _confidence(decision, final_uncertainty, consequence.utility, len(ghost_tokens))

    return RiskFirewallDecision(
        decision=decision,
        confidence=confidence,
        uncertainty=round(final_uncertainty, 4),
        ghost_tokens=ghost_tokens,
        matched_experiences=matches,
        rumination_trace=rumination_trace,
        consequence_score=consequence,
        human_summary=_summary(decision, ghost_tokens, consequence.utility, final_uncertainty),
        audit_log={
            "module": "SDCA-Lite",
            "version": "0.1",
            "firewall_name": "F51 Cognitive Risk Firewall",
            "thresholds": {
                "u_thresh": U_THRESH,
                "epsilon": EPSILON,
                "max_cycles": MAX_CYCLES,
                "block_utility_lt": 0.45,
                "review_utility_lt": 0.65,
            },
            "ghost_reports": [report.model_dump(mode="json") for report in reports],
            "initial_uncertainty": initial_uncertainty,
            "evidence_strength": round(evidence_strength, 4),
            "no_broker_execution": True,
            "no_external_api_calls": True,
            "no_price_prediction": True,
        },
    )
