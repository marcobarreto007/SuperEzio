"""CEO prompt builder -- Bob Core local, section-based, no model branching."""

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


def agent_system_prompt() -> str:
    """Return the CEO system prompt for local Bob Core."""
    return MODEL_PROMPTS["local"]["system"]


# ---------------------------------------------------------------------------
# CEO assistant prefix (prefill technique to prevent refusals)
# ---------------------------------------------------------------------------


def _agent_assistant_prefix(state: PipelineState) -> str:
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
        return "Bob guidance:\n"
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
    "math_report": ["math", "var", "sharpe", "kelly", "crisis"],
    "guardrail_hub": ["guardrail", "firewall", "blocked", "review"],
    "decision_trace": ["trace", "audit", "blame", "latency"],
    "trinity": ["trinity", "genie", "deep", "consensus", "deliberation"],
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
            isinstance(state.get("sdca_firewall"), dict)
            and state.get("sdca_firewall")
            and "error" not in state["sdca_firewall"]
        ),
        "f51": bool(state.get("f51_verdict")),
        "rag_forensics": bool(state.get("rag_context")),
        "math_report": bool(state.get("math_report")),
        "guardrail_hub": bool(state.get("guardrail_hub")),
        "decision_trace": bool(state.get("decision_trace")),
        "trinity": bool(state.get("trinity_report")),
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
    if not neural:
        return ""
    lines = ["[NEURAL_DECISION]"]
    for key in (
        "status",
        "decision",
        "calibration_status",
        "skill_status",
        "model_id",
        "as_of",
        "horizon",
        "prediction_set",
        "reason_codes",
    ):
        value = neural.get(key)
        if value not in (None, "", [], {}):
            lines.append(f"{key}={value}")
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
        "error",
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


def _format_math_report(report: dict[str, Any]) -> str:
    if not report:
        return ""
    summary = report.get("summary") or {}
    coverage = report.get("coverage") or {}
    lines = ["[MATH_REPORT]"]
    lines.append(f"coverage={coverage.get('ok_modules', 0)}/{coverage.get('total_modules', 0)}")
    for key in (
        "latest_price",
        "return_annualized",
        "volatility_annualized",
        "sharpe",
        "max_drawdown",
        "var_95",
        "kelly_fraction",
        "crisis_score",
        "f51_decision_score",
    ):
        value = summary.get(key)
        if value not in (None, "", [], {}):
            lines.append(f"{key}={value}")
    return "\n".join(lines)


def _format_guardrail_hub(guardrail_hub: dict[str, Any]) -> str:
    if not guardrail_hub:
        return ""
    summary = guardrail_hub.get("summary") or {}
    return "\n".join(
        [
            "[GUARDRAIL_HUB]",
            f"total_guardrails={guardrail_hub.get('total_guardrails')}",
            f"decision_counts={summary.get('decision_counts')}",
            f"blocking_guardrails={summary.get('blocking_guardrails')}",
            f"ready={summary.get('ready')}",
        ]
    )


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


def _small_ticket_amount(raw_message: str) -> float | None:
    match = re.search(
        r"(?:cad\s*([\d.,]+)|([\d.,]+)\s*cad|usd\s*([\d.,]+)|\$\s*([\d.,]+))",
        raw_message or "",
        re.IGNORECASE,
    )
    if not match:
        return None
    raw = next((group for group in match.groups() if group), "")
    raw = raw.replace(",", "")
    try:
        return float(raw)
    except ValueError:
        return None


def _build_small_capital_prompt(raw_message: str) -> str:
    """Short mouth prompt for a small cash pile — not the 12-section CFO dump."""
    return "\n\n".join(
        [
            MODEL_PROMPTS["local"]["persona"],
            (
                "SMALL CAPITAL ADVISORY:\n"
                "The user has a small cash pile and asks for an investment "
                "suggestion (amount + risk profile) without naming a ticker and "
                "without requesting a trade, scan, or order.\n"
                "Answer in Portuguese (or the user's language) in at most 12 short lines.\n"
                "Answer structure, in this order:\n"
                "1) short profile read: available capital + declared risk appetite;\n"
                "2) 2 to 4 compatible product/strategy classes under explicit "
                "illustrative premises -- never invent a ticker, never quote "
                "yield, return, or live price;\n"
                "3) explicit honesty: no live market data was collected in this run;\n"
                "4) next step offering exactly two options: the user names a "
                "candidate ticker and you run the verification gates ticker by "
                'ticker, OR the user authorizes a scan (e.g. "pode escanear").\n'
                "Do NOT describe a market scan. Do NOT invent a ticker.\n"
                "Do NOT use the 12-section complex finance contract.\n"
                "Do NOT mention REJECT_ALL, US_CANADA_LIQUID, price_routes_active, "
                "or data-limit telemetry.\n"
                "Do NOT default to 'stay in cash': that verdict belongs only to a "
                "later step, when no verifiable candidate survives the ticker/scan "
                "check. Do NOT make asking for a ticker the whole answer.\n"
                "Tone: educational decision support, never regulated personalized "
                "financial advice."
            ),
            f"USER: {raw_message}",
        ]
    )


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
                '1. **Scope disclaimer** -- one short sentence: "This is an educational framework, not personalized financial advice."\n'
                "2. **Question Classification** -- identify the type: CAPITAL_ALLOCATION, MACRO_THESIS, REAL_ESTATE_VS_MARKETS, PERSONAL_FINANCE, ASSET_ALLOCATION, BUSINESS_CAPITAL, FRAUD_RISK, EDUCATION_INVESTMENT, or UNKNOWN\n"
                "3. **Assumptions** -- state all assumptions being made (Key Assumptions). Always label scenario numbers, returns, and probabilities as illustrative assumptions.\n"
                "4. **Missing Data** -- what data would be needed for a definitive answer\n"
                "5. **Decision Variables** -- the factors that drive the decision\n"
                '6. **Quantitative Thresholds** -- specific numbers, ranges, formulas, or decision gates. Avoid vague thresholds like "risk capacity > $50K". Instead, you MUST use actionable gates:\n'
                "   - emergency fund months (e.g., 3-6 months based on income stability)\n"
                "   - debt interest rate (e.g., pay off debt with interest > 6-8% first)\n"
                "   - income stability (e.g., stable salary vs unstable freelance)\n"
                "   - liquidity need\n"
                "   - time-to-cashflow for business equipment\n"
                "   - tax-advantaged account availability\n"
                '7. **Scenario Analysis** -- base case, downside case, upside case with numbers. You must explicitly label all scenario numbers, returns, and probabilities as illustrative assumptions (e.g., "illustrative scenario assumptions"). Do NOT invent exact expected returns or probabilities unless they are explicitly sourced.\n'
                "8. **Ranked Allocation / Framework** -- ordered ranking of options with rationale (Ranked Decision). Every allocation must include the exact percentage, and you must explain why each bucket gets that percentage. Allocations must sum to exactly 100%.\n"
                '9. **Decision Gates** -- triggers that would flip the recommendation (What Would Change the Decision), main risks (Main Risks), and conditional logic. State clearly "what changes the allocation" in this section.\n'
                "10. **Final Recommendation Under Assumptions** -- clear, actionable next step (Final Recommendation)\n"
                "11. **Confidence Level** -- honest assessment with stated uncertainty\n"
                "12. **Professional Caveat** -- suggestion to consult a CFP as a final caveat, not as the whole answer\n\n"
                "Mandatory Disclaimer Style:\n"
                "Allowed:\n"
                '"This is an educational framework, not personalized financial advice."\n'
                "Forbidden:\n"
                '"I cannot provide a capital allocation plan."\n'
                '"Please consult a CFP" as the full response.\n'
                '"I cannot help with this."\n\n'
                "TOPIC-SPECIFIC RULES:\n"
                "- Avoid fake precision: do not present annualized return ranges as forecasts unless backed by an explicit data/source. Do NOT invent exact expected returns or probabilities unless they are explicitly sourced.\n"
                '- NEVER output exact probability values like "50% chance", "70% probability", "30% likelihood", or similar precise percentages. Instead, use qualitative ranges: "roughly even odds", "more likely than not", "illustrative risk range, not forecast".\n'
                "- Label all scenario numbers, returns, and probabilities as illustrative assumptions.\n"
                "- Ensure proposed portfolio allocations sum to exactly 100%. Every allocation must include why each bucket gets that percentage.\n"
                '- For Canadian personal finance: include CAD, liquidity, emergency reserve. When mentioning Canadian registered accounts, spell them out individually with proper separators: write "TFSA, RRSP, RESP, or FHSA" -- NEVER concatenate them into malformed strings like "TFSABRRSP" or "TFSARRSP". State that tax rules depend on the individual\'s situation.\n'
                '- NEVER recommend specific ETF tickers (e.g., VGRO, XEQT, VFV, ZAG) unless the user provided verified price/fundamental data for that ticker. Instead, describe the asset class: "broad diversified Canadian-listed ETF", "low-cost S&P 500 index ETF", "aggregate bond ETF".\n'
                "  * TICKER DENYLIST: The following are NOT real tickers and must NEVER appear: VOOE, SPYY, VTII, VXUSS, BNDD, SLVV, QQQE, SPYD. If you are unsure a ticker exists, describe the asset class instead.\n"
                "- ETF OVERLAP RULE: Do NOT recommend two or more ETFs that track the same or highly correlated index in the same allocation. Known overlapping pairs to avoid together: SPY/VTI/VOO/IVV (all track US total/large-cap market, correlation >0.95), QQQ/QQQM (identical index), VXUS/VEU (both total international). If SPY is already in the allocation, do NOT add VTI or VOO -- pick ONE US equity ETF and justify it. Same rule applies for any ETF pairs where the underlying index overlap exceeds 80%.\n"
                "- ETF CATEGORY SANITY: VOO/SPY/IVV are S&P 500/US large-cap examples; VTI is total US market; VXUS/VEU are international ex-US; BND is bonds/fixed income; VNQ is REITs; SCHD is dividend quality; VTV is large-cap value and must NEVER be called small-cap; VBR/VB are the small-cap/small-cap-value examples; VWENX is not an ETF and must NEVER be called a bond ETF. If category certainty is low, use the asset-class label instead of a ticker.\n"
                "- For real estate vs markets: include cap rate, cash-on-cash return, mortgage rate sensitivity, vacancy stress, maintenance reserve, insurance, taxes, liquidity, concentration risk, and opportunity cost vs diversified equity.\n"
                "- For macro thesis: first build the thematic exposure logic before giving stock-screening criteria. Separate secular trend, valuation risk, concentration risk, picks-and-shovels infrastructure, hype zones, position sizing logic, and rebalancing discipline.\n"
                "- For AI investment thesis, explicitly separate: 1. infrastructure winners, 2. monetization-risk companies, 3. hype/pivot companies, 4. valuation traps, 5. portfolio sizing, 6. rebalancing rules, and 7. maximum total AI-theme exposure inside the full portfolio.\n"
                "- For capital allocation: include high-interest debt threshold, emergency reserve, reversibility, time-to-cashflow, and family stability.\n\n"
                "FINAL OUTPUT FORMAT -- MANDATORY:\n"
                "Your answer MUST end with exactly these two lines, on their own, after the Professional Caveat section:\n"
                "Final verdict: <PAY_DEBT / CASH / ETF / STOCK_TRADE / WAIT>\n"
                "Confidence: <0-100>\n\n"
                "Pick exactly ONE verdict from the list. Do not combine them.\n"
                "- PAY_DEBT: use when high-interest debt (>6-8%) dominates expected returns\n"
                "- CASH: use when emergency fund is insufficient or liquidity need is urgent\n"
                "- ETF: use when diversified passive investment fits the horizon and risk tolerance\n"
                "- STOCK_TRADE: use only when the user explicitly asks for individual stock trades as the primary option (not as one option among cash/ETF/debt)\n"
                "- WAIT: use when missing data or uncertainty is too high to commit capital\n\n"
                "Confidence must be a single integer from 0 to 100 reflecting how confident you are in the verdict given the available information and stated assumptions.\n\n"
                "Answer in the user's language. Use numbers, not generalities."
            ),
            f"USER: {raw_message}",
        ]
    )


# ---------------------------------------------------------------------------
# Main prompt builder
# ---------------------------------------------------------------------------


def build_agent_prompt(
    state: PipelineState,
    mandamentos: list[Any] | None = None,
) -> str:
    """Build the full CEO prompt from pipeline state for Bob Core."""
    mandamentos = mandamentos or []
    raw_message = state.get("message", "")
    intent = state.get("intent", "general_question")
    route = state.get("route", "general")
    ticker = state.get("ticker", "")

    # â"€â"€ Casual / greeting â"€â"€
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
    # Also route explicit capital_allocation / personal_finance intents
    # (deterministic parser) to the structured complex finance prompt.
    _advisory_intents = {"general_question", "capital_allocation", "personal_finance"}
    if (
        intent in _advisory_intents
        and not has_financial
        and (
            detect_complex_finance_intent(raw_message)
            or intent in ("capital_allocation", "personal_finance")
        )
    ):
        amount = _small_ticket_amount(raw_message)
        if intent == "capital_allocation" and amount is not None and amount <= 500:
            return _build_small_capital_prompt(raw_message)
        return _build_complex_finance_prompt(raw_message)

    msg_has_ticker = bool(re.search(r"\b[A-Z]{1,5}(?:\.[A-Z]{1,2})?\b", raw_message))
    if intent == "general_question" and not has_financial and not msg_has_ticker:
        return "\n\n".join(
            [
                MODEL_PROMPTS["local"]["persona"],
                (
                    "Answer the user's question directly in natural language. "
                    "If the user asks for financial education or general risk advice, "
                    "give practical guidance without pretending market data was collected."
                ),
                f"USER: {raw_message}",
            ]
        )

    # â"€â"€ Structured analysis â"€â"€
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
        (
            "PIPELINE_OBLIGATION: "
            "You are NOT a standalone LLM. A 10-node deterministic pipeline ran "
            "BEFORE this prompt. Its output is below. EVERY module with data "
            "MUST appear in your answer. The RL RewardFunction and SDCA-Lite Cognitive "
            "Risk Firewall score every answer. Skipping a module with data is invalid.\n\n"
            "LANGUAGE: answer in the user's language when it is clear. If the user wrote "
            "in Portuguese, answer in Portuguese. If the user wrote in English, answer in English.\n\n"
            "MARKET CONTEXT: You are a Canada+USA financial expert. "
            "Primary exchanges: TSX/TSX-V/CSE (Canada, CAD), NYSE/NASDAQ (USA, USD). "
            "Canadian accounts: TFSA, RRSP, RESP, FHSA; verify current limits before "
            "quoting exact numbers. "
            "Canada-listed US ETFs include unhedged VFV/XUU and hedged VSP/XUH. "
            "You operate in North American markets (Canada + USA) ONLY. "
            "Never mention B3, BDRs, FIIs, or Brazilian assets.\n\n"
            "You are Bob, SuperEzio's autonomous financial agent. You provide financial decision support "
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
            "Entao explique o PORQUE em portugues. Cite TODO modulo disponivel abaixo pelo nome:\n"
            "- DATA: o que o DataCollector mostra\n"
            "- PENNYLAB: o que os especialistas forenses detectaram\n"
            "- EXPERTS: o que o comite de especialistas concluiu\n"
            "- NEURAL_DECISION: probabilidade direcional, sinal de retorno esperado, regime, risco de drawdown\n"
            "- SDCA_FIREWALL: portao defensivo ALLOW, BLOCK ou REVIEW antes de qualquer acao final\n"
            "- RAG_FORENSICS: quais padroes historicos casam\n"
            "- F51_VERDICT: o que o scoring unificado diz\n"
            "- MATH_REPORT: relatorio numerico consolidado (risco, Sharpe, VaR, Kelly, crise)\n"
            "- GUARDRAIL_HUB: status da auditoria de 30 camadas e bloqueios\n"
            "- DECISION_TRACE: relatorio de responsabilidade e origem de latencia/skip/erro\n\n"
            "Se um modulo nao tiver dados, escreva '[MODULO] MISSING - confidence reduced'.\n"
            "Se um modulo tiver dados, interprete em risco e evidencia, nao em instrucao de corretagem.\n\n"
            "RULES:\n"
            "- Responda primeiro a pergunta real do usuario.\n"
            "- Nunca emita diretiva nua como 'VERDICT: ... -> SHORT'.\n"
            "- Nunca emita ordem direta de compra/venda/short.\n"
            "- Cite evidence_ids para toda afirmacao.\n"
            "- Seja direto, mas mantenha as afirmacoes proporcionais a incerteza e a qualidade dos dados.\n"
            "- Se o usuario pediu tese/dica/direcao/invalidacao/alvo/stop e o pipeline rodou, "
            "entregue esses campos com numeros. Nao substitua a tese por WAIT/paper only. "
            "Live congelado e nota de execucao (uma linha), nao o veredito da analise."
            ""
        ),
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

    math_block = _format_math_report(state.get("math_report") or {})
    if math_block:
        parts.append(f"MATH_REPORT:\n{math_block[:1600]}")

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

    trinity_report = state.get("trinity_report", "")
    if trinity_report:
        parts.append(f"TRINITY:\n{trinity_report[:3000]}")

    neural = state.get("neural_decision") or {}
    if neural and "error" not in neural:
        neural_block = _format_neural_decision(neural)
        if neural_block:
            parts.append(f"NEURAL_DECISION:\n{neural_block[:1200]}")
    else:
        parts.append("NEURAL_DECISION:\nNeuralDecisionExpert not available for this ticker.")

    _sdca_raw = state.get("sdca_firewall")
    sdca = _sdca_raw if isinstance(_sdca_raw, dict) else {}
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
            f"decision_score={f51.get('decision_score', f51.get('confidence'))}, "
            f"score_type={f51.get('score_type', 'legacy_unknown')}, "
            f"calibration={f51.get('calibration_status', 'unknown')}, "
            f"evidence_status={f51.get('evidence_status', 'unknown')}, "
            f"reason_codes={f51.get('reason_codes', [])}, "
            f"factors={f51.get('factors', {})}"
        )
        parts.append(f51_block)

    guardrail_block = _format_guardrail_hub(state.get("guardrail_hub") or {})
    if guardrail_block:
        parts.append(f"GUARDRAIL_HUB:\n{guardrail_block[:1600]}")

    trace = state.get("decision_trace") or {}
    if trace:
        trace_summary = trace.get("summary") or {}
        parts.append(f"DECISION_TRACE:\n{trace_summary}")

    contract = _render_module_contract(state)
    if contract:
        parts.append(contract)

    # ── Output enforcement for quantized models ──
    # Q4_K_M models tend to truncate. This block is placed LAST so it's
    # fresh in the model's attention window.
    parts.append(
        "CRITICAL_OUTPUT_REQUIREMENT:\n"
        "Sua resposta DEVE conter exatamente estes cabecalhos de secao, um por linha, "
        "mesmo se a secao estiver MISSING:\n"
        "## DATA\n"
        "## F51_VERDICT\n"
        "## EXPERTS\n"
        "## NEURAL_DECISION\n"
        "## SDCA_FIREWALL\n"
        "## RAG_FORENSICS\n"
        "## PENNYLAB\n"
        "## MATH_REPORT\n"
        "## GUARDRAIL_HUB\n"
        "## DECISION_TRACE\n"
        "## TRINITY\n\n"
        "Para cada secao escreva 1-3 frases em portugues, linguagem simples. "
        "Se um modulo nao tiver dados, escreva 'MISSING -- confidence reduced'.\n"
        "Depois escreva '## BOB_VERDICT' com seu veredito final em portugues.\n"
        "Nao pule nenhum cabecalho de secao. Obrigatorio."
    )

    return "\n\n".join(parts)


def missing_agent_text(
    ticker: str = "",
    route: str = "general",
    local_ready: bool = False,
) -> str:
    """Error text when local CEO is unavailable."""
    if not local_ready:
        return (
            "MODEL_MISSING: local Bob Core CEO is offline.\n\n"
            f"Prepared route: {route} | ticker: {ticker or 'no ticker'}.\n"
            "Action: verify CEO model server is running on port 8080"
        )
    return (
        "MODEL_MISSING: local Bob Core CEO did not respond.\n\n"
        f"Prepared route: {route} | ticker: {ticker or 'no ticker'}.\n"
        "Action: verify http://127.0.0.1:8080/health and http://127.0.0.1:8080/v1/models."
    )
