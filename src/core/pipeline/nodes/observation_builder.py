"""Build observations for Bob's context window — extracted from agent.py.

Injects all pipeline state (portfolio, experts, guardrails, tools, F51, etc.)
as structured observations for the LLM conversation.

All JSON data is converted to FORMATTED TEXT before injection — LLMs (especially
quantized) perform better with flat text than with nested JSON.
"""

from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger(__name__)

# Configurable data_context truncation limit.
# Can be overridden via env var SUPEREZIO_DATA_CONTEXT_MAX_CHARS.
# math_prompt is injected separately (never truncated), so this limit
# only affects raw news/sentiment/macro context.
DATA_CONTEXT_MAX_CHARS: int = int(os.getenv("SUPEREZIO_DATA_CONTEXT_MAX_CHARS", "4000"))

# ── Formatters: convert JSON dicts to readable flat text ──


def format_math_report(report: dict) -> str:
    """Convert math_report dict to human-readable text."""
    lines = ["═══ MATH REPORT ═══"]
    ticker = report.get("ticker", "")
    price = report.get("price", report.get("close", ""))
    if ticker:
        price_str = f"${price:.2f}" if isinstance(price, (int, float)) else str(price)
        lines.append(f"Ticker: {ticker} | Price: {price_str}")

    # Technical indicators
    tech = report.get("technical_indicators", report.get("technicals", {}))
    if tech:
        parts = []
        rsi = tech.get("rsi", tech.get("RSI"))
        if rsi is not None:
            parts.append(f"RSI: {rsi}")
        macd = tech.get("macd", tech.get("MACD"))
        if macd is not None:
            sign = "+" if isinstance(macd, (int, float)) and macd >= 0 else ""
            parts.append(f"MACD: {sign}{macd}")
        sma = tech.get("sma_20", tech.get("SMA20", tech.get("sma20")))
        if sma is not None:
            parts.append(f"SMA20: ${sma}")
        ema = tech.get("ema_20", tech.get("EMA20", tech.get("ema20")))
        if ema is not None:
            parts.append(f"EMA20: ${ema}")
        if parts:
            lines.append("Technicals: " + " | ".join(parts))

    # Returns
    ret = report.get("returns", report.get("performance", {}))
    if isinstance(ret, dict):
        parts = []
        ann = ret.get("annualized", ret.get("annualized_return"))
        if ann is not None:
            pct = ann * 100 if abs(ann) < 1 else ann
            parts.append(f"annualized={pct:.1f}%")
        sharpe = ret.get("sharpe", ret.get("sharpe_ratio"))
        if sharpe is not None:
            parts.append(f"Sharpe={sharpe}")
        sortino = ret.get("sortino", ret.get("sortino_ratio"))
        if sortino is not None:
            parts.append(f"Sortino={sortino}")
        if parts:
            lines.append("Returns: " + " | ".join(parts))

    # Risk
    risk = report.get("risk", report.get("risk_metrics", {}))
    if isinstance(risk, dict):
        parts = []
        var95 = risk.get("var_95", risk.get("VaR_95", risk.get("var95")))
        if var95 is not None:
            sign = "-" if isinstance(var95, (int, float)) and var95 < 0 else ""
            lines.append(f"Risk: VaR_95={sign}${abs(var95):.2f}")
        mdd = risk.get("max_drawdown", risk.get("max_drawdown_pct"))
        if mdd is not None:
            pct = mdd * 100 if abs(mdd) < 1 else mdd
            lines.append(f"Risk: max_drawdown={pct:.1f}%")
        kelly = risk.get("kelly", risk.get("kelly_fraction", risk.get("kelly_criterion")))
        if kelly is not None:
            pct = kelly * 100 if abs(kelly) < 1 else kelly
            lines.append(f"Risk: Kelly={pct:.1f}%")

    # Crisis
    crisis = report.get("crisis", report.get("crisis_metrics", {}))
    if isinstance(crisis, dict):
        agg = crisis.get("aggregate", crisis.get("crisis_score"))
        if agg is not None:
            alert = crisis.get("alert_level", crisis.get("level", "unknown"))
            lines.append(f"Crisis: aggregate={agg} (alert_level={alert})")

    # Fallback: dump any remaining top-level keys not yet shown
    shown_keys = {
        "ticker",
        "price",
        "close",
        "technical_indicators",
        "technicals",
        "returns",
        "performance",
        "risk",
        "risk_metrics",
        "crisis",
        "crisis_metrics",
    }
    extra = {k: v for k, v in report.items() if k not in shown_keys and not k.startswith("_")}
    if extra:
        for k, v in extra.items():
            if isinstance(v, (int, float)):
                lines.append(f"{k}: {v}")
            elif isinstance(v, str):
                lines.append(f"{k}: {v}")
    return "\n".join(lines)


def format_f51_verdict(f51: dict) -> str:
    """Convert f51_verdict dict to human-readable text."""
    lines = ["═══ F51 VERDICT ═══"]
    score = f51.get("score", f51.get("f51_score", ""))
    passed = f51.get("passed", f51.get("approved", ""))
    decision_score = f51.get("decision_score", f51.get("confidence", ""))
    lines.append(f"score={score} | passed={passed} | decision_score={decision_score}")

    # Factors breakdown
    factors = f51.get("factors", f51.get("scores", f51.get("breakdown", {})))
    if isinstance(factors, dict) and factors:
        factor_strs = [f"{k}={v}" for k, v in factors.items()]
        lines.append("Factors: " + ", ".join(factor_strs))

    # Extra fields
    extra = {
        k: v
        for k, v in f51.items()
        if k
        not in (
            "score",
            "f51_score",
            "passed",
            "approved",
            "decision_score",
            "confidence",
            "factors",
            "scores",
            "breakdown",
        )
        and not k.startswith("_")
    }
    for k, v in extra.items():
        if isinstance(v, (int, float, str)):
            lines.append(f"{k}: {v}")
    return "\n".join(lines)


def format_neural_decision(neural: dict) -> str:
    """Convert neural_decision dict to human-readable text."""
    lines = ["═══ NEURAL DECISION ═══"]
    regime = neural.get("regime", neural.get("market_regime", "unknown"))
    direction = neural.get("direction", neural.get("signal", neural.get("prediction", "HOLD")))
    confidence = neural.get("confidence", neural.get("score", ""))
    lines.append(f"Regime: {regime} | Direction: {direction} | Confidence: {confidence}")

    rec = neural.get("recommendation", neural.get("action", ""))
    if rec:
        lines.append(f"Recommendation: {rec}")

    dd_risk = neural.get("drawdown_risk", neural.get("max_drawdown", ""))
    if dd_risk:
        if isinstance(dd_risk, (int, float)):
            sign = "-" if dd_risk < 0 else ""
            lines.append(f"Drawdown Risk: {sign}{abs(dd_risk)}%")
        else:
            lines.append(f"Drawdown Risk: {dd_risk}")

    # Extra fields
    extra = {
        k: v
        for k, v in neural.items()
        if k
        not in (
            "regime",
            "market_regime",
            "direction",
            "signal",
            "prediction",
            "confidence",
            "score",
            "recommendation",
            "action",
            "drawdown_risk",
            "max_drawdown",
        )
        and not k.startswith("_")
    }
    for k, v in extra.items():
        if isinstance(v, (int, float, str)):
            lines.append(f"{k}: {v}")
    return "\n".join(lines)


def format_sdca(sdca: dict) -> str:
    """Convert sdca_firewall dict to human-readable text."""
    lines = ["═══ SDCA FIREWALL ═══"]
    decision = sdca.get("decision", sdca.get("status", sdca.get("verdict", "UNKNOWN")))
    risk_level = sdca.get("risk_level", sdca.get("severity", "unknown"))
    checks = sdca.get("cognitive_checks", sdca.get("checks_passed", sdca.get("checks", "")))
    total = sdca.get("total_checks", sdca.get("checks_total", ""))
    if checks and total:
        lines.append(
            f"Decision: {decision} | risk_level={risk_level} | cognitive_checks={checks}/{total} passed"
        )
    elif checks:
        lines.append(
            f"Decision: {decision} | risk_level={risk_level} | cognitive_checks={checks} passed"
        )
    else:
        lines.append(f"Decision: {decision} | risk_level={risk_level}")

    # Explanation / reason
    reason = sdca.get("reason", sdca.get("explanation", sdca.get("details", "")))
    if reason:
        lines.append(f"Reason: {reason}")

    extra = {
        k: v
        for k, v in sdca.items()
        if k
        not in (
            "decision",
            "status",
            "verdict",
            "risk_level",
            "severity",
            "cognitive_checks",
            "checks_passed",
            "checks",
            "total_checks",
            "checks_total",
            "reason",
            "explanation",
            "details",
        )
        and not k.startswith("_")
    }
    for k, v in extra.items():
        if isinstance(v, (int, float, str)):
            lines.append(f"{k}: {v}")
    return "\n".join(lines)


def format_guardrail_hub(guardrail: dict) -> str:
    """Convert guardrail_hub dict to human-readable text."""
    lines = ["═══ GUARDRAIL HUB ═══"]
    summary = guardrail.get("summary", guardrail)
    if not isinstance(summary, dict):
        summary = guardrail

    completed = summary.get(
        "completed", summary.get("executed_checks", summary.get("total_run", 0))
    )
    total = summary.get("total", summary.get("total_guardrails", summary.get("total_checks", 0)))
    if completed or total:
        lines.append(f"{completed}/{total} completed")

    counts = summary.get("decision_counts", summary.get("counts", summary.get("results", {})))
    if isinstance(counts, dict):
        allow = counts.get("ALLOW", counts.get("allow", 0))
        block = counts.get("BLOCK", counts.get("block", 0))
        review = counts.get("REVIEW", counts.get("review", 0))
        parts = []
        if allow:
            parts.append(f"{allow} ALLOW")
        if block:
            parts.append(f"{block} BLOCK")
        if review:
            parts.append(f"{review} REVIEW")
        if parts:
            lines.append(" | ".join(parts))

    blockers = summary.get(
        "blocking_guardrails", summary.get("blocked_by", summary.get("blockers", []))
    )
    if isinstance(blockers, list) and blockers:
        lines.append("Blocking: " + str(blockers))

    extra = {
        k: v
        for k, v in summary.items()
        if k
        not in (
            "completed",
            "executed_checks",
            "total_run",
            "total",
            "total_guardrails",
            "total_checks",
            "decision_counts",
            "counts",
            "results",
            "blocking_guardrails",
            "blocked_by",
            "blockers",
        )
        and not k.startswith("_")
    }
    for k, v in extra.items():
        if isinstance(v, (int, float, str)):
            lines.append(f"{k}: {v}")
    return "\n".join(lines)


def format_decision_trace(trace: dict) -> str:
    """Convert decision_trace dict to human-readable text."""
    lines = ["═══ DECISION TRACE ═══"]
    decision = trace.get("decision", trace.get("final_decision", trace.get("action", "")))
    confidence = trace.get("confidence", trace.get("overall_confidence", ""))
    model = trace.get("model", trace.get("model_used", trace.get("llm", "")))
    path = trace.get("path", trace.get("decision_path", trace.get("reasoning_path", "")))
    if decision:
        lines.append(f"Decision: {decision}")
    if confidence:
        lines.append(f"Confidence: {confidence}")
    if model:
        lines.append(f"Model: {model}")
    if path:
        if isinstance(path, list):
            for i, step in enumerate(path, 1):
                step_str = str(step)[:200]
                lines.append(f"  Step {i}: {step_str}")
        elif isinstance(path, str):
            lines.append(f"Path: {path[:300]}")

    extra = {
        k: v
        for k, v in trace.items()
        if k
        not in (
            "decision",
            "final_decision",
            "action",
            "confidence",
            "overall_confidence",
            "model",
            "model_used",
            "llm",
            "path",
            "decision_path",
            "reasoning_path",
        )
        and not k.startswith("_")
    }
    for k, v in extra.items():
        if isinstance(v, (int, float, str)):
            lines.append(f"{k}: {v}")
    return "\n".join(lines)


def format_pennylab(pennylab: dict) -> str:
    """Convert pennylab result dict to human-readable text."""
    lines = ["═══ PENNYLAB RESULT ═══"]
    signal = pennylab.get("signal", pennylab.get("verdict", pennylab.get("decision", "")))
    score = pennylab.get("score", pennylab.get("confidence", pennylab.get("pennylab_score", "")))
    if signal:
        lines.append(f"Signal: {signal}")
    if score:
        lines.append(f"Score: {score}")

    details = pennylab.get("details", pennylab.get("analysis", pennylab.get("reasoning", "")))
    if details:
        detail_str = str(details)
        if len(detail_str) > 600:
            detail_str = detail_str[:600] + "..."
        lines.append(f"Details: {detail_str}")

    extra = {
        k: v
        for k, v in pennylab.items()
        if k
        not in (
            "signal",
            "verdict",
            "decision",
            "score",
            "confidence",
            "pennylab_score",
            "details",
            "analysis",
            "reasoning",
        )
        and not k.startswith("_")
    }
    for k, v in extra.items():
        if isinstance(v, (int, float, str)):
            lines.append(f"{k}: {v}")
    return "\n".join(lines)


# ── End of formatters ──


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
                    f"  30d avg close: ${sum(closes) / len(closes):.2f}\n"
                    f"  30d avg volume: {sum(volumes) / len(volumes):,.0f}"
                )
        except Exception:
            pass
    if state.get("data_context"):
        ctx = str(state.get("data_context"))
        # Never truncate mid-number or mid-word
        if len(ctx) > DATA_CONTEXT_MAX_CHARS:
            ctx = ctx[:DATA_CONTEXT_MAX_CHARS].rsplit(" ", 1)[0] + "\n... (truncated)"
        observations.append(
            f"Data/Scan Context (REAL MARKET DATA — use these exact values):\n{ctx}"
        )
    if state.get("expert_summary"):
        observations.append(f"Expert Committee Summary:\n{state.get('expert_summary')}")
    if state.get("math_prompt"):
        # math_prompt is NEVER truncated — it contains critical RSI, MACD, Sharpe,
        # VaR, and Kelly calculations that must always reach Bob.
        observations.append(
            f"Math Analysis (RSI, MACD, Sharpe, VaR, Kelly):\n{state.get('math_prompt')}"
        )
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
    """Inject evidence using formatted text instead of raw JSON.

    Each field is converted via a dedicated format_*() function that produces
    flat, human-readable text — LLMs (especially quantized) perform better
    with this format than with nested JSON.
    """
    # ── Single-dict fields ──
    value = state.get("math_report")
    if value:
        observations.append(format_math_report(value))

    value = state.get("f51_verdict")
    if value:
        observations.append(format_f51_verdict(value))

    value = state.get("neural_decision")
    if value:
        observations.append(format_neural_decision(value))

    # ── Dictionary-typed fields (only if truthy dict) ──
    value = state.get("sdca_firewall")
    if isinstance(value, dict) and value:
        observations.append(format_sdca(value))

    value = state.get("guardrail_hub")
    if isinstance(value, dict) and value:
        observations.append(format_guardrail_hub(value))

    value = state.get("decision_trace")
    if isinstance(value, dict) and value:
        observations.append(format_decision_trace(value))

    # ── PennyLab (any key) ──
    pennylab = (
        state.get("pennylab_detection") or state.get("pennylab_result") or state.get("pennylab")
    )
    if isinstance(pennylab, dict) and pennylab:
        observations.append(format_pennylab(pennylab))

    # ── Mangala prompt (injected by graph.py) ──
    mangala_prompt = state.get("mangala_prompt")
    if mangala_prompt and isinstance(mangala_prompt, str):
        observations.append(f"MANGALA OPPORTUNITIES:\n{mangala_prompt}")


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
