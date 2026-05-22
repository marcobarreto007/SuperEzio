"""CEO prompt builder â€” Qwen3.6-35B, section-based, no model branching."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..contracts import PipelineState

from ..intents import detect_complex_finance_intent
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
        return "Bob CEO guidance:\n"
    has_data = bool(ticker or state.get("data_context") or state.get("expert_summary"))
    if intent == "general_question" and not has_data:
        return ""
    return "## Analysis\n\n"


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
    "sdca_firewall": ["sdca", "firewall", "block", "review", "ghost"],
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
            (state.get("pennylab") or state.get("pennylab_result") or {}).get("decision")
        ),
        "experts": bool(state.get("expert_summary")),
        "neural": bool(
            state.get("neural_decision") and "error" not in state.get("neural_decision", {})
        ),
        "sdca_firewall": bool(
            state.get("sdca_firewall") and "error" not in state.get("sdca_firewall", {})
        ),
        "f51": bool(state.get("f51_verdict")),
        "rag_forensics": bool(state.get("rag_context")),
    }


def _render_module_contract(state: PipelineState) -> str:
    """Render mandatory module coverage contract for CEO output validation."""
    presence = _required_module_presence(state)
    available = [name for name, ok in presence.items() if ok]
    if not available:
        return ""
    checklist = "\n".join(f"- {name}: AVAILABLE (must be referenced)" for name in available)
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


def _evaluate_module_coverage(text: str, state: PipelineState) -> tuple[list[str], list[str]]:
    """Return (required_modules, missing_modules) for CEO output."""
    route = state.get("route", "general")
    has_market_context = bool(
        state.get("ticker")
        or state.get("data_context")
        or state.get("f51_verdict")
        or state.get("neural_decision")
        or (state.get("pennylab") or state.get("pennylab_result") or {}).get("decision")
    )
    if route == "general" and not has_market_context:
        return [], []

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


def _format_sdca_firewall(sdca: dict[str, Any]) -> str:
    """Compact SDCA-Lite block for CEO prompt."""
    if not sdca or sdca.get("error"):
        return ""
    lines = ["[SDCA_FIREWALL]"]
    for key in (
        "decision",
        "confidence",
        "uncertainty",
        "ghost_tokens",
        "human_summary",
    ):
        val = sdca.get(key)
        if val not in (None, "", [], {}):
            lines.append(f"{key}={val}")
    score = sdca.get("consequence_score")
    if isinstance(score, dict) and score:
        lines.append(f"consequence_score={score}")
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



def _build_complex_finance_prompt(raw_message: str) -> str:
    """Build a specialized CEO prompt for complex finance advisory questions.

    This produces the 12-section decision framework contract instead of the
    generic 'answer directly' prompt. Used for capital allocation, macro thesis,
    real estate vs markets, and similar complex advisory questions.
    """
    return "\n\n".join(
        [
            MODEL_PROMPTS["local"]["persona"],
            (
                "COMPLEX FINANCE ADVISORY CONTRACT:\n"
                "The user is asking a complex financial strategy/framework question.\n"
                "You must answer with a SERIOUS, QUANTITATIVE decision framework.\n"
                "Your answer should feel like a family CFO framework, not a generic financial blog.\n"
                "Do NOT provide generic advice. Do NOT scan for tickers.\n"
                "Do NOT pretend you collected market data.\n\n"
                "You must NOT provide regulated personalized financial advice as a licensed advisor.\n"
                "But you MUST provide educational frameworks, hypothetical capital allocations under explicit assumptions, scenario analysis, decision gates, missing data checklists, conditional recommendations, and risk warnings.\n\n"
                "OVERBLOCKING PROTECTION RULE:\n"
                "For PERSONAL_FINANCE, CAPITAL_ALLOCATION, ASSET_ALLOCATION, EDUCATION_INVESTMENT, BUSINESS_CAPITAL:\n"
                "Do not refuse unless the user asks for:\n"
                "- guaranteed returns\n"
                "- exact personalized investment orders\n"
                "- legal/tax filing instructions as a substitute for a professional\n"
                "- deception, evasion, or fraud\n\n"
                "Otherwise, you MUST answer. Your answer MUST follow this exact 12-section structure:\n\n"
                "1. **Scope disclaimer** — one short sentence: \"This is an educational framework, not personalized financial advice.\"\n"
                "2. **Question Classification** — identify the type: CAPITAL_ALLOCATION, MACRO_THESIS, REAL_ESTATE_VS_MARKETS, PERSONAL_FINANCE, ASSET_ALLOCATION, BUSINESS_CAPITAL, FRAUD_RISK, EDUCATION_INVESTMENT, or UNKNOWN\n"
                "3. **Assumptions** — state all assumptions being made (Key Assumptions). Always label scenario numbers, returns, and probabilities as illustrative assumptions.\n"
                "4. **Missing Data** — what data would be needed for a definitive answer\n"
                "5. **Decision Variables** — the factors that drive the decision\n"
                "6. **Quantitative Thresholds** — specific numbers, ranges, formulas, or decision gates. Avoid vague thresholds like \"risk capacity > $50K\". Instead, you MUST use actionable gates:\n"
                "   - emergency fund months (e.g., 3-6 months based on income stability)\n"
                "   - debt interest rate (e.g., pay off debt with interest > 6-8% first)\n"
                "   - income stability (e.g., stable salary vs unstable freelance)\n"
                "   - liquidity need\n"
                "   - time-to-cashflow for business equipment\n"
                "   - tax-advantaged account availability\n"
                "7. **Scenario Analysis** — base case, downside case, upside case with numbers. You must explicitly label all scenario numbers, returns, and probabilities as illustrative assumptions (e.g., \"illustrative scenario assumptions\"). Do NOT invent exact expected returns or probabilities unless they are explicitly sourced.\n"
                "8. **Ranked Allocation / Framework** — ordered ranking of options with rationale (Ranked Decision). Every allocation must include the exact percentage, and you must explain why each bucket gets that percentage. Allocations must sum to exactly 100%.\n"
                "9. **Decision Gates** — triggers that would flip the recommendation (What Would Change the Decision), main risks (Main Risks), and conditional logic. State clearly \"what changes the allocation\" in this section.\n"
                "10. **Final Recommendation Under Assumptions** — clear, actionable next step (Final Recommendation)\n"
                "11. **Confidence Level** — honest assessment with stated uncertainty\n"
                "12. **Professional Caveat** — suggestion to consult a CFP as a final caveat, not as the whole answer\n\n"
                "Mandatory Disclaimer Style:\n"
                "Allowed:\n"
                "\"This is an educational framework, not personalized financial advice.\"\n"
                "Forbidden:\n"
                "\"I cannot provide a capital allocation plan.\"\n"
                "\"Please consult a CFP\" as the full response.\n"
                "\"I cannot help with this.\"\n\n"
                "TOPIC-SPECIFIC RULES:\n"
                "- Avoid fake precision: do not present annualized return ranges as forecasts unless backed by an explicit data/source. Do NOT invent exact expected returns or probabilities unless they are explicitly sourced.\n"
                "- Label all scenario numbers, returns, and probabilities as illustrative assumptions.\n"
                "- Ensure proposed portfolio allocations sum to exactly 100%. Every allocation must include why each bucket gets that percentage.\n"
                "- For Canadian personal finance: include CAD, liquidity, emergency reserve, TFSA/RRSP/RESP/FHSA account types only when relevant, and explicitly state that tax rules depend on the individual's situation.\n"
                "- For real estate vs markets: include cap rate, cash-on-cash return, mortgage rate sensitivity, vacancy stress, maintenance reserve, insurance, taxes, liquidity, concentration risk, and opportunity cost vs diversified equity.\n"
                "- For macro thesis: first build the thematic exposure logic before giving stock-screening criteria. Separate secular trend, valuation risk, concentration risk, picks-and-shovels infrastructure, hype zones, position sizing logic, and rebalancing discipline.\n"
                "- For AI investment thesis, explicitly separate: 1. infrastructure winners, 2. monetization-risk companies, 3. hype/pivot companies, 4. valuation traps, 5. portfolio sizing, 6. rebalancing rules, and 7. maximum total AI-theme exposure inside the full portfolio.\n"
                "- For capital allocation: include high-interest debt threshold, emergency reserve, reversibility, time-to-cashflow, and family stability.\n\n"
                "Answer in the user's language. Use numbers, not generalities."
            ),
            f"USER: {raw_message}",
        ]
    )


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

    # â”€â”€ Casual / greeting â”€â”€
    has_financial = bool(
        ticker
        or state.get("data_context")
        or state.get("f51_verdict")
        or state.get("neural_decision")
        or bool((state.get("pennylab") or state.get("pennylab_result") or {}).get("decision"))
    )

    # Complex finance questions must be caught BEFORE the msg_has_ticker check
    # because words like "AI", "CAD", "ETF" in complex finance questions
    # false-positive on the uppercase ticker regex.
    if intent == "general_question" and not has_financial:
        if detect_complex_finance_intent(raw_message):
            return _build_complex_finance_prompt(raw_message)

    msg_has_ticker = bool(re.search(r"\b[A-Z]{1,5}(?:\.[A-Z]{1,2})?\b", raw_message))
    if intent == "general_question" and not has_financial and not msg_has_ticker:
        return "\n\n".join(
            [
                MODEL_PROMPTS["local"]["persona"],
                "Answer the user's question directly in natural language. "
                "If the user asks for financial education or general risk advice, "
                "give practical guidance without pretending market data was collected.",
                f"USER: {raw_message}",
            ]
        )

    # â”€â”€ Structured analysis â”€â”€
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
        f"Discuss risk and evidence in that horizon. Do not shorten the user's timeframe.\n"
        f"If the evidence cannot support a confident view for {effective_horizon}, say so plainly.\n"
    )

    parts = [
        "PIPELINE_OBLIGATION: "
        "You are NOT a standalone LLM. A 10-node deterministic pipeline ran "
        "BEFORE this prompt. Its output is below. EVERY module with data "
        "MUST appear in your answer. The RL RewardFunction and SDCA-Lite Cognitive "
        "Risk Firewall score every answer. Skipping a module with data is invalid.\n\n"
        "LANGUAGE: answer in the user's language when it is clear. If the user wrote "
        "in Portuguese, answer in Portuguese. If the user wrote in English, answer in English.\n\n"
        "You are the CEO of SuperEzio (Bob). You provide financial decision support "
        "in natural language. You are NOT a broker execution engine and you must not "
        "turn the answer into a direct trade order.\n\n"
        "MANDATORY FORMAT:\n"
        "```\n"
        "Bob's read: plain-language answer\n"
        "Confidence: 0-100%, with uncertainty\n"
        "Evidence: what the modules say\n"
        "Risks to check before acting: concrete checklist\n"
        "Practical next step: study, wait, review, watchlist, avoid, or small-position planning\n"
        "```\n\n"
        "Then explain WHY. Reference EVERY available module below by name:\n"
        "- DATA: what the DataCollector shows\n"
        "- PENNYLAB: what forensic experts detected\n"
        "- EXPERTS: what the expert committee concluded\n"
        "- NEURAL_DECISION: directional probability, expected return signal, regime, drawdown risk\n"
        "- SDCA_FIREWALL: defensive ALLOW, BLOCK, or REVIEW gate before final action\n"
        "- RAG_FORENSICS: what historical patterns match\n"
        "- F51_VERDICT: what the unified scoring says\n\n"
        "If a module has no data, say '[MODULE] MISSING - confidence reduced'.\n"
        "If a module has data, interpret it into risk and evidence, not a broker instruction.\n\n"
        "RULES:\n"
        "- Answer the user's actual question first.\n"
        "- Never output a naked directive like 'VERDICT: ... -> SHORT'.\n"
        "- Never issue a direct buy/sell/short order.\n"
        "- Cite evidence_ids for every claim.\n"
        "- Be direct, but keep claims proportional to uncertainty and data quality."
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
        parts.append(f"DATA:\n{data_ctx[:3000]}")
    elif route in ("ticker_analysis", "market_scan"):
        parts.append("DATA:\nNo DataCollector evidence. Do not invent prices or fundamentals.")

    rag_ctx = state.get("rag_context", "")
    if rag_ctx:
        parts.append(f"RAG_FORENSICS:\n{rag_ctx[:1200]}")

    pennylab_raw = state.get("pennylab") or state.get("pennylab_result") or {}
    pennylab_block = _format_pennylab(pennylab_raw)
    if pennylab_block:
        parts.append(f"PENNYLAB:\n{pennylab_block[:1200]}")
    else:
        parts.append("PENNYLAB:\nNo PennyLab evidence.")

    expert_summary = state.get("expert_summary", "")
    if expert_summary:
        parts.append(f"EXPERTS:\n{expert_summary[:3000]}")
    else:
        parts.append("EXPERTS:\nNo expert committee output.")

    neural = state.get("neural_decision") or {}
    if neural and "error" not in neural:
        neural_block = _format_neural_decision(neural)
        if neural_block:
            parts.append(f"NEURAL_DECISION:\n{neural_block[:1200]}")
    else:
        parts.append("NEURAL_DECISION:\nNeuralDecisionExpert not available for this ticker.")

    sdca = state.get("sdca_firewall") or {}
    sdca_block = _format_sdca_firewall(sdca)
    if sdca_block:
        parts.append(
            "SDCA_FIREWALL:\n"
            f"{sdca_block[:1200]}\n"
            "If decision=BLOCK, final answer must mark the action as blocked/defensive. "
            "If decision=REVIEW, final answer must require human review or reduced confidence."
        )

    # F51 verdict summary
    f51 = state.get("f51_verdict") or {}
    if f51:
        f51_block = (
            f"F51_VERDICT: passed={f51.get('passed')}, "
            f"confidence={f51.get('confidence')}, "
            f"factors={f51.get('factors', {})}"
        )
        parts.append(f51_block)

    contract = _render_module_contract(state)
    if contract:
        parts.append(contract)

    # ── Output enforcement for quantized models ──
    # Q4_K_M models tend to truncate. This block is placed LAST so it's
    # fresh in the model's attention window.
    parts.append(
        "CRITICAL_OUTPUT_REQUIREMENT:\n"
        "Your answer MUST contain these exact section headers, one per line, "
        "even if the section says MISSING:\n"
        "## DATA\n"
        "## F51_VERDICT\n"
        "## EXPERTS\n"
        "## NEURAL_DECISION\n"
        "## SDCA_FIREWALL\n"
        "## RAG_FORENSICS\n"
        "## PENNYLAB\n\n"
        "For each section write 1-3 sentences in plain language. "
        "If a module has no data, write 'MISSING — confidence reduced'.\n"
        "Then write '## BOB_VERDICT' with your final plain-language verdict.\n"
        "Do NOT skip any section header. This is mandatory."
    )

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
