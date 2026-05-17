"""CEO prompt builder — Qwen3.6-35B, section-based, no model branching."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..contracts import PipelineState

from .gemma import MODEL_PROMPTS, SAFE_ACTIONS


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
            f"## Institutional Quantitative Analysis - {ticker}\n\n"
            "### Executive Summary\n\n"
            "Based on verified DataCollector evidence:\n"
        )
    has_data = bool(ticker or state.get("data_context") or state.get("expert_summary"))
    if intent == "general_question" and not has_data:
        return ""
    return (
        "## Quantitative Analysis\n\n### Key Findings\n\nBased on verified evidence:\n"
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
    parts = [
        "You are the CEO of SuperEzio (Bob), an institutional financial analysis platform. "
        "Analyze penny stocks, detect fraud, assess risk. Be direct and quantitative. "
        "Cite evidence from DataCollector. If evidence is missing, say what is missing. "
        "Answer in English only, 2 paragraphs max. "
        f"Pick one next step: {SAFE_ACTIONS}.",
        "",
        f"TASK: {raw_message}",
        f"INTENT: {intent} route={route}",
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
