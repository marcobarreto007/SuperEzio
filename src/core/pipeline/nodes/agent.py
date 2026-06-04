"""Agent node — the core LLM orchestrator using ReAct / Tool Calling."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from langgraph.config import get_stream_writer

from ..contracts import AgentToolCall
from ..intents import (
    detect_another_trade_recommendation_intent,
    detect_complex_finance_intent,
    detect_decisive_trade_intent,
)
from ..trade_order import (
    BUY_CONFIDENCE_THRESHOLD,
    compute_model_confidence,
    decide_final_action,
    evaluate_quality_gates,
    format_liquidity_display,
    normalize_liquidity_fields,
    pick_candidate,
    rank_candidates,
)

logger = logging.getLogger(__name__)

# ── Bob Sovereign System Prompt (SUPEREZIO_BOB_SOVEREIGN=1) ──

BOB_SOVEREIGN_PROMPT = """
You are Bob, a trusted financial consultant and friend. You have an 80-billion-parameter
brain with deep knowledge of markets, economics, business strategy, and human behavior.

Your CORE IDENTITY:
- You are NOT a Bloomberg terminal. You are a THINKING consultant.
- The user comes to you with natural language. They don't know tickers — they know desires.
- Your job: UNDERSTAND what they really want → FORM A THESIS → CONSULT TOOLS → CONCLUDE.
- You NEVER invent live data. When you need current facts, you CALL a tool.
- You know your own knowledge has a cutoff date. For anything recent, you ASK.

YOUR MARKET EXPERTISE (Canada + USA):
- You are a North American financial expert. Primary markets:
  CANADA: TSX (Toronto), TSX-V (venture), CSE. Currency: CAD.
  USA: NYSE, NASDAQ, OTC. Currency: USD.
- Canadian registered accounts: TFSA (tax-free), RRSP (retirement),
  RESP (education), FHSA (first home). You know the account purpose and
  tax wrapper logic, but verify current contribution limits before quoting
  exact numbers. NEVER concatenate names into garbage.
- Key ETFs you know deeply: SPY/VOO/QQQ/IWM (US), XIU/XIC/VCN (CA equity),
  VFV/XUU (CAD-listed unhedged US exposure), VSP/XUH (CAD-hedged US exposure),
  ZAG/XBB (CA bonds).
- When users mention "reais" (R$) or Brazilian context, you adapt between
  North American and Brazilian markets. You know B3, BDRs, FIIs.
- LANGUAGE: answer in the USER's language. If they write in Portuguese,
  answer in Portuguese — but keep Canada/US market context (CAD, TSX, TFSA).

CRITICAL: CURRENT DATETIME
The current date and time is injected at the top of each conversation.
READ IT. It tells you what "now" means. If a user asks about "recent" events,
compare against this date. If your knowledge predates the user's question,
call search/rag tools to fill the gap.

YOUR WORKFLOW (follow this order):

STEP 0 — DECISION HIERARCHY (MEMORIZE THIS)
You are the CEO. The tools are your ANALYSTS, not your boss.
The decision chain is ALWAYS: SAFETY -> EVIDENCE -> ANALYSIS -> VERDICT.

  0.1 SAFETY FIRST — Before ANY analysis, run firewalls.
      If f51_firewall, sdca_firewall, or social_forensics flag
      manipulation, fraud, or extreme risk -> ALERT immediately.
      You can still analyze, but the alert MUST be in your answer.

  0.2 EVIDENCE SECOND — Never call experts without data.
      collect_data or market_scan MUST complete before experts.
      If data collection fails -> say what is missing, classify STUDY_MORE.

  0.3 ANALYSIS THIRD — Experts are ADVISORS, not judges.
      Each expert gives: verdict (BULLISH/BEARISH/NEUTRAL) + confidence (0-100).
      Your job: WEIGH their votes. Macro weighs more in crises.
      Technical weighs more in trends. Contrarian weighs more at extremes.
      If experts CONTRADICT each other -> investigate the divergence.
      Do NOT blindly average. Explain the tension.

  0.4 VERDICT LAST — You, Bob, make the final call.
      State: (a) what each expert said, (b) how you weighed them,
      (c) your decision with confidence. Never delegate the verdict.

  0.5 NO DATA = STUDY_MORE — If critical evidence is missing,
      list exactly what is missing. Do not invent. Do not guess.

STEP 1 — UNDERSTAND
Read the user's message. What do they REALLY want?
- Are they scared? Excited? Desperate? Curious?
- What's the actual need behind the words?
- Classify: capital allocation? opportunity hunting? education? prediction? analysis?

STEP 2 — FORM A THESIS
Before calling ANY tool, think. What do YOU know?
- What sectors, dynamics, or principles apply here?
- What would a smart, experienced friend say?
- Form a DIRECTION. "I think X because Y. To confirm, I need to check Z."

STEP 3 — CONSULT TOOLS (only if needed)
You have tools available. Use them to CONFIRM or CHALLENGE your thesis:
- collect_data: fetch price, fundamentals, technicals for a ticker
- market_scan: scan for tickers matching a thesis description
- run_experts: invoke the expert committee for multi-angle analysis
- social_forensics: check Reddit/social media for manipulation signals
- rag_forensics: search archived financial documents
- f51_firewall: run the F51 risk veracity engine
- sdca_firewall: cognitive risk firewall check
- neural_decision: get regime and expected return prediction
- pennylab: forensic penny stock manipulation check
- penny_momentum_backtest: run the math-core penny momentum breakout backtest from OHLCV data or scan tickers
- bob_search: search the web and archived documents for current information
- social_forensics: analyze Reddit/social media for pump & dump detection

Call tools ONLY when your thesis needs grounding. Don't call tools blindly.
Every tool call must have a PURPOSE tied to your thesis.

STEP 4 — CONCLUDE
Synthesize your reasoning + tool results into a clear, honest conclusion.
- If tools confirmed your thesis: explain why, with evidence.
- If tools challenged your thesis: explain the tension. You're allowed to disagree.
- If a tool FAILED (missing data, API error): state it. Don't hide failures.
  "The scanner couldn't confirm pricing for X, but my thesis remains Y because..."
- The final ticker (if any) is the CONCLUSION of your reasoning, never the start.
- Always include: what you're confident about, what you're uncertain about, what
  would change your mind.

YOUR VOICE:
- Speak like a smart friend, not a robot. Use the user's language.
- Be honest about uncertainty. "I think" not "I guarantee."
- No hype. No FOMO. No rocket emojis. No promises of returns.
- If something looks like a pump & dump, SAY SO.
- If the user is about to do something reckless, WARN THEM like a friend would.
- For capital allocation, personal finance, or portfolio decisions: include ONE short
  scope line (natural language is fine), e.g. "This is an educational framework, not
  personalized financial advice." Do NOT use the numbered 12-section template.

TOOL CALL FORMAT:
{"tool": "tool_name", "args": {"arg1": "val1"}}

FINAL ANSWER FORMAT:
{"tool": "final_answer", "args": {"content": "your complete analysis here"}}

Remember: You are the BRAIN. The tools are your SENSES.
THINK first. Then look. Then conclude.
"""

# ── Legacy System Prompt (kept for backward compat) ──

SYSTEM_PROMPT = """
You are Bob, SuperEzio's autonomous financial agent.
You must fulfill the user's request by deciding which tools to call.
You have access to the following tools:

1. collect_data
   Description: Fetches market prices, fundamentals, news, and technicals for a ticker.
   Input schema: {"ticker": "AAPL"}
   
2. f51_firewall
   Description: Runs the F51 risk and data veracity engine on collected data.
   Input schema: {}
   
3. pennylab
   Description: Runs forensic manipulation checks on penny stocks.
   Input schema: {}
   
4. run_experts
   Description: Invokes the expert committee (fundamental, technical, risk, macro, quant, sentiment).
   Input schema: {}
   
5. neural_decision
   Description: Runs the Neural Decision Expert to get regime and expected return.
   Input schema: {}
   
6. sdca_firewall
   Description: Runs the final SDCA Cognitive Risk Firewall before taking action.
   Input schema: {}
   
7. rag_forensics
   Description: Searches for historical fraud or manipulation patterns.
   Input schema: {}
   
8. market_scan
   Description: Scans the market for opportunities based on criteria.
   Input schema: {"query": "natural language query describing scan"}

9. penny_momentum_backtest
   Description: Runs the math-core penny-stock momentum breakout backtest.
   Input schema: {"tickers": ["ABCD"], "ohlcv_by_symbol": {"ABCD": [{"date": "YYYY-MM-DD", "close": 1.25, "volume": 1000000}]}}

10. final_answer
   Description: Provides the final natural language answer to the user.
   Input schema: {"content": "Your final verdict and analysis in the user's language."}

**CRITICAL INSTRUCTIONS**:
- You must ONLY output a valid JSON object. No other text.
- Format: {"tool": "tool_name", "args": {"arg1": "val1"}}
- Call one tool at a time.
- If you need market data, call collect_data first.
- If the user asks a general question that doesn't need data, you can just call final_answer directly.
- NEVER invent data.
"""

COMPLEX_FINANCE_SYSTEM_PROMPT = """
You are Bob, SuperEzio's autonomous financial agent.
The user is asking a complex financial advisory/strategy question.
You must provide a SERIOUS, QUANTITATIVE decision framework answer, NOT a market scan.
Your answer should feel like a family CFO framework, not a generic financial blog.

Do NOT call market_scan. Do NOT call collect_data. Do NOT look up tickers.
Call final_answer directly with your comprehensive analysis.

You must NOT provide regulated personalized financial advice as a licensed advisor.
But you MUST provide educational frameworks, hypothetical capital allocations under explicit assumptions, scenario analysis, decision gates, missing data checklists, conditional recommendations, and risk warnings.

BANNED OVERBLOCKING PHRASES — For ordinary educational finance, allocation,
analysis, or thesis questions, do not output any of these as your answer:
- "I cannot provide"
- "I cannot help"
- "I can't provide"
- "I can't help"
- "I am unable"
- "I'm not able"
- "I don't have enough"
- "as an AI"
- "please consult" as your only or main answer
- any sentence that starts with "I cannot" or "I can't"
- refusing to answer

Instead, give a substantive, educational, quantitative answer with assumptions,
decision gates, scenario analysis, and risk warnings.

Safety boundary: do not give guaranteed returns, fraud/deception/evasion help,
legal/tax filing instructions as a substitute for a professional, or exact
personalized trade orders presented as certainty. If the request pushes into
that zone, transform it into an educational framework with conditional logic,
missing data, position-sizing limits, and what would change the decision.

Your answer MUST follow this exact 12-section structure:

1. **Scope disclaimer** — one short sentence: "This is an educational framework, not personalized financial advice."
2. **Question Classification** — identify the type (CAPITAL_ALLOCATION, MACRO_THESIS, REAL_ESTATE_VS_MARKETS, PERSONAL_FINANCE, ASSET_ALLOCATION, BUSINESS_CAPITAL, FRAUD_RISK, EDUCATION_INVESTMENT)
3. **Assumptions** — state all assumptions being made (Key Assumptions). Always label scenario numbers, returns, and probabilities as illustrative assumptions.
4. **Missing Data** — what data would be needed for a definitive answer
5. **Decision Variables** — the factors that drive the decision
6. **Quantitative Thresholds** — specific numbers, ranges, formulas, or decision gates. Avoid vague thresholds like "risk capacity > $50K". Instead, you MUST use actionable gates:
   - emergency fund months (e.g., 3-6 months based on income stability)
   - debt interest rate (e.g., pay off debt with interest > 6-8% first)
   - income stability (e.g., stable salary vs unstable freelance)
   - liquidity need
   - time-to-cashflow for business equipment
   - tax-advantaged account availability
7. **Scenario Analysis** — base case, downside case, upside case with numbers. You must explicitly label all scenario numbers, returns, and probabilities as illustrative assumptions (e.g., "illustrative scenario assumptions"). Do NOT invent exact expected returns or probabilities unless they are explicitly sourced.
8. **Ranked Allocation / Framework** — ordered ranking of options with rationale (Ranked Decision). Every allocation must include the exact percentage, and you must explain why each bucket gets that percentage. Allocations must sum to exactly 100%.
9. **Decision Gates** — triggers that would flip the recommendation (What Would Change the Decision), main risks (Main Risks), and conditional logic. State clearly "what changes the allocation" in this section.
10. **Final Recommendation Under Assumptions** — clear, actionable next step (Final Recommendation)
11. **Confidence Level** — honest assessment with stated uncertainty
12. **Professional Caveat** — suggestion to consult a CFP as a final caveat, not as the whole answer

Mandatory Disclaimer Style:
"This is an educational framework, not personalized financial advice." — Always include this as your scope disclaimer in Section 1.

Rules:
- Use numbers, thresholds, ranges, formulas, or decision gates whenever possible.
- Avoid fake precision: do not present annualized return ranges as forecasts unless backed by an explicit data/source. Do NOT invent exact expected returns or probabilities unless they are explicitly sourced.
- NEVER output exact probability values like "50% chance", "70% probability", "30% likelihood", or similar precise percentages. Instead, use qualitative ranges: "roughly even odds", "more likely than not", "illustrative risk range, not forecast".
- Label all scenario numbers, returns, and probabilities as illustrative assumptions.
- Ensure portfolio allocations sum to exactly 100%. Every allocation must include why each bucket gets that percentage.
- If required data is missing, state assumptions instead of pretending certainty.
- For Canadian personal finance: include CAD, liquidity, emergency reserve. When mentioning Canadian registered accounts, spell them out individually with proper separators: write "TFSA, RRSP, RESP, or FHSA" — NEVER concatenate them into malformed strings like "TFSABRRSP" or "TFSARRSP". State that tax rules depend on the individual's situation.
- NEVER recommend specific ETF tickers (e.g., VGRO, XEQT, VFV, ZAG) unless the user provided verified price/fundamental data for that ticker. Instead, describe the asset class: "broad diversified Canadian-listed ETF", "low-cost S&P 500 index ETF", "aggregate bond ETF".
- For real estate vs markets, include cap rate, cash-on-cash return, mortgage rate sensitivity, vacancy, maintenance, insurance, taxes, liquidity, concentration risk, and opportunity cost.
- For macro thesis questions, first build the thematic exposure logic before giving stock-screening criteria. Separate secular trend, valuation risk, concentration risk, picks-and-shovels infrastructure, hype zones, position sizing logic, and rebalancing discipline.
- For AI investment thesis, explicitly separate:
  1. infrastructure winners
  2. monetization-risk companies
  3. hype/pivot companies
  4. valuation traps
  5. portfolio sizing
  6. rebalancing rules
  7. maximum total AI-theme exposure inside the full portfolio
- Avoid generic advice. Be specific and quantitative.
- Answer in the user's language.

FINAL OUTPUT FORMAT — MANDATORY:
Your answer MUST end with exactly these two lines, on their own, after the Professional Caveat section:
Final verdict: <PAY_DEBT / CASH / ETF / STOCK_TRADE / WAIT>
Confidence: <0-100>

Pick exactly ONE verdict from the list. Do not combine them.
- PAY_DEBT: use when high-interest debt (>6-8%) dominates expected returns
- CASH: use when emergency fund is insufficient or liquidity need is urgent
- ETF: use when diversified passive investment fits the horizon and risk tolerance
- STOCK_TRADE: use only when the user explicitly asks for individual stock trades as the primary option (not as one option among cash/ETF/debt)
- WAIT: use when missing data or uncertainty is too high to commit capital

Confidence must be a single integer from 0 to 100 reflecting how confident you are in the verdict given the available information and stated assumptions.

You must ONLY output a valid JSON object:
{"tool": "final_answer", "args": {"content": "your full analysis here"}}
"""

_REJECTION_LABELS_EN = {
    "missing_ticker": "ticker missing or invalid",
    "missing_exchange": "exchange/market unknown",
    "missing_price": "latest price unavailable from data hub",
    "missing_liquidity": "no recent volume or liquidity proxy",
    "missing_short_term_thesis": "no verifiable 2-week catalyst/thesis",
    "penny_filtered": "sub-$1 price filtered (penny gate)",
    "otc_filtered": "OTC/pink venue filtered",
    "microcap_filtered": "microcap (<$300M) filtered",
}

_REJECTION_LABELS_PT = {
    "missing_ticker": "ticker ausente ou invalido",
    "missing_exchange": "exchange/mercado desconhecido",
    "missing_price": "preco atual indisponivel no data hub",
    "missing_liquidity": "sem volume recente ou proxy de liquidez",
    "missing_short_term_thesis": "sem catalisador/tese verificavel de 2 semanas",
    "penny_filtered": "preco abaixo de US$1 filtrado (gate penny)",
    "otc_filtered": "venue OTC/pink filtrado",
    "microcap_filtered": "microcap (<US$300M) filtrada",
}


def _parse_tool_call(text: str) -> dict[str, Any] | None:
    """Extract the first valid JSON tool-call object from *text*."""
    calls = _parse_tool_calls(text)
    return calls[0] if calls else None


def _parse_tool_calls(text: str) -> list[dict[str, Any]]:
    """Extract every valid JSON tool-call object from *text*.

    The sovereign model sometimes emits multiple tool calls in a single
    response (e.g. f51_firewall + sdca_firewall + collect_data).  This
    function returns them all so the agent can batch-execute them instead
    of silently dropping the second and subsequent calls.
    """
    calls: list[dict[str, Any]] = []
    # First try parsing the whole text as one JSON array
    stripped = text.strip()
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, list):
            for item in parsed:
                if isinstance(item, dict) and "tool" in item:
                    try:
                        calls.append(AgentToolCall.model_validate(item).model_dump())
                    except Exception:
                        pass
            if calls:
                return calls
        elif isinstance(parsed, dict) and "tool" in parsed:
            try:
                return [AgentToolCall.model_validate(parsed).model_dump()]
            except Exception:
                pass
    except (json.JSONDecodeError, TypeError, ValueError):
        pass

    # Try to find every {...} JSON block in the text (greedy, overlapping-safe)
    for match in re.finditer(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", stripped):
        candidate = match.group(0)
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict) and "tool" in obj:
                try:
                    calls.append(AgentToolCall.model_validate(obj).model_dump())
                except Exception:
                    pass
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
    return calls


def _is_portuguese_request(message: str) -> bool:
    raw = (message or "").lower()
    return any(
        token in raw
        for token in (
            "bob",
            "voce",
            "você",
            "tenho",
            "investir",
            "risco",
            "mercado",
            "pesquisa",
            "pequeno",
            "comprar",
        )
    )


def _format_liquidity(volume: Any, candidate: dict[str, Any] | None = None) -> str:
    """Format liquidity with explicit units — never a misleading raw float."""
    if candidate is not None:
        return format_liquidity_display(candidate)
    stub: dict[str, Any] = {"volume": volume}
    normalize_liquidity_fields(stub)
    return format_liquidity_display(stub)


def _top_rejection_reasons(
    summary: dict[str, int], labels: dict[str, str], limit: int = 3
) -> list[str]:
    if not summary:
        return []
    ordered = sorted(summary.items(), key=lambda kv: kv[1], reverse=True)[:limit]
    return [f"{labels.get(reason, reason)} — {count}" for reason, count in ordered]


def _format_candidate_block_en(item: dict[str, Any]) -> list[str]:
    ticker = item.get("ticker") or "?"
    name = item.get("name") or item.get("company") or "—"
    market = item.get("market") or item.get("exchange") or "—"
    price = item.get("price")
    currency = item.get("currency") or "USD"
    volume = item.get("volume") or item.get("avg_volume") or item.get("liquidity")
    catalyst = (
        item.get("catalyst")
        or item.get("thesis")
        or item.get("short_term_thesis")
        or item.get("reason")
        or "—"
    )
    risk = item.get("risk") or item.get("downside_risk") or "see Risk Controls"
    invalid = item.get("invalidation") or item.get("invalidation_condition") or "—"
    confidence = item.get("confidence") or "research-only"
    return [
        f"- {ticker} ({name})",
        f"  Market: {market}",
        f"  Latest price: {price} {currency}",
        f"  Volume/liquidity: {_format_liquidity(volume, item)}",
        f"  Reason/catalyst (2w): {catalyst}",
        f"  Risk: {risk}",
        f"  Invalidation: {invalid}",
        f"  Confidence: {confidence}",
    ]


def _format_candidate_block_pt(item: dict[str, Any]) -> list[str]:
    ticker = item.get("ticker") or "?"
    name = item.get("name") or item.get("company") or "—"
    market = item.get("market") or item.get("exchange") or "—"
    price = item.get("price")
    currency = item.get("currency") or "USD"
    volume = item.get("volume") or item.get("avg_volume") or item.get("liquidity")
    catalyst = (
        item.get("catalyst")
        or item.get("thesis")
        or item.get("short_term_thesis")
        or item.get("reason")
        or "—"
    )
    risk = item.get("risk") or item.get("downside_risk") or "ver Controles de Risco"
    invalid = item.get("invalidation") or item.get("invalidation_condition") or "—"
    confidence = item.get("confidence") or "pesquisa-apenas"
    return [
        f"- {ticker} ({name})",
        f"  Mercado: {market}",
        f"  Preco atual: {price} {currency}",
        f"  Volume/liquidez: {_format_liquidity(volume, item)}",
        f"  Razao/catalisador (2 sem.): {catalyst}",
        f"  Risco: {risk}",
        f"  Invalidacao: {invalid}",
        f"  Confianca: {confidence}",
    ]


def _compute_model_confidence(
    candidate: dict[str, Any],
    *,
    source_errors: list[str] | None = None,
    weak_universe: bool = False,
) -> int:
    """Deterministic 0-100 confidence from data quality (delegates to trade_order)."""
    _, failures = evaluate_quality_gates(candidate)
    return compute_model_confidence(
        candidate,
        gate_failures=failures,
        source_errors=source_errors,
        weak_universe=weak_universe,
    )


def _should_use_decisive_mode(state: dict) -> bool:
    message = state.get("message", "")
    intent = state.get("intent", "")
    trade_ctx = state.get("trade_order_context") or {}
    if intent == "another_trade_recommendation":
        return True
    if trade_ctx.get("mode") in {"DECISIVE_TRADE_ORDER", "DECISIVE_TRADE_ORDER_FOLLOWUP"}:
        if detect_another_trade_recommendation_intent(message):
            return True
    return bool(detect_decisive_trade_intent(message))


def _build_trade_order_context(
    state: dict,
    *,
    mode: str,
    primary_ticker: str,
    ranked: list[dict[str, Any]],
    decision: str,
) -> dict[str, Any]:
    scan = state.get("scan") or {}
    trade_ctx = state.get("trade_order_context") or {}
    prior_excluded = [str(t).upper() for t in trade_ctx.get("excluded_tickers") or [] if t]
    excluded = list(
        dict.fromkeys(prior_excluded + ([primary_ticker.upper()] if primary_ticker else []))
    )
    return {
        "mode": mode,
        "primary_ticker": primary_ticker.upper() if primary_ticker else "",
        "excluded_tickers": excluded,
        "time_horizon": state.get("time_horizon") or trade_ctx.get("time_horizon") or "14 days",
        "universe": scan.get("universe") or trade_ctx.get("universe") or "unspecified",
        "filters": scan.get("filters") or trade_ctx.get("filters") or {},
        "ranked_candidates": ranked,
        "rejected_count": int(scan.get("rejected_count", trade_ctx.get("rejected_count", 0)) or 0),
        "rejection_summary": scan.get("rejection_summary")
        or trade_ctx.get("rejection_summary")
        or {},
        "source_errors": scan.get("source_errors") or trade_ctx.get("source_errors") or [],
        "last_decision": decision,
        "scanned_at": scan.get("collected_at") or trade_ctx.get("scanned_at"),
    }


def _trade_safety_gate_failures(state: dict) -> list[str]:
    failures: list[str] = []
    f51 = state.get("f51_verdict") or {}
    sdca = state.get("sdca_firewall") or {}

    if not isinstance(f51, dict) or not f51:
        failures.append("missing_f51_verdict")
    elif f51.get("error"):
        failures.append("f51_error")
    elif f51.get("passed") is not True:
        failures.append("f51_not_passed")

    if not isinstance(sdca, dict) or not sdca:
        failures.append("missing_sdca_firewall")
    elif sdca.get("error"):
        failures.append("sdca_error")
    elif state.get("sdca_blocked") or sdca.get("decision") == "BLOCK":
        failures.append("sdca_blocked")
    elif sdca.get("decision") != "ALLOW":
        failures.append("sdca_not_allow")

    return failures


def _render_decisive_trade_order(state: dict) -> tuple[str, dict[str, Any] | None]:
    message = state.get("message", "")
    scan = state.get("scan") or {}
    trade_ctx = state.get("trade_order_context") or {}
    intent = state.get("intent", "")
    is_followup = intent == "another_trade_recommendation" or (
        trade_ctx.get("mode") in {"DECISIVE_TRADE_ORDER", "DECISIVE_TRADE_ORDER_FOLLOWUP"}
        and detect_another_trade_recommendation_intent(message)
    )
    mode_label = "DECISIVE_TRADE_ORDER_FOLLOWUP" if is_followup else "DECISIVE_TRADE_ORDER"

    candidates = [c for c in scan.get("candidates", []) if isinstance(c, dict)]
    rejected_count = int(scan.get("rejected_count", 0) or 0)
    rejection_summary = scan.get("rejection_summary") or {}
    universe = scan.get("universe") or trade_ctx.get("universe") or "unspecified"
    errors = scan.get("source_errors") or []
    time_horizon = state.get("time_horizon") or trade_ctx.get("time_horizon") or "14 days"
    excluded = {str(t).upper() for t in trade_ctx.get("excluded_tickers") or [] if t}

    portuguese = _is_portuguese_request(message)
    labels = _REJECTION_LABELS_PT if portuguese else _REJECTION_LABELS_EN
    top_reasons = _top_rejection_reasons(rejection_summary, labels)

    ranked = scan.get("ranked_candidates")
    if not isinstance(ranked, list) or not ranked:
        ranked = rank_candidates(
            candidates,
            source_errors=errors,
            weak_universe=len(candidates) <= 1,
        )

    entry, _ = pick_candidate(ranked, excluded_tickers=excluded)
    sections: list[str] = []

    if is_followup and entry is None:
        prev = trade_ctx.get("primary_ticker") or (list(excluded)[0] if excluded else "?")
        if portuguese:
            sections.extend(
                [
                    "# Bob Model Order",
                    "",
                    f"1. Modo: {mode_label}",
                    "2. Decisao Final: REJECT_ALL",
                    f"3. Candidato Anterior Excluido: {prev}",
                    "",
                    f"Nenhum segundo candidato passou o gate de qualidade apos excluir {prev}.",
                    "",
                    "Resumo de Rejeicoes:",
                    f"   - rejected_count: {rejected_count}",
                ]
            )
            if top_reasons:
                sections.append("   - top_rejection_reasons:")
                for r in top_reasons:
                    sections.append(f"     * {r}")
            sections.extend(
                [
                    "",
                    "Proxima Acao Sugerida:",
                    "   - expandir universo (setor ou pais)",
                    "   - especificar setor ou tema",
                    "   - ajustar tolerancia a risco",
                    "   - pedir analise ticker-por-ticker (ex.: AAPL, MSFT)",
                    "",
                    "Model verdict: REJECT_ALL",
                ]
            )
        else:
            sections.extend(
                [
                    "# Bob Model Order",
                    "",
                    f"1. Mode: {mode_label}",
                    "2. Final Decision: REJECT_ALL",
                    f"3. Previous Candidate Excluded: {prev}",
                    "",
                    f"No second candidate passed the quality gate after excluding {prev}.",
                    "",
                    "Rejected Summary:",
                    f"   - rejected_count: {rejected_count}",
                ]
            )
            if top_reasons:
                sections.append("   - top_rejection_reasons:")
                for r in top_reasons:
                    sections.append(f"     * {r}")
            sections.extend(
                [
                    "",
                    "Next Best Action:",
                    "   - expand universe (sector or country)",
                    "   - specify a sector or theme",
                    "   - lower/raise risk tolerance",
                    "   - run explicit ticker analysis (e.g. AAPL, MSFT)",
                    "",
                    "Model verdict: REJECT_ALL",
                ]
            )
        ctx = _build_trade_order_context(
            state, mode=mode_label, primary_ticker=prev, ranked=ranked, decision="REJECT_ALL"
        )
        return "\n".join(sections), ctx

    if not candidates and entry is None:
        if portuguese:
            sections.extend(
                [
                    "# Bob Model Order",
                    "",
                    f"1. Modo: {mode_label}",
                    "2. Decisao Final: REJECT_ALL",
                    "",
                    f"Nenhuma ordem de modelo gerada. {rejected_count} ticker(s) rejeitado(s) nos gates de qualidade de dados.",
                ]
            )
            if top_reasons:
                sections.append("Principais motivos de rejeicao:")
                for r in top_reasons:
                    sections.append(f"   - {r}")
            sections.extend(
                [
                    f"Universo do scan: {universe}.",
                    "",
                    "Proximo scan sugerido: ampliar universo (setor ou pais), nomear um tema ou apertar filtros de liquidez.",
                    "Proximo prompt sugerido: 'Faca uma checagem ticker-por-ticker de AAPL, MSFT e SPY com preco, volume, ATR de 14 dias e proximo evento conhecido.'",
                    "Model verdict: REJECT_ALL",
                ]
            )
        else:
            sections.extend(
                [
                    "# Bob Model Order",
                    "",
                    f"1. Mode: {mode_label}",
                    "2. Final Decision: REJECT_ALL",
                    "",
                    f"No valid model order generated. {rejected_count} ticker(s) rejected at data-quality gates.",
                ]
            )
            if top_reasons:
                sections.append("Top rejection reasons:")
                for r in top_reasons:
                    sections.append(f"   - {r}")
            sections.extend(
                [
                    f"Scan universe: {universe}.",
                    "",
                    "Suggested next scan: broaden universe (sector or country), name a theme, or tighten liquidity filters.",
                    "Suggested next prompt: 'Run a ticker-by-ticker check on AAPL, MSFT and SPY with price, volume, 14-day ATR and the next known event.'",
                    "Model verdict: REJECT_ALL",
                ]
            )
        if errors:
            sections.append("Data limit: " + "; ".join(str(e) for e in errors[:3]))
        ctx = _build_trade_order_context(
            state, mode=mode_label, primary_ticker="", ranked=ranked, decision="REJECT_ALL"
        )
        return "\n".join(sections), ctx

    if entry is None:
        entry = ranked[0] if ranked else None
    if entry is None:
        ctx = _build_trade_order_context(
            state, mode=mode_label, primary_ticker="", ranked=ranked, decision="REJECT_ALL"
        )
        return "Model verdict: REJECT_ALL", ctx

    primary = entry.get("candidate") or {}
    normalize_liquidity_fields(primary)
    gate_failures = list(entry.get("gate_failures") or [])
    if not gate_failures:
        _, gate_failures = evaluate_quality_gates(primary)
    confidence = int(
        entry.get("confidence")
        or compute_model_confidence(
            primary,
            gate_failures=gate_failures,
            source_errors=errors,
            weak_universe=len(candidates) <= 1,
        )
    )
    decision = entry.get("decision") or decide_final_action(confidence, gate_failures)
    if gate_failures and decision == "BUY_CANDIDATE":
        decision = decide_final_action(confidence, gate_failures)
    safety_gate_failures = _trade_safety_gate_failures(state)
    if safety_gate_failures and decision == "BUY_CANDIDATE":
        gate_failures = list(dict.fromkeys(gate_failures + safety_gate_failures))
        if any(item in safety_gate_failures for item in ("f51_not_passed", "sdca_blocked")):
            decision = "REJECT_ALL"
        else:
            decision = "WAIT"

    ticker = primary.get("ticker") or "?"
    name = primary.get("name") or primary.get("company") or "—"
    market = primary.get("market") or primary.get("exchange") or "—"
    price = primary.get("price")
    currency = primary.get("currency") or "USD"
    catalyst = (
        primary.get("catalyst")
        or primary.get("thesis")
        or primary.get("short_term_thesis")
        or primary.get("reason")
        or "—"
    )
    risk = primary.get("risk") or primary.get("downside_risk") or "—"
    invalidation = primary.get("invalidation") or primary.get("invalidation_condition") or "—"
    provider = primary.get("provider") or primary.get("source") or "data hub"
    collected_at = scan.get("collected_at") or "—"
    liquidity_text = _format_liquidity(None, primary)
    prev_excluded = ""
    if is_followup:
        prev_excluded = trade_ctx.get("primary_ticker") or (list(excluded)[0] if excluded else "—")

    is_buy_candidate = decision == "BUY_CANDIDATE"
    candidate_heading_pt = (
        "Candidato Primario da Ordem:"
        if is_buy_candidate
        else "Candidato de Estudo (Nao e recomendacao):"
    )
    candidate_heading_en = (
        "Primary Order Candidate:"
        if is_buy_candidate
        else "Study Candidate (Not a Recommendation):"
    )
    plan_heading_pt = (
        "Plano de Ordem Sugerido:" if is_buy_candidate else "Plano de Watchlist / Sem Ordem:"
    )
    plan_heading_en = "Suggested Order Plan:" if is_buy_candidate else "Watchlist / No-Trade Plan:"
    entry_line_pt = (
        "ordem limitada proximo ao preco atual"
        if is_buy_candidate
        else "Sem entrada ate risco, invalidacao e confianca passarem nos gates"
    )
    entry_line_en = (
        "limit order near current price"
        if is_buy_candidate
        else "No entry until risk, invalidation, and confidence gates pass"
    )
    max_risk_line_pt = (
        "0.5%-1.0% do capital de trading" if is_buy_candidate else "0 ate virar BUY_CANDIDATE"
    )
    max_risk_line_en = (
        "0.5%-1.0% of trading capital" if is_buy_candidate else "0 until upgraded to BUY_CANDIDATE"
    )

    if portuguese:
        sections.extend(
            [
                "# Bob Model Order",
                "",
                f"1. Modo: {mode_label}",
                f"2. Decisao Final: {decision}",
                "",
            ]
        )
        if is_followup:
            sections.append(f"3. Candidato Anterior Excluido: {prev_excluded}")
            sections.append("")
            sections.append(f"4. {candidate_heading_pt}")
        else:
            sections.append(f"3. {candidate_heading_pt}")
        sections.extend(
            [
                f"   - Ticker: {ticker}",
                f"   - Empresa: {name}",
                f"   - Mercado: {market}",
                f"   - Preco Atual: {price} {currency}",
                f"   - Dados: {collected_at} (fonte: {provider})",
                f"   - Liquidez: {liquidity_text}",
                f"   - Catalisador: {catalyst}",
                f"   - Horizonte: {time_horizon}",
                f"   - Confianca do Modelo: {confidence}/100",
            ]
        )
        if gate_failures:
            sections.append(f"   - Gates falhados: {', '.join(gate_failures)}")
        if safety_gate_failures:
            sections.append(
                "   - Gates obrigatorios de seguranca: F51 + SDCA precisam estar executados e aprovados antes de BUY_CANDIDATE."
            )
        plan_num = "5" if is_followup else "4"
        sections.extend(
            [
                "",
                f"{plan_num}. {plan_heading_pt}",
                f"   - Entrada: {entry_line_pt}",
                f"   - Stop/Invalidacao: {invalidation}",
                f"   - Risco: {risk}",
                f"   - Risco Maximo: {max_risk_line_pt}",
                "",
                "Ordem do modelo, nao e lucro garantido. Confirmacao humana obrigatoria.",
                f"Model verdict: {decision}",
            ]
        )
    else:
        sections.extend(
            [
                "# Bob Model Order",
                "",
                f"1. Mode: {mode_label}",
                f"2. Final Decision: {decision}",
                "",
            ]
        )
        if is_followup:
            sections.append(f"3. Previous Candidate Excluded: {prev_excluded}")
            sections.append("")
            sections.append(f"4. {candidate_heading_en}")
        else:
            sections.append(f"3. {candidate_heading_en}")
        sections.extend(
            [
                f"   - Ticker: {ticker}",
                f"   - Company: {name}",
                f"   - Market: {market}",
                f"   - Latest Price: {price} {currency}",
                f"   - Data Timestamp: {collected_at} (source: {provider})",
                f"   - Liquidity: {liquidity_text}",
                f"   - Catalyst: {catalyst}",
                f"   - Time Horizon: {time_horizon}",
                f"   - Model Confidence: {confidence}/100",
            ]
        )
        if gate_failures:
            sections.append(f"   - Gate failures: {', '.join(gate_failures)}")
        if safety_gate_failures:
            sections.append(
                "   - Required safety gates: F51 + SDCA must run and pass before BUY_CANDIDATE."
            )
        plan_num = "5" if is_followup else "4"
        sections.extend(
            [
                "",
                f"{plan_num}. {plan_heading_en}",
                f"   - Entry: {entry_line_en}",
                f"   - Stop/Invalidation: {invalidation}",
                f"   - Risk: {risk}",
                f"   - Max Risk: {max_risk_line_en}",
                "",
                "Model order, not guaranteed profit. Human confirmation required.",
                f"Model verdict: {decision}",
            ]
        )

    if decision == "WAIT":
        sections.append("")
        if portuguese:
            sections.append(
                f"Nota: confianca abaixo do limiar de compra ({BUY_CONFIDENCE_THRESHOLD}/100) ou gates de liquidez/risco incompletos."
            )
            if gate_failures:
                sections.append(f"Motivos: {', '.join(gate_failures)}")
            sections.append(
                "Permanece na watchlist de estudo ate liquidez, risco e invalidacao elevarem ao limiar de compra do modelo."
            )
        else:
            sections.append(
                f"Note: confidence below buy threshold ({BUY_CONFIDENCE_THRESHOLD}/100) or liquidity/risk gates not satisfied."
            )
            if gate_failures:
                sections.append(f"Reasons: {', '.join(gate_failures)}")
            sections.append(
                "Keep on a study watchlist until liquidity, risk, and invalidation upgrade to model-buy thresholds."
            )

    if errors:
        sections.append("")
        sections.append(
            ("Limite de dados: " if portuguese else "Data limit: ")
            + "; ".join(str(e) for e in errors[:3])
        )

    ctx = _build_trade_order_context(
        state, mode=mode_label, primary_ticker=str(ticker), ranked=ranked, decision=decision
    )
    return "\n".join(sections), ctx


def _decisive_trade_order_answer(state: dict) -> str:
    answer, _ = _render_decisive_trade_order(state)
    return answer


def _market_scan_answer(state: dict) -> str:
    message = state.get("message", "")
    if _should_use_decisive_mode(state) or detect_decisive_trade_intent(message):
        return _decisive_trade_order_answer(state)

    scan = state.get("scan") or {}
    candidates = [c for c in scan.get("candidates", []) if isinstance(c, dict)]
    rejected_count = int(scan.get("rejected_count", 0) or 0)
    rejection_summary = scan.get("rejection_summary") or {}
    universe = scan.get("universe") or "unspecified"
    filters = scan.get("filters") or {}
    errors = scan.get("source_errors") or []

    portuguese = _is_portuguese_request(message)
    labels = _REJECTION_LABELS_PT if portuguese else _REJECTION_LABELS_EN
    top_reasons = _top_rejection_reasons(rejection_summary, labels)

    if portuguese:
        sections: list[str] = []
        sections.append(
            "Bob: este e um relatorio de pesquisa de mercado, nao uma ordem de compra. Lucro nao e garantido."
        )
        sections.append("")
        sections.append("1) Classificacao: pesquisa de oportunidade de curto prazo.")
        sections.append("2) Horizonte: aproximadamente 2 semanas (curto prazo).")
        sections.append(f"3) Universo do scan: {universe}")
        sections.append(
            "4) Gate de qualidade de dados: ticker, exchange, preco atual, volume/liquidez, catalisador de curto prazo, risco e condicao de invalidacao sao obrigatorios. Sem todos esses campos, o candidato e rejeitado."
        )
        sections.append("")
        sections.append("5) Candidatos:")
        if candidates:
            for item in candidates[:6]:
                sections.extend(_format_candidate_block_pt(item))
        else:
            sections.append(
                "Nenhum candidato passou nos gates minimos de qualidade de dados para uma ideia de pesquisa de 2 semanas."
            )
        sections.append("")
        sections.append(f"6) Resumo de rejeicoes: {rejected_count} ticker(s) descartado(s).")
        if top_reasons:
            sections.append("   Principais motivos:")
            for reason in top_reasons:
                sections.append(f"   - {reason}")
        sections.append(
            f"   Filtros usados: paises={filters.get('resolved_countries')}, setor={filters.get('sector')}, permitir_penny_otc={filters.get('allow_penny_otc')}, permitir_microcap={filters.get('allow_microcap')}."
        )
        sections.append("")
        sections.append("7) Controles de risco:")
        sections.append("   - Defina perda maxima por posicao antes de qualquer ordem.")
        sections.append("   - Exija liquidez suficiente para entrar e sair sem spread absurdo.")
        sections.append(
            "   - Confirme catalisador verificavel (filing, earnings, evento) e nao hype social."
        )
        sections.append("   - Estabeleca condicao de invalidacao tecnica/fundamentalista clara.")
        sections.append("")
        sections.append(
            "8) Aviso: apenas pesquisa. Sem garantia de lucro. Decisao de compra/venda e sua responsabilidade."
        )
        if not candidates:
            sections.append("")
            sections.append(
                "Proximo prompt sugerido: 'Faca uma checagem ticker-por-ticker de AAPL, MSFT e SPY com preco, volume, ATR de 14 dias e proximo evento conhecido.'"
            )
        if errors:
            sections.append("")
            sections.append("Limite de dados: " + "; ".join(str(err) for err in errors[:3]))
        return "\n".join(sections)

    sections = []
    sections.append(
        "Bob: this is a market research report, not a buy order. Profit is not guaranteed."
    )
    sections.append("")
    sections.append("1) Classification: short-term opportunity research.")
    sections.append("2) Time horizon: approximately 2 weeks (short term).")
    sections.append(f"3) Scan universe: {universe}")
    sections.append(
        "4) Data quality gate: ticker, exchange, latest price, volume/liquidity, short-term catalyst, downside risk and an invalidation condition are all required. Without every field, a candidate is rejected."
    )
    sections.append("")
    sections.append("5) Candidates:")
    if candidates:
        for item in candidates[:6]:
            sections.extend(_format_candidate_block_en(item))
    else:
        sections.append(
            "No candidate passed the minimum data-quality gates for a 2-week research idea."
        )
    sections.append("")
    sections.append(f"6) Rejected candidates summary: {rejected_count} ticker(s) discarded.")
    if top_reasons:
        sections.append("   Top reasons:")
        for reason in top_reasons:
            sections.append(f"   - {reason}")
    sections.append(
        f"   Filters used: countries={filters.get('resolved_countries')}, setor={filters.get('sector')}, allow_penny_otc={filters.get('allow_penny_otc')}, allow_microcap={filters.get('allow_microcap')}."
    )
    sections.append("")
    sections.append("7) Risk controls:")
    sections.append("   - Define maximum loss per position before placing any order.")
    sections.append("   - Require liquidity sufficient to enter and exit without extreme spreads.")
    sections.append(
        "   - Confirm a verifiable catalyst (filing, earnings, event) rather than social hype."
    )
    sections.append("   - Set a clear technical/fundamental invalidation condition.")
    sections.append("")
    sections.append(
        "8) Caveat: research only. No guaranteed profit. The buy/sell decision is your own responsibility."
    )
    if not candidates:
        sections.append("")
        sections.append(
            "Suggested next prompt: 'Run a ticker-by-ticker check on AAPL, MSFT and SPY with price, volume, 14-day ATR and the next known event.'"
        )
    if errors:
        sections.append("")
        sections.append("Data limit: " + "; ".join(str(err) for err in errors[:3]))
    return "\n".join(sections)


def _loop_failsafe_answer(state: dict) -> str:
    if state.get("scan"):
        return _market_scan_answer(state)
    if state.get("cognitive_mode"):
        return _contract_fallback_answer(state)
    if _is_portuguese_request(state.get("message", "")):
        return (
            "Bob: Encerrei o ciclo de ferramentas após atingir o limite. "
            "Aqui está o que analisei até agora. Mande um ticker ou ajuste a busca para continuar."
        )
    return (
        "Bob: I stopped the tool cycle after reaching the limit. "
        "Narrow down your request or ask a specific question to continue."
    )


def _tool_blocked_answer(state: dict) -> str:
    blocked = state.get("tool_blocked") or {}
    tool = blocked.get("tool", "unknown")
    reason = blocked.get("reason", "already executed")
    if state.get("cognitive_mode") or "cognitive_contract" in str(reason):
        return _contract_fallback_answer(state)
    if _is_portuguese_request(state.get("message", "")):
        return f"Bob: A ferramenta '{tool}' foi bloqueada ({reason}). Produzindo resposta final."
    return f"Bob: Tool '{tool}' was blocked ({reason}). Producing final answer."


def _complex_finance_fallback_answer(message: str) -> str:
    msg = (message or "").lower()
    is_capital = any(
        token in msg
        for token in (
            "allocate",
            "allocation",
            "emergency",
            "debt",
            "equipment",
            "education",
            "cash reserve",
            "cad",
        )
    )
    classification = "CAPITAL_ALLOCATION" if is_capital else "MACRO_THESIS"
    verdict = "CASH" if "unstable" in msg or "emergency" in msg else "ETF"
    confidence = 74 if is_capital else 68
    return (
        "1. **Scope disclaimer** — This is an educational framework, not personalized financial advice.\n"
        f"2. **Question Classification** — {classification}.\n"
        "3. **Assumptions** — CAD capital, Canadian household context, family stability matters, "
        "income may be unstable, and all scenario numbers are illustrative assumptions, not forecasts.\n"
        "4. **Missing Data** — debt balances and interest rates, current emergency reserve, monthly expenses, "
        "TFSA, RRSP, RESP, or FHSA room, tax bracket, business revenue history, and education timeline.\n"
        "5. **Decision Variables** — liquidity need, emergency fund months, debt interest rate, downside risk, "
        "reversibility, time-to-cashflow, health/energy constraints, and family stability.\n"
        "6. **Quantitative Thresholds** — keep 3-6 months of emergency cash reserve first; pay debt above "
        "6-8% interest before market risk; fund business equipment only when expected payback/time-to-cashflow "
        "is clear; keep education spending staged and reversible.\n"
        "7. **Scenario Analysis** — Illustrative downside: unstable income plus no reserve forces asset sales. "
        "Illustrative base case: reserve plus high-interest debt payoff reduces fragility. Illustrative upside: "
        "surplus after safety gates can compound through a broad diversified Canadian-listed ETF or productive "
        "business equipment.\n"
        "8. **Ranked Allocation / Framework** — 40% emergency cash reserve, 30% high-interest debt payoff, "
        "15% broad diversified Canadian-listed ETF, 10% side-business equipment only with payback evidence, "
        "5% education. These illustrative buckets sum to 100% and prioritize survival before upside.\n"
        "9. **Decision Gates** — If emergency reserve is below 3 months, CASH dominates. If debt interest is "
        "above 6-8%, PAY_DEBT dominates. If business equipment has fast payback and low execution burden, shift "
        "some ETF/education budget to equipment. Tax account choices depend on the individual's situation.\n"
        "10. **Final Recommendation Under Assumptions** — Build the emergency reserve first, then pay expensive "
        "debt, then deploy remaining surplus gradually into ETF/business/education only after liquidity is safe.\n"
        f"11. **Confidence Level** — {confidence}/100, limited by missing debt rate, monthly expenses, and tax room.\n"
        "12. **Professional Caveat** — Confirm tax/account details with a CFP or qualified Canadian professional.\n"
        f"Final verdict: {verdict}\n"
        f"Confidence: {confidence}"
    )


def _repair_known_etf_category_errors(text: str) -> str:
    repaired = text or ""
    small_cap_window = re.compile(r"small[- ]cap", re.IGNORECASE)
    bond_etf_window = re.compile(r"(bond|fixed income|investment grade|etf)", re.IGNORECASE)
    for match in reversed(list(re.finditer(r"\bVTV\b", repaired))):
        window_start = max(0, match.start() - 80)
        window_end = min(len(repaired), match.end() + 80)
        if small_cap_window.search(repaired[window_start:window_end]):
            repaired = repaired[: match.start()] + "VBR" + repaired[match.end() :]
    for match in reversed(list(re.finditer(r"\bVWENX\b", repaired))):
        window_start = max(0, match.start() - 80)
        window_end = min(len(repaired), match.end() + 80)
        if bond_etf_window.search(repaired[window_start:window_end]):
            repaired = repaired[: match.start()] + "BND" + repaired[match.end() :]
    return repaired


def _repair_unsourced_etf_tickers(text: str) -> str:
    replacements = {
        "VCN": "a broad Canadian equity index ETF",
        "VCE": "a broad Canadian equity index ETF",
        "XIC": "a broad diversified Canadian-listed ETF",
        "VUN": "a broad US total-market ETF",
        "ZAG": "an aggregate bond ETF",
        "VGRO": "a balanced growth ETF",
        "XEQT": "an all-equity diversified ETF",
        "VFV": "an S&P 500 index ETF",
    }
    repaired = text or ""
    for ticker, asset_class in replacements.items():
        repaired = re.sub(rf"\b{ticker}(?:\.TO)?\b", asset_class, repaired)
    return repaired


def _repair_unsupported_exact_returns(text: str) -> str:
    return re.sub(
        r"guaranteed\s+\d+(?:\s*[–-]\s*\d+)?%\s+return",
        "guaranteed return equal to the avoided interest rate",
        text or "",
        flags=re.IGNORECASE,
    )


def _repair_answer_quality(text: str) -> str:
    return _repair_unsupported_exact_returns(
        _repair_unsourced_etf_tickers(_repair_known_etf_category_errors(text or ""))
    )


def _repair_complex_finance_answer(message: str, content: str) -> str:
    msg = (message or "").lower()
    text = _repair_answer_quality(content or "")
    lower = text.lower()
    additions: list[str] = []

    disclaimer_markers = (
        "not personalized financial advice",
        "not a registered financial advisor",
        "not licensed",
        "not regulated",
        "educational framework",
    )
    if not any(marker in lower for marker in disclaimer_markers):
        additions.append(
            "Scope note: This is an educational framework, not personalized financial advice."
        )

    assumption_markers = (
        "illustrative",
        "assumption",
        "assumptions",
        "assum",
        "ilustrativ",
        "supos",
    )
    if not any(marker in lower for marker in assumption_markers):
        additions.append(
            "Assumptions note: Scenario numbers, allocations, returns, and thresholds above "
            "are illustrative assumptions for decision framing, not forecasts."
        )

    business_prompt = any(token in msg for token in ("business", "equipment", "side-business"))
    has_business_cashflow = any(
        token in lower
        for token in (
            "cashflow",
            "cash flow",
            "time-to-cashflow",
            "time to cashflow",
            "payback",
            "fluxo",
            "caixa",
            "receita",
        )
    )
    if business_prompt and not has_business_cashflow:
        additions.append(
            "Business cashflow gate: fund equipment only with documented demand, "
            "clear payback, and time-to-cashflow evidence; otherwise keep that capital liquid."
        )

    canadian_capital_prompt = any(
        token in msg
        for token in (
            "canada",
            "canadian",
            "cad",
            "family",
            "debt",
            "education",
            "tax",
        )
    )
    has_registered_account = any(term in text for term in ("TFSA", "RRSP", "RESP", "FHSA"))
    if canadian_capital_prompt and not has_registered_account:
        additions.append(
            "Canadian registered-account gate: consider TFSA, RRSP, RESP, or FHSA room only "
            "after liquidity and debt gates; tax/account choices depend on the individual's situation."
        )

    if "Final verdict:" not in text:
        additions.append("Final verdict: WAIT")
    if "Confidence:" not in text:
        additions.append("Confidence: 72")

    if not additions:
        return text
    addition_block = "\n".join(additions)
    footer_idx = text.rfind("\nFinal verdict:")
    if footer_idx == -1:
        return text.rstrip() + "\n" + addition_block
    prefix = text[:footer_idx].rstrip()
    footer = text[footer_idx + 1 :].lstrip()
    return prefix + "\n" + addition_block + "\n" + footer


def _industry_research_fallback_answer(state: dict) -> str:
    message = state.get("message", "")
    is_pt = _is_portuguese_request(message)
    lower = (message or "").lower()
    if "fax" in lower:
        if is_pt:
            return (
                "Bob: minha leitura direta: fax e uma industria legada, em declinio estrutural, "
                "e eu nao comecaria por ticker. A oportunidade real nao e 'empresa de fax'; e o fluxo "
                "adjacente que substitui fax: document workflow seguro, e-signature, healthcare records, "
                "compliance, automacao de back office e cybersecurity para troca de documentos.\n\n"
                "Tese: fax sobrevive onde existe friccao regulatoria e sistemas antigos, mas o crescimento "
                "deve ir para plataformas que removem essa friccao. O risco de comprar uma pure-play de fax "
                "e pegar uma base instalada morrendo, receita em queda e baixo multiple por motivo justo.\n\n"
                "Como usar isso: 1) mapear setores ainda presos in fax, 2) procurar fornecedores que digitalizam "
                "esse fluxo, 3) exigir crescimento verificavel, margem, retencao e baixa dependencia de hype. "
                "Ticker vem depois, se voce pedir uma varredura de ativos.\n\n"
                "Final verdict: pesquisar adjacencias digitais, nao fax puro.\n"
                "Confidence: 84/100"
            )
        return (
            "Bob: direct read: fax is a legacy industry in structural decline, so I would not start with a ticker. "
            "The real opportunity is the workflow replacing fax: secure document workflow, e-signature, healthcare records, "
            "compliance automation, back-office automation, and cybersecurity around document exchange.\n\n"
            "Thesis: fax survives where regulation and old systems create friction, but growth should accrue to platforms "
            "that remove that friction. The risk in a pure fax business is buying a shrinking installed base at a cheap multiple for a good reason.\n\n"
            "Use it this way: map sectors still trapped in fax, find vendors digitizing that flow, then require verified growth, margins, retention, and low hype dependence. "
            "Tickers come later if you ask for an asset scan.\n\n"
            "Final verdict: research digital adjacencies, not pure fax.\n"
            "Confidence: 84/100"
        )
    return (
        "Bob: this is industry research, not a ticker-first request. I would first build the thesis, identify whether the industry is expanding or decaying, "
        "then look for adjacent markets where the economics are improving. Only after that should we screen tickers.\n\n"
        "Final verdict: thesis first, ticker scan second.\n"
        "Confidence: 78/100"
    )


def _risk_lab_fallback_answer(state: dict) -> str:
    is_pt = _is_portuguese_request(state.get("message", ""))
    if is_pt:
        return (
            "Bob: para CAD 50 por semana, eu trataria isso como laboratorio de risco, nao como investimento principal. "
            "A regra e simples: o prejuizo maximo da semana e CAD 50, sem dobrar aposta, sem alavancagem, sem recuperar perda.\n\n"
            "Contrato do laboratorio:\n"
            "- Capital semanal: CAD 50.\n"
            "- Max loss: CAD 50, acabou a semana.\n"
            "- Entrada so com tese, catalisador, liquidez, invalidacao e tamanho da posicao definidos antes.\n"
            "- Se nao houver edge verificavel, a decisao correta e NO_BET_THIS_WEEK.\n"
            "- Depois de cada tentativa: registrar tese, entrada, saida, erro e aprendizado.\n\n"
            "Final verdict: NO_BET_THIS_WEEK ate aparecer uma oportunidade verificavel.\n"
            "Confidence: 86/100"
        )
    return (
        "Bob: for CAD 50 per week, treat this as a risk lab, not core investing. "
        "The weekly max loss is CAD 50. No doubling down, no leverage, no revenge trade.\n\n"
        "Risk lab contract:\n"
        "- Weekly capital: CAD 50.\n"
        "- Max loss: CAD 50, then the week is over.\n"
        "- Enter only with thesis, catalyst, liquidity, invalidation, and position size set before entry.\n"
        "- If no verifiable edge exists, the correct decision is NO_BET_THIS_WEEK.\n"
        "- After every attempt: log thesis, entry, exit, mistake, and lesson.\n\n"
        "Final verdict: NO_BET_THIS_WEEK until a verifiable opportunity appears.\n"
        "Confidence: 86/100"
    )


def _advisory_knowledge_fallback_answer(state: dict) -> str:
    message = state.get("message", "")
    lower = (message or "").lower()
    if "dividend" in lower or "passive income" in lower:
        return (
            "Bob: for a Canadian passive-income portfolio, I would not chase yield first. "
            "Start with dividend durability, tax placement, and concentration limits.\n\n"
            "Framework: use Canadian-listed broad dividend ETFs or high-quality Canadian dividend names as the core, keep any single stock small, "
            "and use RRSP/TFSA rules deliberately. US dividend ETFs can be useful, but withholding tax and account type matter.\n\n"
            "Examples to research, not blind buys: Canadian dividend ETF exposure, Canadian banks, regulated utilities, pipelines/midstream, and one broad-market ETF for diversification. "
            "Verify current yield, payout ratio, debt, dividend growth, and valuation before choosing tickers.\n\n"
            "Final verdict: build a diversified dividend core; do not chase the highest yield.\n"
            "Confidence: 80/100"
        )
    if "dollar-cost" in lower or "dca" in lower or "wait for a correction" in lower:
        return (
            "Bob: default recommendation is DCA, not waiting for the perfect correction. "
            "Without verified live macro data in this run, I would not pretend to time rates or volatility precisely.\n\n"
            "Practical plan: split the capital into 4-8 scheduled tranches, keep emergency cash separate, and accelerate only if valuation and personal cash stability both improve. "
            "Waiting only wins if you have a specific trigger and the discipline to buy when the market is ugly.\n\n"
            "Final verdict: DCA.\n"
            "Confidence: 78/100"
        )
    return (
        "Bob: this is a natural-language financial question, not a ticker-first request. "
        "I can answer from framework knowledge, then use data tools only when current market evidence or a named ticker is required.\n\n"
        "Final verdict: answer the thesis first; use tools only when the question needs verified market data.\n"
        "Confidence: 76/100"
    )


def _contract_fallback_answer(state: dict) -> str:
    mode = state.get("cognitive_mode", "ADVISORY_KNOWLEDGE")
    if state.get("scan"):
        return _market_scan_answer(state)
    if mode == "CAPITAL_ALLOCATION" or state.get("intent") in (
        "capital_allocation",
        "personal_finance",
    ):
        return _complex_finance_fallback_answer(state.get("message", ""))
    if mode == "INDUSTRY_RESEARCH":
        return _industry_research_fallback_answer(state)
    if mode == "RISK_LAB":
        return _risk_lab_fallback_answer(state)
    if mode == "TICKER_ANALYSIS":
        ticker = state.get("ticker", "the ticker")
        return (
            f"Bob: I have a ticker-specific request for {ticker}. "
            "If fresh DataCollector evidence is unavailable, I will not invent prices or fundamentals. "
            "Use the collected evidence when present, then judge thesis, risk, invalidation, and position discipline.\n\n"
            "Final verdict: WAIT until the ticker data path returns verified evidence.\n"
            "Confidence: 62/100"
        )
    if mode == "DISCOVERY_SCAN":
        return (
            "Bob: this is a discovery request, so the scanner is the right tool. "
            "If scanner evidence is unavailable or incomplete, the correct answer is not to invent a candidate.\n\n"
            "Final verdict: REJECT_ALL\n"
            "Confidence: 70/100"
        )
    return _advisory_knowledge_fallback_answer(state)


def _final_payload(content: str, iterations: int) -> dict[str, Any]:
    return {
        "final": content,
        "agent_tool_call": {"tool": "final_answer", "args": {"content": content}},
        "agent_iterations": iterations + 1,
        "_pending_tool_calls": [],
    }


async def node_agent(state: dict, *, gateway=None, config=None, mandamentos=None) -> dict:
    writer = get_stream_writer()
    run_id = state.get("run_id", "")
    iterations = state.get("agent_iterations", 0)

    if iterations > 7:
        content = _loop_failsafe_answer(state)
        writer({"type": "CHUNK", "content": content})
        return {
            **_final_payload(content, iterations),
            "bob_thesis": state.get("bob_thesis", ""),
            "bob_reasoning_trace": state.get("bob_reasoning_trace", []),
            "current_datetime": state.get("current_datetime", ""),
            "_pending_tool_calls": [],
        }

    if state.get("tool_blocked"):
        content = _tool_blocked_answer(state)
        writer({"type": "CHUNK", "content": content})
        return {
            **_final_payload(content, iterations),
            "bob_thesis": state.get("bob_thesis", ""),
            "bob_reasoning_trace": state.get("bob_reasoning_trace", []),
            "current_datetime": state.get("current_datetime", ""),
        }

    if gateway is None:
        return {"errors": state.get("errors", []) + ["no_gateway"]}

    writer(
        {
            "type": "PIPELINE_STEP",
            "run_id": run_id,
            "step": "agent_primary",
            "status": "started",
        }
    )

    _detected_intent = state.get("intent", "")
    is_complex_finance = detect_complex_finance_intent(
        state.get("message", "")
    ) or _detected_intent in ("capital_allocation", "personal_finance")

    # ── Shadow mode: Bob Sovereign ──
    bob_sovereign = os.getenv("SUPEREZIO_BOB_SOVEREIGN", "0") == "1"
    logger.info("BOB_SOVEREIGN=%s iterations=%d", bob_sovereign, iterations)

    if bob_sovereign:
        from datetime import datetime as dt_now

        active_system_prompt = BOB_SOVEREIGN_PROMPT
        now_str = dt_now.now().strftime("%Y-%m-%d %H:%M:%S UTC")
        risk = state.get("risk_tolerance", "moderada")
        bob_intent = state.get("bob_intent", state.get("intent", "general_question"))

        messages = [{"role": "system", "content": active_system_prompt}]
        messages.append(
            {
                "role": "user",
                "content": (
                    f"CURRENT DATE: {now_str}\n"
                    f"DETECTED RISK LEVEL: {risk}\n\n"
                    f"DETECTED BOB INTENT: {bob_intent}\n\n"
                    f"USER: {state.get('message', '')}\n\n"
                    f"BANNED: Do NOT output the 12-section framework template. "
                    f"BANNED: Do NOT use numbered sections like '1. **Scope disclaimer** —'. "
                    f"REQUIRED for allocation/personal-finance questions: one short scope line "
                    f"(educational framework, not personalized financial advice). "
                    f"Talk like a smart friend giving advice. "
                    f"If the user wants a stock pick, give them tickers with reasons. "
                    f"If you need market data, call tools. If you can answer from knowledge, do so."
                ),
            }
        )
        state["current_datetime"] = now_str
    else:
        active_system_prompt = (
            COMPLEX_FINANCE_SYSTEM_PROMPT if is_complex_finance else SYSTEM_PROMPT
        )
        messages = [{"role": "system", "content": active_system_prompt}]
        messages.append({"role": "user", "content": f"User Request: {state.get('message', '')}"})

    # Inject current state context as observations
    observations = []
    if state.get("ticker"):
        observations.append(f"Current Ticker: {state.get('ticker')}")
    if state.get("data_context"):
        observations.append(f"Data/Scan Context:\n{state.get('data_context')[:3000]}")
    if state.get("f51_verdict"):
        observations.append(
            f"F51 Verdict:\n{json.dumps(state.get('f51_verdict'), ensure_ascii=False)}"
        )
    if state.get("expert_summary"):
        observations.append(f"Expert Committee Summary:\n{state.get('expert_summary')}")
    # Dynamic expert weights based on scenario context
    if state.get("expert_weights"):
        observations.append(
            f"Expert Reliability Weights (dynamic, context-adjusted):\n"
            f"{json.dumps(state.get('expert_weights'), ensure_ascii=False)}\n"
            f"Higher weight = more reliable for this specific scenario. "
            f"Give more weight to high-weight experts in your final answer. "
            f"social_forensics (>0.30) has VETO power if manipulation_score >= 70."
        )
    if state.get("neural_decision"):
        observations.append(
            f"Neural Decision:\n{json.dumps(state.get('neural_decision'), ensure_ascii=False)}"
        )
    if state.get("sdca_firewall"):
        observations.append(
            f"SDCA Firewall:\n{json.dumps(state.get('sdca_firewall'), ensure_ascii=False)}"
        )
    if state.get("pennylab_result") or state.get("pennylab"):
        observations.append(
            f"PennyLab Result:\n{json.dumps(state.get('pennylab_result') or state.get('pennylab'), ensure_ascii=False)}"
        )
    if state.get("rag_context"):
        observations.append(f"RAG Forensics Context:\n{state.get('rag_context')}")
    if state.get("executed_tools"):
        observations.append(
            "Tools already executed in this run: "
            + ", ".join(str(tool) for tool in state.get("executed_tools", []))
            + ". Do NOT call these tools again with the same parameters. Use existing results or call final_answer."
        )
    if state.get("errors"):
        observations.append(
            "Errors/Warnings encountered during tool execution:\n"
            + "\n".join(f"- {err}" for err in state.get("errors", []))
        )

    # ── F51 Dynamic Expert Veto Gate ──
    # If social_forensics detected manipulation (score >= 70),
    # the pipeline MUST block any bullish recommendation.
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

    if observations:
        messages.append(
            {"role": "user", "content": "Observations so far:\n" + "\n\n".join(observations)}
        )

    messages.append(
        {
            "role": "user",
            "content": "Decide on the next action (tool call or final_answer). Output ONLY the JSON block.",
        }
    )

    try:
        from ...model_serving.providers import AGENT_PROVIDER_NAME

        raw = await gateway.chat_completion(
            messages=messages,
            temperature=0.7 if bob_sovereign else 0.1,
            max_tokens=4096 if bob_sovereign else 2048,
            preferred_provider=AGENT_PROVIDER_NAME,
            json_mode=False if bob_sovereign else True,
        )

        # Extract sovereign reasoning before cleaning thinking blocks
        reasoning = ""
        if bob_sovereign:
            think_match = re.search(r"<think>(.*?)</think>", raw, re.DOTALL)
            if think_match:
                reasoning = think_match.group(1).strip()
            else:
                json_start = raw.find("{")
                if json_start > 0:
                    reasoning = raw[:json_start].strip()
                elif json_start == -1:
                    reasoning = raw.strip()

            if reasoning:
                if iterations == 0:
                    state["bob_thesis"] = reasoning
                trace = list(state.get("bob_reasoning_trace") or [])
                trace.append(reasoning)
                state["bob_reasoning_trace"] = trace

        # Clean thinking blocks
        if "<think>" in raw:
            raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()

        tool_calls = _parse_tool_calls(raw)

        # ── Bob Sovereign: if no JSON tool call found, treat entire response as final_answer ──
        if bob_sovereign and not tool_calls:
            # If the model put everything inside <think> tags, raw is now empty.
            # Use the extracted reasoning as the final answer instead of falling back.
            content_source = raw.strip() or reasoning
            if len(content_source) > 20:
                tool_calls = [{"tool": "final_answer", "args": {"content": content_source}}]

        # ── Sovereign batch guard: when the model emits ONLY tool-call JSON
        #     with zero natural-language text between them, it is planning its
        #     workflow rather than answering.  Execute the first tool and store
        #     the rest so they are not silently dropped. ──
        pending_tools = list(state.get("_pending_tool_calls") or [])
        if bob_sovereign and tool_calls:
            # Check whether the raw output is pure JSON (no substantial NL text)
            json_only = not reasoning or len(reasoning) < 30 or reasoning.strip().startswith("{")
            if json_only and len(tool_calls) > 1:
                # Keep only the first tool for this iteration; queue the rest
                pending_tools = tool_calls[1:] + pending_tools
                tool_calls = tool_calls[:1]
                state["_pending_tool_calls"] = pending_tools
            elif json_only and len(tool_calls) == 1 and tool_calls[0].get("tool") != "final_answer":
                # Single tool call with no NL – it's a planning step, not an answer
                pass
            elif not json_only and tool_calls:
                # NL present: clear pending queue since model is now reasoning
                state["_pending_tool_calls"] = []

        # If we have pending tools from a previous iteration, process them first
        if not tool_calls and pending_tools:
            tool_calls = [pending_tools[0]]
            state["_pending_tool_calls"] = pending_tools[1:]

        # ── Force final_answer when only tool-call JSON and no NL after max planning ──
        if (
            bob_sovereign
            and tool_calls
            and all(tc.get("tool") != "final_answer" for tc in tool_calls)
            and iterations >= 2
            and not pending_tools
        ):
            # Model keeps planning without answering — force synthesis
            tool_calls = [
                {"tool": "final_answer", "args": {"content": _contract_fallback_answer(state)}}
            ]

        tool_call = tool_calls[0] if tool_calls else None

        if tool_call and "tool" in tool_call:
            if tool_call["tool"] == "final_answer":
                content = tool_call.get("args", {}).get("content") or ""
                if not str(content).strip():
                    if is_complex_finance:
                        content = _complex_finance_fallback_answer(state.get("message", ""))
                    else:
                        content = _contract_fallback_answer(state)
                elif is_complex_finance:
                    content = _repair_complex_finance_answer(state.get("message", ""), content)
                else:
                    content = _repair_answer_quality(content)
                writer({"type": "CHUNK", "content": content})
                writer(
                    {
                        "type": "PIPELINE_STEP",
                        "run_id": run_id,
                        "step": "agent_primary",
                        "status": "completed",
                    }
                )
                return {
                    "final": content,
                    "agent_tool_call": tool_call,
                    "agent_iterations": iterations + 1,
                    "_pending_tool_calls": [],
                    "bob_thesis": state.get("bob_thesis", ""),
                    "bob_reasoning_trace": state.get("bob_reasoning_trace", []),
                    "current_datetime": state.get("current_datetime", ""),
                }
            else:
                return {
                    "agent_tool_call": tool_call,
                    "agent_iterations": iterations + 1,
                    "_pending_tool_calls": list(state.get("_pending_tool_calls") or []),
                    "bob_thesis": state.get("bob_thesis", ""),
                    "bob_reasoning_trace": state.get("bob_reasoning_trace", []),
                    "current_datetime": state.get("current_datetime", ""),
                }
        else:
            # Fallback
            content = (
                _complex_finance_fallback_answer(state.get("message", ""))
                if is_complex_finance
                else _contract_fallback_answer(state)
            )
            writer({"type": "CHUNK", "content": content})
            return {
                "final": content,
                "agent_tool_call": {"tool": "final_answer", "args": {"content": content}},
                "agent_iterations": iterations + 1,
                "_pending_tool_calls": [],
                "bob_thesis": state.get("bob_thesis", ""),
                "bob_reasoning_trace": state.get("bob_reasoning_trace", []),
                "current_datetime": state.get("current_datetime", ""),
            }

    except Exception as exc:
        logger.error(f"Agent error: {exc}")
        return {
            "agent_tool_call": {
                "tool": "final_answer",
                "args": {"content": f"Internal agent error: {exc}"},
            },
            "bob_thesis": state.get("bob_thesis", ""),
            "bob_reasoning_trace": state.get("bob_reasoning_trace", []),
            "current_datetime": state.get("current_datetime", ""),
        }
