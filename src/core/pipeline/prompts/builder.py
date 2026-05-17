"""CEO prompt builder — Qwen3.6-35B, section-based, no model branching."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..contracts import PipelineState

from ._prompts import MODEL_PROMPTS


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------


def ceo_system_prompt() -> str:
    """Return the CEO system prompt for local Qwen3.6-35B."""
    return MODEL_PROMPTS["local"]["system"]


# ---------------------------------------------------------------------------
# CEO assistant prefix (prefill technique to prevent refusals)
# ---------------------------------------------------------------------------


def _ceo_assistant_prefix(state: PipelineState) -> str:
    """Prefixo role=assistant para impedir recusa do modelo."""
    ticker = state.get("ticker", "")
    route = state.get("route", "general")
    intent = state.get("intent", "general_question")

    if intent == "explain_capabilities":
        return ""
    if route == "market_scan":
        return (
            "## Quantitative Market Scan\n\n"
            "### Volume Anomaly Shortlist\n\n"
            "Based on collected data:\n"
        )
    if ticker:
        return (
            "VERDICT: "
        )
    has_data = bool(ticker or state.get("data_context") or state.get("expert_summary"))
    if intent == "general_question" and not has_data:
        return ""
    return (
        "## Analysis\n\n"
    )


# ---------------------------------------------------------------------------
# Module coverage contract
# ---------------------------------------------------------------------------

_MODULE_KEYWORDS: dict[str, list[str]] = {
    "price": ["price", "close", "last"],
    "technical": ["rsi", "macd", "technical", "sma", "ema"],
    "profile": ["profile", "sector", "market cap", "fundamental"],
    "quant": ["monte carlo", "ml", "combined prob", "predictive"],
    "risk": ["risk", "var", "drawdown", "volatility", "cvar"],
    "macro": ["macro", "fed", "boc", "inflation", "rates", "yield"],
    "sentiment": ["sentiment", "news"],
    "reddit": ["reddit", "social"],
    "pennylab": ["pennylab", "forensic", "fraud", "manipulation"],
    "experts": ["experts", "committee", "fundamental", "technical", "risk"],
    "neural": ["neural", "direction prob", "regime", "expected return", "drawdown"],
    "f51": ["f51", "verdict", "confidence", "threshold"],
    "rag_forensics": ["rag", "forensics", "historical", "past case"],
}


def _required_module_presence(state: PipelineState) -> dict[str, bool]:
    """Which modules produced usable evidence for this request."""
    data = state.get("data") or {}

    def _has(key: str, source: dict | None = None) -> bool:
        src = source or data
        val = src.get(key)
        return bool(val and "error" not in val)

    return {
        "price": bool(data.get("price")),
        "technical": _has("technicals"),
        "profile": _has("profile"),
        "quant": _has("quant"),
        "risk": _has("risk"),
        "macro": _has("macro"),
        "sentiment": _has("sentiment"),
        "reddit": _has("reddit"),
        "pennylab": bool(
            (state.get("pennylab") or state.get("pennylab_result") or {}).get(
                "decision"
            )
        ),
        "experts": bool(state.get("expert_summary")),
        "neural": bool(state.get("neural_decision") and "error" not in state.get("neural_decision", {})),
        "f51": bool(state.get("f51_verdict")),
        "rag_forensics": bool(state.get("rag_context")),
    }


def _render_module_contract(state: PipelineState) -> str:
    """Render mandatory module coverage contract for CEO output validation."""
    presence = _required_module_presence(state)
    available = [name for name, ok in presence.items() if ok]
    if not available:
        return ""
    checklist = "\n".join(
        f"- {name}: AVAILABLE (must be referenced)" for name in available
    )
    sections = "\n".join(f"- SECTION [{name.upper()}]" for name in available)
    return (
        "[MANDATORY_MODULE_COVERAGE]\n"
        "You MUST explicitly reference every AVAILABLE module below.\n"
        "If any available module is omitted, the output is invalid.\n"
        "Available modules:\n"
        f"{checklist}\n\n"
        "Mandatory section headers in your answer:\n"
        f"{sections}\n"
    )


def _evaluate_module_coverage(
    text: str, state: PipelineState
) -> tuple[list[str], list[str]]:
    """Return (required_modules, missing_modules) for CEO output."""
    presence = _required_module_presence(state)
    required = [name for name, ok in presence.items() if ok]
    if not required:
        return [], []
    content = (text or "").lower()
    missing: list[str] = []
    for module in required:
        terms = _MODULE_KEYWORDS.get(module, [module])
        if not any(term in content for term in terms):
            missing.append(module)
    return required, missing


# ---------------------------------------------------------------------------
# Section formatters
# ---------------------------------------------------------------------------


def _format_pennylab(pennylab: dict[str, Any]) -> str:
    """Compact PennyLab block for CEO prompt."""
    if not pennylab or not pennylab.get("decision"):
        return ""
    lines = ["[PENNYLAB]"]
    for key in (
        "ticker",
        "decision",
        "mathcore_verdict",
        "confidence",
        "scores",
        "risks",
        "entry_conditions",
        "exit_conditions",
    ):
        val = pennylab.get(key)
        if val not in (None, "", [], {}):
            lines.append(f"{key}={val}")
    return "\n".join(lines)


def _format_neural_decision(neural: dict[str, Any]) -> str:
    """Compact NeuralDecisionExpert block for CEO prompt."""
    if not neural or neural.get("error"):
        return ""
    lines = ["[NEURAL_DECISION]"]
    direction = neural.get("direction_prob", {})
    if direction:
        lines.append(
            f"direction_prob=up:{direction.get('up', '?')} "
            f"down:{direction.get('down', '?')} "
            f"sideways:{direction.get('sideways', '?')}"
        )
    for key in (
        "expected_return",
        "drawdown_risk",
        "uncertainty",
        "regime",
        "recommendation",
        "veto",
        "reason",
        "timeframe",
    ):
        val = neural.get(key)
        if val is not None and val != "":
            lines.append(f"{key}={val}")
    return "\n".join(lines)


def _format_mandamentos(mandamentos: list[Any]) -> str:
    """Render user rules block."""
    if not mandamentos:
        return ""
    lines = ["[USER_RULES]"]
    for m in mandamentos:
        mid = getattr(m, "id", "") or "MANDAMENTO"
        mdata = getattr(m, "data", "")
        mregra = getattr(m, "regra", "")
        lines.append(f"- {mid} ({mdata}): {mregra}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main prompt builder
# ---------------------------------------------------------------------------


def build_ceo_prompt(
    state: PipelineState,
    mandamentos: list[Any] | None = None,
) -> str:
    """Build the full CEO prompt from pipeline state for Qwen3.6-35B."""
    mandamentos = mandamentos or []
    raw_message = state.get("message", "")
    intent = state.get("intent", "general_question")
    route = state.get("route", "general")
    ticker = state.get("ticker", "")

    # ── Casual / greeting ──
    has_financial = bool(
        ticker
        or state.get("data_context")
        or state.get("expert_summary")
        or bool(
            (state.get("pennylab") or state.get("pennylab_result") or {}).get(
                "decision"
            )
        )
    )
    msg_has_ticker = bool(re.search(r"\b[A-Z]{1,5}(?:\.[A-Z]{1,2})?\b", raw_message))
    msg_has_fin = bool(
        re.search(
            r"\b(analyz|analis|invest|trade|buy|sell|stock|price|chart|trend|"
            r"volume|market|risk|portfolio|dividend|candle|bullish|bearish|"
            r"RSI|MACD|SMA|EMA|Bollinger|support|resistance|pattern|forecast|"
            r"quarterly|earnings|financial|statement|P/E|market cap|sector)\b",
            raw_message,
            re.IGNORECASE,
        )
    )
    is_casual = (
        intent == "general_question"
        and not has_financial
        and not msg_has_ticker
        and not msg_has_fin
    )

    if is_casual:
        return "\n\n".join(
            [
                MODEL_PROMPTS["local"]["persona"],
                f"USER: {raw_message}",
            ]
        )

    # ── Structured analysis ──
    # Extract time horizon from the user message
    _horizon_match = re.search(
        r"(\d+)\s*(day|days|week|weeks|month|months)",
        raw_message,
        re.IGNORECASE,
    )
    _horizon_text = _horizon_match.group(0) if _horizon_match else ""

    # Use state-level time_horizon if present (set by orchestrator or UI)
    state_horizon = state.get("time_horizon", "")
    effective_horizon = _horizon_text or state_horizon or "14 days"

    horizon_constraint = (
        f"\n[CRITICAL_TIMEFRAME_CONSTRAINT]\n"
        f"The user's investment horizon is: {effective_horizon}.\n"
        f"Your TIMEFRAME field MUST be '{effective_horizon}' — NOT 1-3 days, NOT any other value.\n"
        f"Your TARGET price must be the expected price at the END of this timeframe ({effective_horizon}).\n"
        f"Your MOVEMENT % must reflect the expected change over {effective_horizon}.\n"
        f"If you cannot estimate a {effective_horizon} target, set CONFIDENCE lower and explain why.\n"
        f"DO NOT default to 1-3 days. DO NOT shorten the user's timeframe.\n"
    )

    parts = [
        "LANGUAGE: WRITE 100% IN ENGLISH. Even if the user wrote in Portuguese, "
        "Spanish, or any other language, your ENTIRE response MUST be in ENGLISH. "
        "Section headers, explanations, verdicts — EVERYTHING in English.\n\n"
        "You are the CEO of SuperEzio (Bob). You decide BUY, SELL, or HOLD. "
        "You are a TRADING DECISION ENGINE. The user is putting real money on the line "
        "and wants YOUR OPINION — not a data report, not a WATCHLIST, not a hedge.\n\n"
        "MANDATORY FORMAT:\n"
        "```\n"
        "VERDICT: BUY / SELL / HOLD\n"
        "CONFIDENCE: 0-100%\n"
        "TIMEFRAME: must match user's horizon\n"
        "ENTRY: current price\n"
        "TARGET: expected price at end of timeframe\n"
        "MOVEMENT: expected % gain or drop over the full timeframe\n"
        "STOP LOSS: suggested stop level\n"
        "```\n\n"
        "Then explain WHY. Reference EVERY available module below by name:\n"
        "- DATA: what the DataCollector shows\n"
        "- PENNYLAB: what forensic experts detected\n"
        "- EXPERTS: what the expert committee concluded\n"
        "- NEURAL_DECISION: directional probability, expected return, regime, drawdown risk\n"
        "- RAG_FORENSICS: what historical patterns match\n"
        "- F51_VERDICT: what the unified scoring says\n\n"
        "If a module has no data, say '[MODULE] MISSING — confidence reduced'.\n"
        "If a module has data, interpret it into a trading signal.\n\n"
        "RULES:\n"
        "- LANGUAGE: ENGLISH ONLY. NOT Portuguese. NOT any other language. ENGLISH.\n"
        "- ALWAYS give BUY, SELL, or HOLD — never refuse\n"
        "- Give a NUMERIC price target and % movement\n"
        "- Cite evidence_ids for every claim\n"
        "- Be AGGRESSIVE in your interpretation — the user wants conviction\n"
        "- Answer in English only",
        "",
        f"TASK: {raw_message}",
        f"INTENT: {intent} route={route}",
        horizon_constraint,
    ]

    if intent == "explain_capabilities":
        parts.append(
            "This is a method/capability question, not a market scan. "
            "Answer directly with the research tools and risk checks "
            "SuperEzio uses. Do not ask for a ticker."
        )

    chart_ctx = state.get("context", "")
    if chart_ctx:
        parts.append(f"CHART:\n{chart_ctx[:1000]}")

    data_ctx = state.get("data_context", "")
    if data_ctx:
        parts.append(f"DATA:\n{data_ctx[:1500]}")
    elif route == "ticker_analysis":
        parts.append(
            "DATA:\nNo DataCollector evidence. Do not invent prices or fundamentals."
        )

    rag_ctx = state.get("rag_context", "")
    if rag_ctx:
        parts.append(f"RAG_FORENSICS:\n{rag_ctx[:800]}")

    pennylab_raw = state.get("pennylab") or state.get("pennylab_result") or {}
    pennylab_block = _format_pennylab(pennylab_raw)
    if pennylab_block:
        parts.append(f"PENNYLAB:\n{pennylab_block[:800]}")
    else:
        parts.append("PENNYLAB:\nNo PennyLab evidence.")

    expert_summary = state.get("expert_summary", "")
    if expert_summary:
        parts.append(f"EXPERTS:\n{expert_summary[:1000]}")
    else:
        parts.append("EXPERTS:\nNo expert committee output.")

    neural = state.get("neural_decision") or {}
    if neural and "error" not in neural:
        neural_block = _format_neural_decision(neural)
        if neural_block:
            parts.append(f"NEURAL_DECISION:\n{neural_block[:800]}")
    else:
        parts.append("NEURAL_DECISION:\nNeuralDecisionExpert not available for this ticker.")

    contract = _render_module_contract(state)
    if contract:
        parts.append(contract)

    return "\n\n".join(parts)


def missing_ceo_text(
    ticker: str = "",
    route: str = "general",
    local_ready: bool = False,
) -> str:
    """Error text when local CEO is unavailable."""
    if not local_ready:
        return (
            "MODEL_MISSING: local Qwen3.6-35B CEO is offline.\n\n"
            f"Prepared route: {route} | ticker: {ticker or 'no ticker'}.\n"
            "Action: verify CEO model server is running on port 8082"
        )
    return (
        "MODEL_MISSING: local Qwen3.6-35B CEO did not respond.\n\n"
        f"Prepared route: {route} | ticker: {ticker or 'no ticker'}.\n"
        "Action: verify http://127.0.0.1:8082/health and http://127.0.0.1:8082/v1/models."
    )
