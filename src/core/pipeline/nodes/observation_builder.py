"""Build observations for Bob's context window — extracted from agent.py.

Injects all pipeline state (portfolio, experts, guardrails, tools, F51, etc.)
as structured observations for the LLM conversation.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def build_observations(state: dict) -> list[str]:
    """Build ordered list of observation strings from pipeline state.

    These are injected into the LLM conversation as context for Bob.
    Order matters: CASE rules first, then system status, then evidence.
    """
    observations: list[str] = []

    # ── CASE CONTEXT: contrato obrigatorio ──
    _inject_case_context(state, observations)

    # ── SYSTEM STATUS (always included) ──
    _inject_system_status(state, observations)

    # ── FEEDBACK LOOP ──
    _inject_feedback_loop(state, observations)

    # ── RAG semantic search ──
    _inject_rag_knowledge(state, observations)

    # ── Evidence sections (ticker, data, math, experts, guardrails) ──
    _inject_evidence(state, observations)

    # ── F51 Dynamic Veto Gate ──
    _inject_social_veto(state, observations)

    return observations


def _inject_case_context(state: dict, observations: list[str]):
    case_context = state.get("case_context") or ""
    case_pending = state.get("case_pending") or []
    # Late import to avoid circular dependency
    from .generator import _has_actionable_market_request
    if not case_pending and _has_actionable_market_request(state):
        case_pending = ["scanner", "price_enrichment", "sentiment_check"]
    state["case_pending"] = case_pending

    if case_pending:
        pending_list = ", ".join(case_pending)
        observations.append(
            f"REGRAS DO CASE — Etapas pendentes: {pending_list}. "
            + "Voce NAO pode dar veredito final sem completar cada etapa. "
            + "Use as ferramentas: market_scan, collect_data, social_forensics, run_experts."
        )
    if case_context:
        observations.append(case_context)


def _inject_system_status(state: dict, observations: list[str]):
    sys_lines = []
    pf = state.get("portfolio_snapshot") or state.get("portfolio_context") or ""
    if pf and "offline" not in pf.lower():
        sys_lines.append(f"IBKR: CONNECTED — {pf[:300]}")
    else:
        sys_lines.append("IBKR: OFFLINE")
    gr = state.get("guardrail_hub") or {}
    gr_summary = gr.get("summary", {}) if isinstance(gr, dict) else {}
    if gr_summary:
        blockers = gr_summary.get("blocking_guardrails", [])
        sys_lines.append(
            f"Guardrails: {gr_summary.get('decision_counts', {}).get('ALLOW', '?')} allow, "
            f"{len(blockers)} blocking"
        )
    observations.append("SYSTEM STATUS:\n" + "\n".join(sys_lines))


def _inject_feedback_loop(state: dict, observations: list[str]):
    try:
        from core.trading.feedback_loop import get_feedback_loop
        feedback = get_feedback_loop()
        lessons_ctx = feedback.render_for_bob(max_chars=1500)
        if lessons_ctx:
            observations.append(lessons_ctx)
        stats = feedback.get_stats()
        if stats.get("lessons_logged", 0) > 0:
            observations.append(
                f"FEEDBACK: {stats['closed_trades']} trades fechados, "
                f"{stats['wins']}W/{stats['losses']}L "
                f"(win rate: {stats.get('win_rate', 0):.0%}), "
                f"{stats['lessons_logged']} lições aprendidas."
            )
        try:
            cal = feedback.calibrate_confidence()
            if cal.get("status") == "calibrated":
                observations.append(f"CALIBRAGEM: {cal.get('interpretation', '')}")
        except Exception:
            pass
    except Exception:
        pass


def _inject_rag_knowledge(state: dict, observations: list[str]):
    try:
        from core.rag.engine import forensic_rag
        message = state.get("message", "")
        ticker = state.get("ticker", "")
        query = f"{ticker} {message}" if ticker else message
        if len(query) > 20:
            rag_results = forensic_rag.search(query, top_k=3)
            if rag_results:
                rag_ctx = forensic_rag.format_context(rag_results, max_chars=800)
                observations.append("RAG KNOWLEDGE:\n" + rag_ctx)
    except Exception:
        pass


def _inject_evidence(state: dict, observations: list[str]):
    """Inject all collected tool evidence into observations."""

    # Simple key-value evidence (no wrapping needed)
    if state.get("ticker"):
        ticker = state.get("ticker")
        has_data = bool(state.get("data") or state.get("data_context"))
        status = "DATA AVAILABLE" if has_data else "NO MARKET DATA — CALL collect_data"
        observations.append(f"Current Ticker: {ticker} ({status})")

        # Inject pre-computed expert analyses from learner 24/7
        try:
            from core.trading.batch_expert_runner import get_expert_analysis, get_expert_summary
            precomputed = get_expert_analysis(ticker)
            if precomputed:
                summary = get_expert_summary(ticker)
                observations.append(f"PRE-COMPUTED EXPERT ANALYSIS (24/7 learner):\n{summary}")
        except Exception:
            pass

        # Inject cached OHLCV summary
        try:
            from core.trading.historical_cache import get_cached_ohlcv
            ohlcv = get_cached_ohlcv(ticker, days=30)
            if ohlcv:
                closes = [c["close"] for c in ohlcv[-30:]]
                volumes = [c["volume"] for c in ohlcv[-30:]]
                high30 = max(c["high"] for c in ohlcv[-30:])
                low30 = min(c["low"] for c in ohlcv[-30:])
                latest = ohlcv[-1]
                observations.append(
                    f"OHLCV CACHE (30 days, pre-computed):\n"
                    f"  Latest: ${latest['close']:.2f} (vol: {latest['volume']:,.0f})\n"
                    f"  30d range: ${low30:.2f} - ${high30:.2f}\n"
                    f"  30d avg close: ${sum(closes)/len(closes):.2f}\n"
                    f"  30d avg volume: {sum(volumes)/len(volumes):,.0f}"
                )
        except Exception:
            pass
    if state.get("data_context"):
        ctx = str(state.get("data_context"))
        # Never truncate mid-number or mid-word
        if len(ctx) > 4000:
            ctx = ctx[:4000].rsplit(" ", 1)[0] + "\n... (truncated)"
        observations.append(f"Data/Scan Context (REAL MARKET DATA — use these exact values):\n{ctx}")
    if state.get("expert_summary"):
        observations.append(f"Expert Committee Summary:\n{state.get('expert_summary')}")
    if state.get("trinity_report"):
        observations.append(f"Trinity Deliberation:\n{state.get('trinity_report')}")
    if state.get("portfolio_snapshot"):
        observations.append(state.get("portfolio_snapshot"))
    if state.get("rag_context"):
        observations.append(f"RAG Forensics Context:\n{state.get('rag_context')}")
    if state.get("last_tool_result"):
        observations.append(f"LAST TOOL EXECUTION RESULT:\n{state.get('last_tool_result')}")

    # JSON-dumped evidence
    _inject_json_evidence(state, observations)

    # Expert weights
    if state.get("expert_weights"):
        observations.append(
            f"Expert Reliability Weights (dynamic, context-adjusted):\n"
            f"{json.dumps(state.get('expert_weights'), ensure_ascii=False)}\n"
            f"Higher weight = more reliable for this specific scenario. "
            f"Give more weight to high-weight experts in your final answer. "
            f"social_forensics (>0.30) has VETO power if manipulation_score >= 70."
        )

    # Executed tools
    if state.get("executed_tools"):
        observations.append(
            "Tools already executed in this run: "
            + ", ".join(str(tool) for tool in state.get("executed_tools", []))
            + ". Do NOT call these tools again with the same parameters. "
            + "Use existing results or call final_answer."
        )

    # Errors
    if state.get("errors"):
        observations.append(
            "Errors/Warnings encountered during tool execution:\n"
            + "\n".join(f"- {err}" for err in state.get("errors", []))
        )


def _inject_json_evidence(state: dict, observations: list[str]):
    """Inject evidence that requires JSON serialization for the LLM."""
    json_keys = {
        "math_report": "Math Report",
        "f51_verdict": "F51 Verdict",
        "neural_decision": "Neural Decision",
    }
    for key, label in json_keys.items():
        value = state.get(key)
        if value:
            observations.append(f"{label}:\n{json.dumps(value, ensure_ascii=False)}")

    # Dictionary-typed evidence (only if truthy)
    dict_keys = {
        "sdca_firewall": "SDCA Firewall",
        "guardrail_hub": "Guardrail Hub",
        "decision_trace": "Decision Trace",
    }
    for key, label in dict_keys.items():
        value = state.get(key)
        if isinstance(value, dict) and value:
            observations.append(f"{label}:\n{json.dumps(value, ensure_ascii=False)}")

    # PennyLab (either key)
    pennylab = state.get("pennylab_result") or state.get("pennylab")
    if pennylab:
        observations.append(f"PennyLab Result:\n{json.dumps(pennylab, ensure_ascii=False)}")


def _inject_social_veto(state: dict, observations: list[str]):
    social_veto = state.get("social_forensics_veto")
    if social_veto:
        veto_reason = social_veto.get("reason", "manipulation_detected")
        veto_score = social_veto.get("manipulation_score", 0)
        observations.append(
            f"CRITICAL VETO: Social Forensics expert detected synthetic manipulation "
            f"(score: {veto_score}/100). Reason: {veto_reason}. "
            f"You MUST NOT recommend buying this asset. "
            f"Your final_answer MUST include this warning prominently."
        )
