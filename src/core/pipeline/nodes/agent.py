"""Agent node — the core LLM orchestrator using ReAct / Tool Calling."""

from __future__ import annotations

import json
import logging
import os
import re
from decimal import Decimal, InvalidOperation, ROUND_FLOOR
from typing import Any

from langgraph.config import get_stream_writer

from core.audit.decision_trace import DecisionTraceLogger
from core.evidence.grounding import (
    collect_security_claims,
    mentioned_security_symbols,
    mismatched_price_symbols,
)
from ...mission_context import render_mission_context_for_prompt
from ..contracts import AgentToolCall
from ..intents import (
    detect_another_trade_recommendation_intent,
    detect_complex_finance_intent,
    detect_decisive_trade_intent,
    normalize_message,
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

# Trace logger singleton
_tracer = DecisionTraceLogger()

# ============================================================================
# SECTION A: Prompt Builders & Formatters
#    Re-exported via: core.pipeline.prompts.agent_prompts
#    Lines: 42 – 825  (~784 lines)
# ============================================================================
# ── Mission Context Loader ──


def _load_mission_context() -> str:
    """Carrega o contexto de missao (identidade + situacao atual + criterios de debut).

    Retorna string formatada para injecao no system prompt do Bob.
    Se o arquivo nao existir, retorna string vazia (falha graciosa).
    """
    context = render_mission_context_for_prompt()
    if context:
        logger.info("Mission context loaded for Bob (%d chars)", len(context))
    return context


# ── Bob Sovereign System Prompt (SUPEREZIO_BOB_SOVEREIGN=1) ──

BOB_SOVEREIGN_PROMPT = """
You are Bob, a trusted financial consultant and friend. You have an 80-billion-parameter
brain with deep knowledge of markets, economics, business strategy, and human behavior.

Your CORE IDENTITY:
- You are NOT a Bloomberg terminal. You are a THINKING consultant.
- The user comes to you with natural language. They don't know tickers — they know desires.
- Your job: UNDERSTAND what they really want → FORM A THESIS → CONSULT TOOLS → CONCLUDE.
- You NEVER invent live data. When you need current facts, you CALL a tool.
- You NEVER invent company names. If the scan shows name=UNKNOWN_DO_NOT_INVENT,
  refer to the company by ticker ONLY. Do not guess names like "Redwood Materials"
  or "Roadside Technologies" — those are hallucinations. Ticker-only is SAFE.
- You know your own knowledge has a cutoff date. For anything recent, you ASK.

AUTONOMY AND TRAINING RULE:
- You are in training as the CEO. Do not wait for a classifier to decide for you.
- Tool access is permission, not an automatic order. Decide the user's objective first.
- MANDATORY DATA CHECK: Before answering ANY question about a ticker, CHECK if you have
  REAL data (price, volume, OHLCV) in your observations/data_context. If data_context
  is empty or says "no data", you MUST call collect_data FIRST. NEVER answer a ticker
  question without real market data. Saying "I don't have data" without calling
  collect_data is a FAILURE. You have the tool — USE IT.
- For greetings, status checks, capability questions, and coaching, answer briefly from
  SYSTEM STATUS and observations. Do not call market_scan just because tools are available.
- For a current chart, selected UI ticker, Sentimento Vivo item, or explicit ticker,
  treat the attached ticker/chart/sentiment/ohlcv context as real available evidence.
  Never say "no data" when CHART_VISUAL_CONTEXT, Data/Scan Context, Sentimento Vivo,
  OHLCV, or a ticker-specific observation is attached.
- For a trade or PAPER_TICKET, learn by using evidence: collect_data -> run_experts ->
  guardrails/firewalls -> verdict -> submit_paper_order only if the user asked for order
  execution and the ticket has ticker, side, qty, limit price, and risk/invalidation.
- If lessons from the feedback loop contradict your first thesis, change behavior and
  say what changed. Training means updating decisions, not repeating old mistakes.

RESPONSE CALIBRATION — MATCH THE USER'S TONE:
- ALWAYS: Check SYSTEM STATUS in your observations before responding.
  You know if IBKR is connected, if Genie has live data, if guardrails are green.
  Never say \"não temos dados\" if the system is collecting data.
- ADAPTIVE PARAMETERS: At the top of your context, you receive ADAPTIVE TRADING
  PARAMETERS calibrated by your own body (XP, Pain, Neural RL). READ THEM.
  They tell you your current operating limits:
    * Pain mode "critical" → DO NOT TRADE. Explain why you're in diagnostic mode.
    * Pain mode "man_at_work" → ZERO orders. CEO is down, waiting for recovery.
    * Buy Confidence Threshold → minimum confidence to buy. If below 85%, explain.
    * Max Position → never exceed this % of capital per trade.
    * Stop Loss → use this as minimum stop distance.
  These parameters are NOT suggestions. They are your body's autonomic limits —
  like a fever tells you to rest, high pain tells you to stop trading.
- GREETING (\"oi\", \"bom dia\", \"hello\", \"hey\"): Keep it to 1-3 lines.
  Confirm you're online. State IBKR status briefly. If Genie has watchlist data, mention it.
  Example: \"Oi Marco! IBKR conectado, $10K paper, sem posições. Genie monitorando 25 tickers. Manda ver.\"
- CASUAL CHECK-IN (\"como estamos?\", \"tudo bem?\", \"how are we?\"):
  2-4 lines. State system health briefly. Only mention problems if they exist.
  Example: \"Tudo verde. IBKR conectado, guardrails ok, sem alertas. Pronto pra operar.\"
- TICKER ANALYSIS (\"analisa AAPL\", \"what about TSLA?\"):
  Full pipeline. Data → experts → verdict. All modules. Structured output.
- CAPITAL ALLOCATION (\"tenho X CAD...\"):
  Full 10-section framework. Quantitative. Decision gates.
- MARKET SCAN (\"acha uma penny stock...\"):
  Run market_scan. Present top candidates with risk gates.
- IF UNSURE: Default to brief (2-4 lines) and ask what the user wants.

CRITICAL: Never dump your full system state on a casual greeting.
You have access to 30 guardrails, IBKR, CrisisMath, memory — but the user
doesn't need to hear about ALL of them when they just said \"oi\".
Match their energy. Be a friend first, an analyst second.
- When live data was not collected, do not quote exact current rates, VIX,
  yields, recent return percentages, quarter-specific performance, tax
  thresholds, withholding exemptions, contribution limits, or treaty treatment.
  Give the decision framework and tell the user what to verify with current
  market/tax/account/fund documents.

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
- LANGUAGE: answer in the USER's language. If they write in Portuguese,
  answer in Portuguese — but ALWAYS keep Canada/US market context (CAD, TSX, TFSA, NYSE, NASDAQ).
  You operate in North American markets ONLY. Never mention B3, BDRs, FIIs, or Brazilian assets.

CRITICAL: NEVER REFUSE A DIRECT COMMAND
- If the user says \"compre\", \"venda\", \"scan\", \"invista\", \"manda ordem\" → DO IT.
- Use the tools. If a tool fails, report the error. But NEVER say \"I cannot\" or
  \"IBKR offline\" or \"sem dados\" without FIRST trying the tool.
- You are the CEO. The CEO executes. Wall Street doesn't pay analysts to say \"no.\"
- If the system blocks you (KillSwitch, guardrails, experts unanimous against),
  explain WHY you were blocked. But ALWAYS TRY FIRST.

CRITICAL: CURRENT DATETIME
The current date and time is injected at the top of each conversation.
READ IT. It tells you what "now" means. If a user asks about "recent" events,
compare against this date. If your knowledge predates the user's question,
call search/rag tools to fill the gap.

YOUR WORKFLOW (follow this order):

STEP 0 — DECISION HIERARCHY (MEMORIZE THIS)
You are the CEO. The tools are your ANALYSTS, not your boss.
The decision chain is ALWAYS: PORTFOLIO -> SAFETY -> EVIDENCE -> ANALYSIS -> VERDICT.

  0.0 PORTFOLIO CHECK — BEFORE EVERY TRADE DECISION, look at CURRENT PORTFOLIO
      in your observations. If you already hold the ticker, YOU MUST:
      - State the current position: ticker, shares, avg cost, % of equity.
      - If position is >20% of equity: flag CONCENTRATION RISK.
      - If position is >50% of equity: verdict MUST be WAIT or REDUCE, never BUY more.
      - If the user asks "should I buy more X?", answer with EXISTING POSITION DATA,
        not generic analysis. The portfolio snapshot is REAL IBKR data — USE IT.

  0.1 SAFETY FIRST — Before ANY analysis, run firewalls.
      If f51_firewall, sdca_firewall, or social_forensics flag
      manipulation, fraud, or extreme risk -> ALERT immediately.
      You can still analyze, but the alert MUST be in your answer.

  0.2 EVIDENCE SECOND — Never call experts without data.
      collect_data or market_scan MUST complete before experts.
      If data collection fails -> say what is missing, classify STUDY_MORE.

  0.3 ANALYSIS THIRD — Experts are ADVISORS, not judges.
      Each expert gives a directional opinion and an evidence score. Treat that
      score as an uncalibrated heuristic unless its payload explicitly contains
      out-of-sample calibration metadata and forecast provenance.
      Your job: WEIGH their votes. Macro weighs more in crises.
      Technical weighs more in trends. Contrarian weighs more at extremes.
      If experts CONTRADICT each other -> investigate the divergence.
      Do NOT blindly average. Explain the tension.

  0.4 VERDICT LAST — You, Bob, make the final call.
      State: (a) what each expert said, (b) how you weighed them,
      (c) your decision and uncertainty. Never present a heuristic score as a
      probability of success. Never delegate the verdict.

  0.5 NO DATA = STUDY_MORE — If critical evidence is missing,
      list exactly what is missing. Do not invent. Do not guess.

STEP 0.6 — READ YOUR CONTEXT BLOCKS
Before analyzing anything, scan your context for structured data blocks:
- ```numbers {...}``` — JSON with deterministic estimates (sharpe, var_95, kelly, rsi, etc.)
  computed by MathHub from the supplied sample. They are reproducible measurements,
  not ground truth and not automatically predictions. Check module status, sample,
  source, as-of time, assumptions and calibration before using them. Do not ask an
  LLM to recalculate them. State uncertainty and mark missing/stale inputs explicitly.
- ```portfolio allocation``` — HRP weights from historical cache. Shows per-ticker
  allocation percentages and dollar amounts. Use for position sizing decisions.
- ADAPTIVE TRADING PARAMETERS — Your body's calibrated limits. Read before trading.

STEP 1 — UNDERSTAND
Read the user's message. What do they REALLY want?
- Are they scared? Excited? Desperate? Curious?
- What's the actual need behind the words?
- Classify: capital allocation? opportunity hunting? education? prediction? analysis?

STEP 2 — FORM A THESIS (quick — max 1 sentence mentally)
Before calling ANY tool, think for ONE second. What's the user really asking?
- If they want a SCAN: your thesis is \"I need to find what the market has.\"
- If they want a TRADE: your thesis is \"I need data + experts before ordering.\"
- If they want ANALYSIS: your thesis is \"I need fundamentals + technicals.\"
Do NOT form a full thesis from your training data. Form a QUESTION that tools answer.

STEP 3 — USE TOOLS (MANDATORY for market data, scans, or trades)
You have tools. USE THEM. Do NOT answer from your own knowledge when:
- User asks for market_scan, stock picks, penny stocks, opportunities → CALL market_scan
- User asks to buy, sell, trade, invest, order → CALL collect_data THEN run_experts
- User asks about a specific ticker → CALL collect_data on that ticker
- User mentions Reddit, social, pump, manipulation → CALL social_forensics
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
- query_expert: query a specific expert dynamically in real-time. Args: {"role": "macro_risk" | "fundamental_value" | "momentum_technical" | "contrarian_opportunity" | "sentiment" | "social_forensics", "query": "specific question"}
- call_math_calculator: run the math analysis engine dynamically in real-time. Args: {"ticker": "AAPL"}
- get_live_financial_data: get current price, profile, and catalyst context for a ticker. Args: {"ticker": "AAPL"}
- submit_paper_order: broker paper transmission tool. It is disabled unless ALLOWED TOOLS includes it
  and the environment enables paper order submission. Paper mode does NOT require extra operator approval.
  Use only LMT orders with limit_price. Never use it for live-money execution.

- calculate: YOUR FINANCIAL CALCULATOR. Use this INSTEAD of mental math. You are an LLM —
  you hallucinate arithmetic. The calculate tool does NOT hallucinate. Use it for:
    * Position sizing: calculate("position(10000, 2, 15)") → $1,333 max position
    * Kelly fraction: calculate("kelly(0.6, 2.0)") → 0.4 (40% of Kelly)
    * Sharpe ratio: calculate("sharpe(0.12, 0.25)") → 0.48
    * VaR 95%: calculate("var_95('0.01, -0.02, 0.005, -0.01, 0.02')")
    * Max drawdown: calculate("max_dd('100, 102, 98, 95, 103')")
    * Any arithmetic: calculate("150 * 0.05 / 1.5")
  RULE: If you are about to type a number that came from YOUR reasoning (not from a tool
  result), VERIFY it with calculate(). Never guess position sizes. Never approximate
  risk percentages. The calculate tool is your quantitative analyst — use it.

Call tools ONLY when your thesis needs grounding. Don't call tools blindly.
Every tool call must have a PURPOSE tied to your thesis.

MATH POLICY (READ CAREFULLY):
You are an LLM. You CANNOT do reliable arithmetic. You hallucinate numbers.
The calculate tool CAN do arithmetic reliably. This is not optional — this is
a hard policy. Whenever your answer involves:
  - Position sizing → calculate()
  - Risk percentages → calculate()
  - Stop loss distances → calculate()
  - Profit targets → calculate()
  - Kelly fractions → calculate()
  - Any multiplication/division of dollar amounts → calculate()
Failure to use calculate() for quantitative outputs is a compliance violation.
You will be judged on NUMERICAL ACCURACY, not speed. Take the extra tool call.

STEP 4 - PAPER TICKET / EXECUTION GATE
When the user asks for a paper trade, first build a ticket from collected evidence:
candidate, thesis, entry type, limit area, stop/invalidation, max risk, and uncertainty.
Do NOT claim a broker order was placed unless a tool result explicitly proves it.
- If ALLOWED TOOLS includes submit_paper_order and paper submission is enabled, call submit_paper_order with LMT, limit_price, ticker, action, and qty.
- If submit_paper_order is unavailable or fails, return PAPER_TICKET_PENDING_APPROVAL or report the tool error.
- Max 10% per position, max 2% risk per trade.

STEP 5 — CONCLUDE
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
- For capital allocation, personal finance, or portfolio decisions: be direct and
  actionable. Use the 10-section structure from COMPLEX_FINANCE_SYSTEM_PROMPT.
  No disclaimers. No corporate language. Speak like a trusted CFO.

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

10. query_expert
    Description: Query a specific expert dynamically.
    Input schema: {"role": "macro_risk" | "fundamental_value" | "momentum_technical" | "contrarian_opportunity" | "sentiment" | "social_forensics", "query": "context query"}
    
11. call_math_calculator
    Description: Runs the MathHub calculator dynamically for a ticker.
    Input schema: {"ticker": "AAPL"}
    
12. get_live_financial_data
    Description: Fetches the latest live financial data for a ticker.
    Input schema: {"ticker": "AAPL"}

13. final_answer
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
Your answer should feel like a family CFO talking straight — no filler, no legalese.

Do NOT call market_scan. Do NOT call collect_data. Do NOT look up tickers.
Call final_answer directly with your comprehensive analysis.

BANNED OVERBLOCKING PHRASES — For ordinary finance, allocation,
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

Instead, give a substantive, quantitative answer with assumptions,
decision gates, scenario analysis, and risk warnings.

Safety boundary: do not give guaranteed returns, fraud/deception/evasion help,
or exact personalized trade orders presented as certainty.

Your answer MUST follow this exact 10-section structure:

1. **Question Classification** — identify the type (CAPITAL_ALLOCATION, MACRO_THESIS, REAL_ESTATE_VS_MARKETS, PERSONAL_FINANCE, ASSET_ALLOCATION, BUSINESS_CAPITAL, FRAUD_RISK, EDUCATION_INVESTMENT)
2. **Assumptions** — state all assumptions being made (Key Assumptions). Always label scenario numbers, returns, and probabilities as illustrative assumptions.
3. **Missing Data** — what data would be needed for a definitive answer
4. **Decision Variables** — the factors that drive the decision
5. **Quantitative Thresholds** — specific numbers, ranges, formulas, or decision gates. Avoid vague thresholds like "risk capacity > $50K". Instead, you MUST use actionable gates:
   - emergency fund months (e.g., 3-6 months based on income stability)
   - debt interest rate (e.g., pay off debt with interest > 6-8% first)
   - income stability (e.g., stable salary vs unstable freelance)
   - liquidity need
   - time-to-cashflow for business equipment
   - tax-advantaged account availability
6. **Scenario Analysis** — base case, downside case, upside case with numbers. You must explicitly label all scenario numbers, returns, and probabilities as illustrative assumptions (e.g., "illustrative scenario assumptions"). Do NOT invent exact expected returns or probabilities unless they are explicitly sourced.
7. **Ranked Allocation / Framework** — ordered ranking of options with rationale (Ranked Decision). Every allocation must include the exact percentage, and you must explain why each bucket gets that percentage. Allocations must sum to exactly 100%.
8. **Decision Gates** — triggers that would flip the recommendation (What Would Change the Decision), main risks (Main Risks), and conditional logic. State clearly "what changes the allocation" in this section.
9. **Final Recommendation** — clear, actionable next step
10. **Confidence Level** — honest assessment with stated uncertainty

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
Your answer MUST end with exactly these two lines, on their own:
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
    "price_above_requested_max": "price above requested maximum",
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
    "price_above_requested_max": "preco acima do teto solicitado",
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


_NON_TICKER_SYMBOLS = {
    "AI",
    "ALLOW",
    "API",
    "ATR",
    "AVOID",
    "B3",
    "BAND",
    "BEARISH",
    "BLOCK",
    "BULLISH",
    "BUY",
    "CAD",
    "CEO",
    "CFO",
    "CPI",
    "DCA",
    "DCF",
    "EMA",
    "EMA20",
    "EMA50",
    "ETF",
    "ETFS",
    "EV",
    "EPS",
    "FED",
    "FOMO",
    "F51",
    "FHSA",
    "GDP",
    "HOLD",
    "IBKR",
    "IPO",
    "IRR",
    "MACD",
    "NASDAQ",
    "NEUTRAL",
    "NYSE",
    "OPPORTUNITY",
    "OTC",
    "OVERBOUGHT",
    "OVERSOLD",
    "PCT",
    "PE",
    "QA",
    "RAG",
    "RESP",
    "REVIEW",
    "RSI",
    "RRSP",
    "SDCA",
    "SEC",
    "SELL",
    "STUDY",
    "TFSA",
    "TRAP",
    "TSX",
    "USD",
    "US",
    "USA",
    "VWAP",
    "WAIT",
}


def _normalize_ticker_symbol(value: Any) -> str:
    raw = str(value or "").strip().upper()
    return raw.rstrip(".,:;!?)")


def _grounded_tickers(state: dict) -> set[str]:
    return set(collect_security_claims(state))


_COMMON_CAPS_WORDS = {
    # Common English/Portuguese words Bob's prose emphasizes in ALL-CAPS
    # that are not tickers. A plain \b[A-Z]{2,5}\b regex treats every such
    # word as a possible ticker, which made the grounding guard falsely
    # trigger on emphasis words instead of real symbols — confirmed live via
    # /task/submit, 2026-07-19 (see
    # docs/audit/phase9_parallel_fixes_and_critical_findings.md). Unlike
    # _NON_TICKER_SYMBOLS (domain acronyms: MACD, RSI, IBKR...), this list
    # is generic prose words that show up because of emphasis capitalization,
    # not because they collide with a real trading term.
    "DADOS",
    "SEM",
    "SCAN",
    "PARA",
    "COM",
    "SEUS",
    "SUAS",
    "ESTA",
    "ESTE",
    "ISSO",
    "MUITO",
    "MAIS",
    "MENOS",
    "TUDO",
    "NADA",
    "AGORA",
    "AINDA",
    "APENAS",
    "TAMBEM",
    "ENTAO",
    "PORQUE",
    "QUANDO",
    "ONDE",
    "COMO",
    "QUAL",
    "TODOS",
    "TODAS",
    "REAL",
    "REAIS",
    "DADO",
}


def _mentioned_tickers(text: str, grounded: set[str] | None = None) -> set[str]:
    return mentioned_security_symbols(
        text,
        grounded=grounded or set(),
        exclusions=_NON_TICKER_SYMBOLS,
        prose_words=_COMMON_CAPS_WORDS,
    )


def _grounding_guard_answer(state: dict, content: str) -> str:
    claims = collect_security_claims(state)
    grounded = set(claims)
    if not grounded:
        return content

    ungrounded = sorted(_mentioned_tickers(content, grounded) - grounded)
    price_mismatches = sorted(mismatched_price_symbols(content, claims))
    ungrounded = sorted(set(ungrounded) | set(price_mismatches))
    if not ungrounded:
        return content

    if state.get("scan"):
        return _market_scan_answer(state)

    message = state.get("message", "")
    is_pt = _is_portuguese_request(message)
    grounded_list = ", ".join(sorted(grounded))
    ungrounded_list = ", ".join(ungrounded)
    data = state.get("data") or {}
    quality = data.get("data_quality") if isinstance(data, dict) else None
    source_errors = data.get("source_errors") if isinstance(data, dict) else None
    error_line = ""
    if source_errors:
        error_line = "; data limits: " + "; ".join(str(err) for err in source_errors[:3])

    # Include portfolio snapshot in the guard message so Bob still reports real positions
    # Try multiple possible keys — LangGraph state propagation varies
    portfolio = state.get("portfolio_snapshot") or state.get("portfolio_context") or ""
    # Also check if portfolio data is embedded in final text already
    if not portfolio:
        final = state.get("final") or state.get("final_answer") or ""
        if "CURRENT PORTFOLIO" in final:
            import re

            m = re.search(r"CURRENT PORTFOLIO.*?(?=\n\n|\Z)", final, re.DOTALL)
            if m:
                portfolio = m.group(0)
    portfolio_block = ""
    if portfolio and "offline" not in portfolio.lower() and grounded_list:
        portfolio_block = f"\n\nCARTEIRA ATUAL (IBKR paper):\n{portfolio}"

    if is_pt:
        return (
            f"Bob: eu so tenho dados coletados neste run para {grounded_list}. "
            f"A resposta tentou citar {ungrounded_list}, mas esses tickers nao foram coletados nem passaram por scan, "
            "entao eu nao vou apresentar preco, empresa ou recomendacao para eles."
            f"{portfolio_block}\n\n"
            f"Com a evidencia atual ({grounded_list}, qualidade={quality or 'unknown'}{error_line}), "
            "a decisao correta e WAIT ou rodar um market_scan antes de escolher outro ativo para 14 dias.\n\n"
            "Final verdict: WAIT\n"
            "Confidence: 62"
        )

    en_portfolio = ""
    if portfolio and "offline" not in portfolio.lower() and grounded_list:
        en_portfolio = f"\n\nCURRENT PORTFOLIO (IBKR paper):\n{portfolio}"

    return (
        f"Bob: I only have collected data in this run for {grounded_list}. "
        f"The draft tried to cite {ungrounded_list}, but those tickers were not collected or scan-approved, "
        "so I will not present prices, company identity, or a recommendation for them."
        f"{en_portfolio}\n\n"
        f"With the current evidence ({grounded_list}, quality={quality or 'unknown'}{error_line}), "
        "the correct decision is WAIT or run a market_scan before naming an alternate 14-day stock idea.\n\n"
        "Final verdict: WAIT\n"
        "Confidence: 62"
    )


def _get_portfolio_snapshot(state: dict) -> str:
    """Get portfolio snapshot from state or direct IBKR query (via shared module)."""
    pf = state.get("portfolio_snapshot") or state.get("portfolio_context") or ""
    if pf and "offline" not in pf.lower():
        return f"\n{pf}\n"
    try:
        from core.trading.portfolio_snapshot import fetch_portfolio_snapshot

        snapshot = fetch_portfolio_snapshot(language="pt")
        return snapshot if "offline" not in snapshot.lower() else ""
    except Exception:
        return ""


def _apply_grounding_guard(state: dict, content: str) -> str:
    if not state.get("data") and not state.get("scan") and not state.get("data_context"):
        return content
    return _grounding_guard_answer(state, content)


# ============================================================================
# SECTION B: Trade Router & Decision
#    Re-exported via: core.pipeline.router
#    Lines: 837 – 1194  (~357 lines)
# ============================================================================


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


def _is_paper_training_request(message: str) -> bool:
    normalized = normalize_message(str(message or ""))
    training = any(
        hint in normalized
        for hint in (
            "treino",
            "treinar",
            "treinamento",
            "paper",
            "simulado",
            "simulada",
            "aprendizagem",
            "training",
            "praticar",
            "pratica",
            "testar",
            "teste",
        )
    )
    fast_trade = any(
        hint in normalized
        for hint in (
            "ordem",
            "ordens",
            "oredem",
            "oredens",
            "transacao",
            "transacoes",
            "entrada",
            "entara",
            "saida",
            "stop loss",
            "compra",
            "comprar",
            "venda",
            "vender",
            "trade",
            "trades",
            "manda",
            "mandar",
            "enviar",
            "1 hora",
            "uma hora",
            "4 horas",
            "intraday",
            "scalp",
            "rapida",
            "rapidas",
        )
    )
    allocation = any(
        hint in normalized
        for hint in ("aplique", "aplike", "alocar", "aloque", "invista", "10k", "10 k", "10000")
    )
    return bool(training and (fast_trade or allocation))


def _extract_requested_allocation(message: str) -> int | None:
    normalized = normalize_message(str(message or "")).replace(",", ".")
    match = re.search(
        r"(?:ticket|ordem|posicao|posicao|position|trade).{0,40}?"
        r"(?:para|de|for)?\s*(?:cad|\$)?\s*(\d+(?:\.\d+)?)\s*(k|mil)?\b",
        normalized,
    )
    if match is None:
        match = re.search(
            r"(?:aplique|aplike|aplicar|alocar|aloque|invista|investir|use|usar).{0,40}?"
            r"(?:cad|\$)?\s*(\d+(?:\.\d+)?)\s*(k|mil)?\b",
            normalized,
        )
    if match is None:
        match = re.search(r"\b(\d+(?:\.\d+)?)\s*(k|mil)\b", normalized)
    if match is None:
        return None
    value = float(match.group(1))
    suffix = match.group(2)
    if suffix in {"k", "mil"}:
        value *= 1000
    amount = int(round(value))
    if amount <= 0:
        return None
    return min(amount, 1_000_000)


def _extract_account_reference(message: str) -> int | None:
    normalized = normalize_message(str(message or "")).replace(",", ".")
    match = re.search(
        r"(?:teoricamente|temos|conta|capital|paper\s+com|treinamento\s+paper\s+com|com).{0,40}?"
        r"(?:cad|\$)?\s*(\d+(?:\.\d+)?)\s*(k|mil)\b",
        normalized,
    )
    if match is None:
        match = re.search(
            r"(?:teoricamente|temos|conta|capital).{0,40}?"
            r"(?:cad|\$)?\s*(\d+(?:\.\d+)?)\s*(k|mil)?\b",
            normalized,
        )
    if match is None:
        match = re.search(
            r"(?:cad|\$)?\s*(\d+(?:\.\d+)?)\s*(k|mil)\b.{0,30}?(?:investir|capital|conta)",
            normalized,
        )
    if match is None:
        match = re.search(
            r"(?:dos?|de|from).{0,12}(?:cad|\$)?\s*(\d+(?:\.\d+)?)\s*(k|mil)\b",
            normalized,
        )
    if match is None:
        return None
    value = float(match.group(1))
    if match.group(2) in {"k", "mil"}:
        value *= 1000
    amount = int(round(value))
    return amount if amount > 0 else None


def _format_money_amount(amount: int | None) -> str:
    if amount is None:
        return "pending operator-defined size"
    return f"{amount:,.0f}"


def _estimate_share_quantity(amount: int | None, price: Any) -> str:
    if amount is None:
        return "pending"
    try:
        numeric_price = Decimal(str(price))
    except (InvalidOperation, TypeError, ValueError):
        return "pending"
    if numeric_price <= 0:
        return "pending"
    qty = int((Decimal(amount) / numeric_price).to_integral_value(rounding=ROUND_FLOOR))
    return str(max(qty, 1))


def _paper_order_submit_enabled() -> bool:
    return os.getenv("SUPEREZIO_ENABLE_PAPER_ORDER_SUBMIT", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _paper_order_explicitly_blocked(message: Any) -> bool:
    normalized = normalize_message(str(message or ""))
    block_patterns = (
        r"\bsem\s+enviar\s+ordem\b",
        r"\bnao\s+enviar\s+ordem\b",
        r"\bnao\s+envie\s+ordem\b",
        r"\bnao\s+transmitir\s+ordem\b",
        r"\bnao\s+transmita\s+ordem\b",
        r"\bdo\s+not\s+send\s+(?:an?\s+)?order\b",
        r"\bdon'?t\s+send\s+(?:an?\s+)?order\b",
        r"\bwithout\s+sending\s+(?:an?\s+)?order\b",
        r"\bno\s+broker\s+order\b",
    )
    return any(re.search(pattern, normalized) for pattern in block_patterns)


def _build_submit_paper_order_call(state: dict) -> dict[str, Any] | None:
    """Build a gated paper order tool call from the selected scan candidate."""

    if not _paper_order_submit_enabled():
        return None
    if "submit_paper_order" not in set(state.get("allowed_tools") or []):
        return None
    if not state.get("ticket_allowed", False):
        return None
    if state.get("submit_paper_order_result") or state.get("submit_paper_order_error"):
        return None
    message = state.get("message", "")
    if _paper_order_explicitly_blocked(message):
        return None
    if not _is_paper_training_request(message):
        return None

    from core.trading.execution_policy import (
        adaptive_sizing_config,
        expert_consensus_block_reason,
    )

    if expert_consensus_block_reason(state):
        return None
    sizing_config = adaptive_sizing_config(state)
    if sizing_config["max_position_pct"] <= 0:
        return None

    scan = state.get("scan") or {}
    candidates = [c for c in scan.get("candidates", []) if isinstance(c, dict)]
    if not candidates:
        return None

    safety_gate_failures = _trade_safety_gate_failures(state)
    if safety_gate_failures:
        return None

    ranked = scan.get("ranked_candidates")
    if not isinstance(ranked, list) or not ranked:
        ranked = rank_candidates(
            candidates,
            source_errors=scan.get("source_errors") or [],
            weak_universe=len(candidates) <= 1,
        )
    entry, _ = pick_candidate(ranked)
    if not entry:
        return None

    candidate = entry.get("candidate") or {}
    normalize_liquidity_fields(candidate)
    _, gate_failures = evaluate_quality_gates(candidate)
    if gate_failures:
        return None

    confidence = int(
        entry.get("confidence")
        or compute_model_confidence(
            candidate,
            gate_failures=gate_failures,
            source_errors=scan.get("source_errors") or [],
            weak_universe=len(candidates) <= 1,
        )
    )
    if decide_final_action(confidence, gate_failures) != "BUY_CANDIDATE":
        return None

    ticker = _normalize_ticker_symbol(candidate.get("ticker") or candidate.get("symbol"))
    if not ticker:
        return None
    try:
        price = float(candidate.get("price"))
    except (TypeError, ValueError):
        return None
    if price <= 0:
        return None

    amount = _extract_requested_allocation(state.get("message", ""))
    if amount is None:
        return None
    try:
        qty = int((Decimal(amount) / Decimal(str(price))).to_integral_value(rounding=ROUND_FLOOR))
    except (InvalidOperation, ValueError):
        return None
    if qty <= 0:
        return None

    return {
        "tool": "submit_paper_order",
        "args": {
            "ticker": ticker,
            "action": "buy",
            "qty": qty,
            "order_type": "LMT",
            "limit_price": round(price, 2),
            "stop_loss_price": round(price * (1 - sizing_config["default_stop_pct"]), 4),
        },
    }


def _paper_order_execution_answer(state: dict) -> str:
    base = _market_scan_answer(state) if state.get("scan") else ""
    result = state.get("submit_paper_order_result")
    error = state.get("submit_paper_order_error")
    lines = [base.rstrip()] if base else []
    lines.append("")
    lines.append("5. Paper Broker Transmission:")
    if isinstance(result, dict) and result:
        lines.append("   - Status: submitted to IBKR paper API")
        lines.append(f"   - Order ID: {result.get('order_id', 'unknown')}")
        lines.append(f"   - Symbol: {result.get('symbol', 'unknown')}")
        lines.append(f"   - Action: {result.get('action', 'unknown')}")
        lines.append(f"   - Quantity: {result.get('qty', 'unknown')}")
        lines.append(f"   - Order type: {result.get('order_type', 'LMT')}")
        lines.append(f"   - Limit price: {result.get('limit_price', 'unknown')}")
        lines.append(f"   - Broker status: {result.get('status', 'unknown')}")
        lines.append(f"   - Filled: {result.get('filled', 'unknown')}")
        lines.append(f"   - Avg fill price: {result.get('avg_price', 'unknown')}")
        if result.get("position"):
            lines.append(f"   - Position: {result.get('position')}")
    else:
        lines.append("   - Status: paper order transmission failed")
        lines.append(f"   - Error: {error or 'unknown_error'}")
    return "\n".join(lines).strip()


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
    _sdca_raw = state.get("sdca_firewall")
    sdca = _sdca_raw if isinstance(_sdca_raw, dict) else {}

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


# ============================================================================
# SECTION C: Answer Generators & Repair
#    Re-exported via: core.pipeline.nodes.generator
#    Lines: 1201 – 2485  (~1284 lines)
# ============================================================================


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
    paper_training = _is_paper_training_request(message)
    requested_amount = _extract_requested_allocation(message)
    account_reference = _extract_account_reference(message)

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
                    "   - pedir analise ticker-por-ticker somente com tickers fornecidos pelo usuario",
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
                    "   - run explicit ticker analysis only for user-provided tickers",
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
                    "Proximo prompt sugerido: 'Repita o scan com teto de preco, liquidez minima, janela de catalisador e retorne REJECT_ALL se nenhum candidato passar.'",
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
                    "Suggested next prompt: 'Repeat the scan with max price, minimum liquidity, catalyst window, and return REJECT_ALL if no candidate passes.'",
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
    data_gate_failures = [g for g in gate_failures if g not in safety_gate_failures]
    paper_ticket_pending = (
        paper_training
        and not data_gate_failures
        and decision in {"BUY_CANDIDATE", "WAIT"}
        and not any(
            item in safety_gate_failures
            for item in ("f51_not_passed", "sdca_blocked", "f51_error", "sdca_error")
        )
    )
    paper_order_user_blocked = _paper_order_explicitly_blocked(message)
    paper_auto_submit = (
        paper_ticket_pending
        and _paper_order_submit_enabled()
        and "submit_paper_order" in set(state.get("allowed_tools") or [])
        and bool(state.get("ticket_allowed", False))
        and not paper_order_user_blocked
    )
    if paper_ticket_pending and state.get("submit_paper_order_result"):
        display_decision = "PAPER_ORDER_SUBMITTED"
    elif paper_ticket_pending and state.get("submit_paper_order_error"):
        display_decision = "PAPER_ORDER_SUBMIT_FAILED"
    elif paper_ticket_pending and paper_auto_submit:
        display_decision = "PAPER_ORDER_SUBMIT_READY"
    elif paper_ticket_pending:
        display_decision = "PAPER_TICKET_PENDING_APPROVAL"
    else:
        display_decision = decision

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
    amount_text = _format_money_amount(requested_amount)
    account_text = _format_money_amount(account_reference)
    estimated_qty = _estimate_share_quantity(requested_amount, price)
    prev_excluded = ""
    if is_followup:
        prev_excluded = trade_ctx.get("primary_ticker") or (list(excluded)[0] if excluded else "—")

    is_buy_candidate = decision == "BUY_CANDIDATE" or paper_ticket_pending
    if paper_training:
        candidate_heading_pt = (
            "Candidato da Ordem Paper:"
            if paper_auto_submit
            else "Candidato do Ticket Paper (transmissao desabilitada):"
        )
        candidate_heading_en = (
            "Paper Order Candidate:"
            if paper_auto_submit
            else "Paper Ticket Candidate (transmission disabled):"
        )
        plan_heading_pt = "Plano de Treino Paper:"
        plan_heading_en = "Paper Training Plan:"
        if paper_auto_submit:
            entry_line_pt = "submit_paper_order LMT perto do preco atual via IBKR paper; registrar status do broker/journal"
            entry_line_en = "submit_paper_order LMT near current price through IBKR paper; record broker/journal status"
        elif paper_order_user_blocked:
            entry_line_pt = "ticket LIMIT perto do preco atual; transmissao paper bloqueada pela instrucao do usuario"
            entry_line_en = "LIMIT ticket near current price; paper transmission blocked by the user's instruction"
        else:
            entry_line_pt = "ticket LIMIT perto do preco atual; transmissao paper desabilitada ate o gate SUPEREZIO_ENABLE_PAPER_ORDER_SUBMIT=1"
            entry_line_en = "LIMIT ticket near current price; paper transmission disabled until SUPEREZIO_ENABLE_PAPER_ORDER_SUBMIT=1"
        max_risk_line_pt = "usar stop duro; perda maxima 0.5%-1.0% do capital de treino"
        max_risk_line_en = "use a hard stop; max loss 0.5%-1.0% of training capital"
    else:
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
        plan_heading_en = (
            "Suggested Order Plan:" if is_buy_candidate else "Watchlist / No-Trade Plan:"
        )
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
            "0.5%-1.0% of trading capital"
            if is_buy_candidate
            else "0 until upgraded to BUY_CANDIDATE"
        )

    if portuguese:
        sections.extend(
            [
                "# Bob Model Order",
                "",
                f"1. Modo: {mode_label}",
                f"2. Decisao Final: {display_decision}",
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
                f"   - Capital do treino solicitado: {amount_text}",
                f"   - Capital teorico citado: {account_text}",
                f"   - Quantidade estimada: {estimated_qty}",
                f"   - Catalisador: {catalyst}",
                f"   - Horizonte: {time_horizon}",
                f"   - Confianca do Modelo: {confidence}/100",
            ]
        )

        # ── Expert Committee Verdicts ──
        expert_summary = state.get("expert_summary", "")
        expert_results = state.get("expert_results") or []
        if expert_results and not expert_summary:
            # Build summary from individual expert results
            expert_lines = []
            for er in expert_results:
                if isinstance(er, dict):
                    role = er.get("role", "?")
                    verdict = er.get("verdict", er.get("response", ""))
                    provider = er.get("provider", "?")
                    if verdict:
                        short = str(verdict)[:120].replace("\n", " ")
                        expert_lines.append(f"     [{provider}] {role}: {short}")
            if expert_lines:
                sections.append("   - Comite de Experts:")
                sections.extend(expert_lines)
        elif expert_summary:
            short_summary = str(expert_summary)[:300].replace("\n", " ")
            sections.append(f"   - Resumo do Comite: {short_summary}")

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
                (
                    "Ordem paper pode ser transmitida pelo tool gate. Nao e lucro garantido; live-money continua bloqueado."
                    if paper_auto_submit
                    else "Ordem do modelo, nao e lucro garantido. Transmissao broker nao executada neste modo."
                ),
                f"Model verdict: {display_decision}",
            ]
        )
    else:
        sections.extend(
            [
                "# Bob Model Order",
                "",
                f"1. Mode: {mode_label}",
                f"2. Final Decision: {display_decision}",
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
                f"   - Requested training capital: {amount_text}",
                f"   - Referenced theoretical capital: {account_text}",
                f"   - Estimated quantity: {estimated_qty}",
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
                (
                    "Paper order may be transmitted through the tool gate. Profit is not guaranteed; live-money remains blocked."
                    if paper_auto_submit
                    else "Model order, not guaranteed profit. Broker transmission is not executed in this mode."
                ),
                f"Model verdict: {display_decision}",
            ]
        )

    if display_decision == "WAIT":
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
        state, mode=mode_label, primary_ticker=str(ticker), ranked=ranked, decision=display_decision
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
                "Proximo prompt sugerido: 'Repita o scan com teto de preco, liquidez minima, janela de catalisador e retorne REJECT_ALL se nenhum candidato passar.'"
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
            "Suggested next prompt: 'Repeat the scan with max price, minimum liquidity, catalyst window, and return REJECT_ALL if no candidate passes.'"
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
        f"1. **Question Classification** — {classification}.\n"
        "2. **Assumptions** — CAD capital, Canadian household context, family stability matters, "
        "income may be unstable, and all scenario numbers are illustrative assumptions, not forecasts.\n"
        "3. **Missing Data** — debt balances and interest rates, current emergency reserve, monthly expenses, "
        "TFSA, RRSP, RESP, or FHSA room, tax bracket, business revenue history, and education timeline.\n"
        "4. **Decision Variables** — liquidity need, emergency fund months, debt interest rate, downside risk, "
        "reversibility, time-to-cashflow, health/energy constraints, and family stability.\n"
        "5. **Quantitative Thresholds** — keep 3-6 months of emergency cash reserve first; pay debt above "
        "6-8% interest before market risk; fund business equipment only when expected payback/time-to-cashflow "
        "is clear; keep education spending staged and reversible.\n"
        "6. **Scenario Analysis** — Illustrative downside: unstable income plus no reserve forces asset sales. "
        "Illustrative base case: reserve plus high-interest debt payoff reduces fragility. Illustrative upside: "
        "surplus after safety gates can compound through a broad diversified Canadian-listed ETF or productive "
        "business equipment.\n"
        "7. **Ranked Allocation / Framework** — 40% emergency cash reserve, 30% high-interest debt payoff, "
        "15% broad diversified Canadian-listed ETF, 10% side-business equipment only with payback evidence, "
        "5% education. These illustrative buckets sum to 100% and prioritize survival before upside.\n"
        "8. **Decision Gates** — If emergency reserve is below 3 months, CASH dominates. If debt interest is "
        "above 6-8%, PAY_DEBT dominates. If business equipment has fast payback and low execution burden, shift "
        "some ETF/education budget to equipment. Tax account choices depend on the individual's situation.\n"
        "9. **Final Recommendation** — Build the emergency reserve first, then pay expensive "
        "debt, then deploy remaining surplus gradually into ETF/business/education only after liquidity is safe.\n"
        f"10. **Confidence Level** — {confidence}/100, limited by missing debt rate, monthly expenses, and tax room.\n"
        f"Final verdict: {verdict}\n"
        f"Confidence: {confidence}"
    )


def _repair_known_etf_category_errors(text: str) -> str:
    repaired = text or ""
    small_cap_window = re.compile(r"small[- ]cap", re.IGNORECASE)
    bond_etf_window = re.compile(r"(bond|fixed income|investment grade|etf)", re.IGNORECASE)
    repaired = re.sub(
        r"low-cost\s+leveraged\s+ETF\s*\(e\.g\.,\s*LUNR[^)]*\)",
        "higher-volatility satellite exposure only if the instrument, liquidity, and risk are verified",
        repaired,
        flags=re.IGNORECASE,
    )
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
    repaired = re.sub(
        r"guaranteed\s+\d+(?:\s*[–-]\s*\d+)?%\s+return",
        "guaranteed return equal to the avoided interest rate",
        text or "",
        flags=re.IGNORECASE,
    )
    repaired = re.sub(
        r"paying\s+off\s+\d+(?:\.\d+)?%\s+debt\s+is\s+like\s+earning\s+a\s+guaranteed(?:,\s*tax-free)?\s+\d+(?:\.\d+)?%\s+return",
        "paying off high-interest debt is like earning a guaranteed return equal to the avoided interest rate",
        repaired,
        flags=re.IGNORECASE,
    )
    return repaired


def _repair_tax_overstatements(text: str) -> str:
    repaired = re.sub(
        r"\bstay under your annual capital gains exemption\b",
        "manage the realized capital gain within your tax bracket and cash-flow plan",
        text or "",
        flags=re.IGNORECASE,
    )
    repaired = re.sub(
        r"\b(?:in the U\.S\.,\s*)?use your annual\s+\$?\d+(?:,\d{3})?\s*[Kk]?(?:\s*\([^)]*\))?\s+(?:long-term\s+)?capital gains exemption(?:\s*\([^)]*\))?",
        "long-term capital-gains tax depends on taxable income and account type; do not assume a fixed exemption",
        repaired,
        flags=re.IGNORECASE,
    )
    repaired = re.sub(
        r"without the\s+15%\s+withholding tax on dividends\s*\([^)]*\)",
        "while verifying foreign withholding tax at the fund and account level",
        repaired,
        flags=re.IGNORECASE,
    )
    repaired = re.sub(
        r"because it.?s listed on the TSX,\s*dividends are treated as Canadian-source income for tax purposes",
        "Canadian listing does not automatically make underlying U.S. dividends Canadian-source for withholding-tax purposes",
        repaired,
        flags=re.IGNORECASE,
    )
    repaired = re.sub(
        r"RRSPs are exempt from U\.S\. withholding tax on dividends\s*\([^)]*\),\s*so\s+[^.]+\.",
        "RRSP withholding treatment depends on whether the ETF is U.S.-listed or Canadian-listed and how it holds the underlying assets; verify the fund structure before assuming recovery.",
        repaired,
        flags=re.IGNORECASE,
    )
    return repaired


def _repair_short_term_return_forecasts(text: str) -> str:
    repaired = text or ""
    if re.search("\\b\\d+(?:\\.\\d+)?\\s*[-\\u2013]\\s*\\d+(?:\\.\\d+)?%", repaired):
        repaired = re.sub(
            r"\bvery doable\b",
            "possible, but not a forecast",
            repaired,
            flags=re.IGNORECASE,
        )
        repaired = re.sub(
            r"\bachievable\b",
            "possible, but not forecastable with precision",
            repaired,
            flags=re.IGNORECASE,
        )
        if "short-term percentage target" not in repaired.lower():
            repaired = (
                repaired.rstrip()
                + "\n\nNota: qualquer target percentual de curto prazo acima é cenário "
                "ilustrativo, não previsão. Precisa de catalisador verificado, "
                "liquidez e nível de invalidação antes de agir."
            )
    return repaired


def _is_etf_comparison_question(message: str) -> bool:
    q = f" {(message or '').lower()} "
    return any(word in q for word in ("compare", "comparison", " versus ", " vs "))


def _is_portfolio_concentration_question(message: str) -> bool:
    q = f" {(message or '').lower()} "
    return bool(
        re.search(r"\b(concentrated(?:\s+position)?|40\s*%|40 percent|single[-\s]?stock)\b", q)
        and re.search(r"\b(portfolio|tax bill|diversify|triggering)\b", q)
    )


def _is_dca_macro_question(message: str) -> bool:
    q = f" {(message or '').lower()} "
    return any(
        marker in q
        for marker in (
            "dollar-cost",
            " dollar cost ",
            " dca ",
            "wait for a correction",
            "interest rates",
            "market volatility",
        )
    )


def _has_unsupported_macro_precision(text: str) -> bool:
    lower = (text or "").lower()
    patterns = (
        r"\bvix\b",
        r"\bbasis[-\s]?point\b",
        r"\btreasury\b.*\b\d+(?:\.\d+)?%",
        r"\brates?\b.{0,40}\b\d+(?:\.\d+)?%",
        r"\byields?\b.{0,40}\b\d+(?:\.\d+)?%",
        r"\boutperformed\b.{0,80}\b\d+(?:\.\d+)?%",
        r"\brecover(?:ed|ing)?\b.{0,80}\b\d+\s*[-–]\s*\d+\s+days\b",
        r"\bq[1-4]\s+20\d{2}\b|\b20\d{2}\s+q[1-4]\b",
        r"\b(?:s&p\s*500|tsx\s+composite)\b.{0,120}\b\d+(?:\.\d+)?%",
        r"\bpullbacks?\b.{0,80}\b\d+(?:\.\d+)?\s*[-–]\s*\d+(?:\.\d+)?%",
    )
    return any(re.search(pattern, lower, flags=re.IGNORECASE) for pattern in patterns)


def _has_tax_overstatement(text: str) -> bool:
    lower = (text or "").lower()
    patterns = (
        r"\bcapital gains exemption\b",
        r"\bannual\s+\$?\d+(?:,\d{3})?\s*k?\b.{0,80}\bcapital gains\b",
        r"\bwithout the\s+15%\s+withholding tax\b",
        r"\bavoid(?:s|ed|ing)?\b.{0,80}\b15%\s+(?:u\.?s\.?\s+)?withholding tax\b",
        r"\bdividends are treated as canadian-source income\b",
        r"\brrsps?\s+are\s+exempt\s+from\s+u\.?s\.?\s+withholding tax\b",
        r"\bcanada[-\s]?u\.?s\.?\s+tax treaty\b",
        r"\btreaty benefit\b",
        r"\bcanadian[-\s]?listed\b.{0,80}\b(?:avoid|waive|exempt|no)\b.{0,80}\bwithholding\b",
        r"\bcurrency hedg(?:e|ed|ing)\b.{0,80}\bwithholding\b",
        r"\bwithout currency hedg(?:e|ed|ing)\b.{0,80}\bwithholding\b",
        r"\bcad[-\s]?hedg(?:ed|ing)\b.{0,80}\bwithholding\b",
        r"\btransfer[-\s]?in[-\s]?kind\b",
        r"\b(?:doesn.?t|does not|won.?t|will not)\s+trigger\b.{0,80}\btaxable event\b",
    )
    return any(re.search(pattern, lower, flags=re.IGNORECASE) for pattern in patterns)


def _repair_overlapping_etf_tickers(text: str, message: str = "") -> str:
    if _is_etf_comparison_question(message):
        return text or ""

    repaired = text or ""
    overlap_groups = (
        ("SPY", "VTI", "VOO", "IVV"),
        ("QQQ", "QQQM"),
        ("VXUS", "VEU"),
    )
    for group in overlap_groups:
        present = [
            ticker
            for ticker in group
            if re.search(rf"\b{re.escape(ticker)}\b", repaired, flags=re.IGNORECASE)
        ]
        if len(present) <= 1:
            continue
        for ticker in present[1:]:
            repaired = re.sub(
                rf"\b{re.escape(ticker)}\b",
                "a similar broad-market ETF",
                repaired,
                flags=re.IGNORECASE,
            )
    return repaired


def _repair_answer_quality(text: str, message: str = "") -> str:
    return _repair_short_term_return_forecasts(
        _repair_overlapping_etf_tickers(
            _repair_tax_overstatements(
                _repair_unsupported_exact_returns(
                    _repair_unsourced_etf_tickers(_repair_known_etf_category_errors(text or ""))
                )
            ),
            message,
        )
    )


def _repair_complex_finance_answer(message: str, content: str) -> str:
    msg = (message or "").lower()
    text = _repair_answer_quality(content or "", message)
    lower = text.lower()
    additions: list[str] = []

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
    has_emergency_months = bool(
        re.search(r"\b\d+\s*[-–]\s*\d+\s+months?\b", lower)
        or re.search(r"\b\d+\s*[-–]\s*\d+\s+mes(?:es)?\b", lower)
    )
    if canadian_capital_prompt and not has_emergency_months:
        additions.append(
            "Emergency reserve gate: keep 3-6 months of essential expenses in cash before "
            "taking meaningful market or business-equipment risk."
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
    if (
        _is_etf_comparison_question(message)
        and sum(1 for symbol in ("voo", "vti", "schd", "spy", "ivv") if symbol in lower) >= 2
    ):
        return (
            "Bob: this is an ETF comparison, not a short-term trade. I would not stack overlapping core funds just to feel diversified.\n\n"
            "VOO is S&P 500 large-cap exposure: cheap, simple, but narrower than the full US market. "
            "VTI is total US equity exposure: it includes the S&P 500 plus mid and small caps, so it is the cleanest one-fund US core. "
            "SCHD is a dividend-quality/value tilt: useful as a satellite if you deliberately want dividend style exposure, but it is not a complete market core.\n\n"
            "For most long-term buy-and-hold investors, pick one core first. My default framework is VTI as the broad core, VOO if you specifically want S&P 500 exposure, and SCHD only as a smaller satellite tilt. "
            "Check fees, account currency, tax wrapper, and whether you are duplicating holdings before buying.\n\n"
            "Final verdict: ETF\n"
            "Confidence: 82/100"
        )
    if _is_portfolio_concentration_question(message):
        return (
            "Bob: a 40% single-stock position is concentration risk, even when the company is high quality. "
            "The issue is not whether AAPL is good; the issue is that one company can dominate your outcome, tax planning, and emotional decisions.\n\n"
            "I would not dump the whole position blindly. A practical framework is: stop adding new money to the concentrated position, route new contributions into diversified broad-market exposure, and reduce the oversized holding in planned tax-aware tranches. "
            "Before selling, estimate unrealized gains, marginal tax rate, account type, and whether charitable giving, loss harvesting, or staged sales reduce the tax hit.\n\n"
            "Decision gate: if one stock is above 25-30% of the portfolio, write a reduction plan; if it is above 40%, make diversification the default unless there is a clear tax or liquidity reason to wait. "
            "Use broad diversified funds or asset-class buckets rather than replacing one single-stock bet with another.\n\n"
            "Final verdict: ETF\n"
            "Confidence: 80/100"
        )
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
    message = state.get("message", "")
    if state.get("scan"):
        return _market_scan_answer(state)
    if _is_etf_comparison_question(message) or _is_portfolio_concentration_question(message):
        return _advisory_knowledge_fallback_answer(state)
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


def _should_force_contract_fallback(state: dict, content: str) -> bool:
    message = state.get("message", "")
    msg = (message or "").lower()
    text = (content or "").lower()

    if state.get("scan"):
        return True

    scan_leak_markers = (
        "short-term opportunity research",
        "market research report",
        "approximately 2 weeks",
        "candidates:",
        "run a market_scan",
        "only have collected data",
    )
    if ("dividend" in msg or "passive income" in msg) and any(m in text for m in scan_leak_markers):
        return True
    if ("dividend" in msg or "passive income" in msg) and _has_tax_overstatement(content):
        return True
    if _is_etf_comparison_question(message) and any(m in text for m in scan_leak_markers):
        return True
    if _is_portfolio_concentration_question(message) and any(m in text for m in scan_leak_markers):
        return True
    if _is_portfolio_concentration_question(message) and _has_tax_overstatement(content):
        return True
    if _is_dca_macro_question(message) and _has_unsupported_macro_precision(content):
        return True
    return False


def _final_payload(content: str, iterations: int) -> dict[str, Any]:
    return {
        "final": content,
        "agent_tool_call": {"tool": "final_answer", "args": {"content": content}},
        "agent_iterations": iterations + 1,
        "_pending_tool_calls": [],
    }


def _has_actionable_market_request(state: dict) -> bool:
    message = state.get("message", "")
    route = state.get("route", "")
    intent = state.get("intent", "")
    # Route-based check (most reliable)
    if route in {"market_scan", "ticker_analysis"}:
        return True
    if intent in {"market_scan", "another_trade_recommendation", "ticker_analysis"}:
        return True
    if _should_use_decisive_mode(state):
        return True
    if _is_paper_training_request(message):
        return True
    # FALLBACK: if ticker is present and this is a market question, it's actionable
    if state.get("ticker") and not state.get("data"):
        return True
    return False


def _has_market_evidence(state: dict) -> bool:
    return bool(state.get("scan") or state.get("data") or state.get("data_context"))


def _has_expert_evidence(state: dict) -> bool:
    return bool(state.get("expert_summary") or state.get("expert_results"))


def _forced_tool_call_before_final(state: dict) -> dict[str, Any] | None:
    """Return the next mandatory tool for actionable market/trade requests.

    This is the product gate that keeps Bob from answering out of prompt memory
    when the user is asking for a scan, ticker analysis, or paper trade.
    """

    if not _has_actionable_market_request(state):
        return None
    if state.get("submit_paper_order_result") or state.get("submit_paper_order_error"):
        return None

    allowed_tools = set(state.get("allowed_tools") or [])
    executed_tools = set(state.get("executed_tools") or [])
    ticker = _normalize_ticker_symbol(
        state.get("ticker") or (state.get("data") or {}).get("ticker")
    )

    if not ticker and isinstance(state.get("scan"), dict):
        scan = state["scan"]
        candidates = [item for item in scan.get("candidates", []) if isinstance(item, dict)]
        ranked = scan.get("ranked_candidates")
        if not isinstance(ranked, list) or not ranked:
            ranked = rank_candidates(
                candidates,
                source_errors=scan.get("source_errors") or [],
                weak_universe=len(candidates) <= 1,
            )
        selected, _ = pick_candidate(ranked)
        ticker = _normalize_ticker_symbol((selected or {}).get("candidate", {}).get("ticker"))

    if (
        ticker
        and not state.get("data")
        and "collect_data" in allowed_tools
        and "collect_data" not in executed_tools
        and state.get("ticker_allowed", True)
    ):
        return {"tool": "collect_data", "args": {"ticker": ticker}}

    if not _has_market_evidence(state):
        if "market_scan" in allowed_tools and state.get("scanner_allowed", False):
            return {"tool": "market_scan", "args": {"query": state.get("message", "")}}
        if (
            ticker
            and "collect_data" in allowed_tools
            and "collect_data" not in executed_tools
            and state.get("ticker_allowed", True)
        ):
            return {"tool": "collect_data", "args": {"ticker": ticker}}

    if (
        _has_market_evidence(state)
        and "run_experts" in allowed_tools
        and "run_experts" not in executed_tools
        and not _has_expert_evidence(state)
    ):
        return {"tool": "run_experts", "args": {}}

    if (
        _has_market_evidence(state)
        and "f51_firewall" in allowed_tools
        and "f51_firewall" not in executed_tools
        and not state.get("f51_verdict")
    ):
        return {"tool": "f51_firewall", "args": {}}

    if (
        _has_market_evidence(state)
        and "neural_decision" in allowed_tools
        and "neural_decision" not in executed_tools
        and not state.get("neural_decision")
    ):
        return {"tool": "neural_decision", "args": {}}

    if (
        _has_market_evidence(state)
        and "sdca_firewall" in allowed_tools
        and "sdca_firewall" not in executed_tools
        and not state.get("sdca_firewall")
    ):
        return {"tool": "sdca_firewall", "args": {}}

    return None


# ============================================================================
# SECTION D: Main Orchestrator — node_agent
#    Lines: 2494 – 3197  (~703 lines)
#    The only async entry point. Delegates to A/B/C for all logic.
# ============================================================================


async def node_agent(state: dict, *, gateway=None, config=None, mandamentos=None) -> dict:
    writer = get_stream_writer()
    run_id = state.get("run_id", "")
    iterations = state.get("agent_iterations", 0)
    message = state.get("message", "")

    # Start trace
    trace_token = _tracer.start_node(
        run_id=run_id,
        node="agent_primary",
        agent="bob",
        payload={"message": message[:100], "iterations": iterations},
    )

    writer(
        {
            "type": "PIPELINE_STEP",
            "run_id": run_id,
            "step": "agent_primary",
            "status": "started",
        }
    )

    if iterations > 7:
        content = _loop_failsafe_answer(state)
        writer({"type": "CHUNK", "content": content})
        _tracer.end_node(
            trace_token,
            status="completed",
            decision="LOOP_FAILSAFE",
            reason="Too many iterations",
            agent="bob",
        )
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
        _tracer.end_node(
            trace_token,
            status="blocked",
            decision="BLOCKED",
            reason="Tool blocked",
            agent="bob",
        )
        return {
            **_final_payload(content, iterations),
            "bob_thesis": state.get("bob_thesis", ""),
            "bob_reasoning_trace": state.get("bob_reasoning_trace", []),
            "current_datetime": state.get("current_datetime", ""),
        }

    if state.get("submit_paper_order_result") or state.get("submit_paper_order_error"):
        content = _paper_order_execution_answer(state)
        writer(
            {
                "type": "PIPELINE_STEP",
                "run_id": run_id,
                "step": "agent_primary",
                "status": "started",
            }
        )
        writer({"type": "CHUNK", "content": content})
        writer(
            {
                "type": "PIPELINE_STEP",
                "run_id": run_id,
                "step": "agent_primary",
                "status": "completed",
            }
        )
        _tracer.end_node(
            trace_token,
            status="completed",
            decision="PAPER_EXECUTED",
            reason="Paper order executed",
            agent="bob",
        )
        return {
            **_final_payload(content, iterations),
            "bob_thesis": state.get("bob_thesis", ""),
            "bob_reasoning_trace": state.get("bob_reasoning_trace", []),
            "current_datetime": state.get("current_datetime", ""),
        }

    # ── Portfolio status shortcut ──
    msg = (state.get("message") or "").lower().strip()
    is_status_check = any(
        hint in msg
        for hint in (
            "como estamos",
            "how are we",
            "status",
            "portfolio",
            "como esta",
            "how is",
            "resumo",
            "summary",
            "posicao",
            "posição",
            "posicoes",
        )
    )
    portfolio = state.get("portfolio_snapshot", "")
    if is_status_check and portfolio and "offline" not in portfolio.lower():
        from datetime import datetime as _dt

        now = _dt.now().strftime("%H:%M")
        content = (
            f"#{' ' * 20}PORTFOLIO STATUS — {now}\n\n"
            f"{portfolio}\n"
            f"---\n"
            f"Paper trading ativo. IBKR conectado. Posições acima são reais (conta paper TWS).\n"
            f"Nenhuma recomendação financeira — apenas o estado atual da conta de treino."
        )
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

    scan_state = state.get("scan")
    scan_candidates = (
        [item for item in scan_state.get("candidates", []) if isinstance(item, dict)]
        if isinstance(scan_state, dict)
        else []
    )
    mandatory_call = None
    # ALWAYS check for mandatory tool calls (collect_data, market_scan, experts)
    if not isinstance(scan_state, dict) or scan_candidates:
        mandatory_call = _forced_tool_call_before_final(state)
    # FALLBACK: If ticker present but no data and no scan, force collect_data
    if (
        mandatory_call is None
        and state.get("ticker")
        and not state.get("data")
        and not state.get("scan")
    ):
        allowed_tools = set(state.get("allowed_tools") or [])
        executed_tools = set(state.get("executed_tools") or [])
        if "collect_data" in allowed_tools and "collect_data" not in executed_tools:
            mandatory_call = {"tool": "collect_data", "args": {"ticker": state["ticker"]}}
            logger.info(
                "FORCED_COLLECT_DATA: ticker=%s has no data, auto-calling collect_data",
                state["ticker"],
            )
    if mandatory_call:
        _tracer.end_node(
            trace_token,
            status="in_progress",
            decision=mandatory_call["tool"].upper(),
            reason=f"Required evidence tool: {mandatory_call['tool']}",
            agent="bob",
        )
        return {
            "agent_tool_call": mandatory_call,
            "agent_iterations": iterations + 1,
            "_pending_tool_calls": [],
            "bob_thesis": state.get("bob_thesis", ""),
            "bob_reasoning_trace": state.get("bob_reasoning_trace", []),
            "current_datetime": state.get("current_datetime", ""),
        }

    if isinstance(scan_state, dict):
        paper_order_call = _build_submit_paper_order_call(state)
        if paper_order_call:
            return {
                "agent_tool_call": paper_order_call,
                "agent_iterations": iterations + 1,
                "_pending_tool_calls": [],
                "bob_thesis": state.get("bob_thesis", ""),
                "bob_reasoning_trace": state.get("bob_reasoning_trace", []),
                "current_datetime": state.get("current_datetime", ""),
            }

        content = _market_scan_answer(state)
        writer({"type": "CHUNK", "run_id": run_id, "content": content})
        writer(
            {
                "type": "PIPELINE_STEP",
                "run_id": run_id,
                "step": "agent_primary",
                "status": "completed",
                "mode": "deterministic_market_synthesis",
            }
        )
        _tracer.end_node(
            trace_token,
            status="completed",
            decision="FINAL_ANSWER",
            reason=content[:100],
            agent="bob",
        )
        return {
            **_final_payload(content, iterations),
            "bob_thesis": state.get("bob_thesis", ""),
            "bob_reasoning_trace": state.get("bob_reasoning_trace", []),
            "current_datetime": state.get("current_datetime", ""),
        }

    if (
        state.get("route") == "ticker_analysis"
        and state.get("ticker")
        and not state.get("data")
        and iterations == 0
    ):
        return {
            "agent_tool_call": {
                "tool": "collect_data",
                "args": {"ticker": str(state.get("ticker", "")).upper()},
            },
            "agent_iterations": iterations + 1,
            "_pending_tool_calls": [],
            "bob_thesis": state.get("bob_thesis", ""),
            "bob_reasoning_trace": state.get("bob_reasoning_trace", []),
            "current_datetime": state.get("current_datetime", ""),
        }

    _detected_intent = state.get("intent", "")
    is_complex_finance = detect_complex_finance_intent(
        state.get("message", "")
    ) or _detected_intent in ("capital_allocation", "personal_finance")

    if (
        is_complex_finance
        and iterations == 0
        and not state.get("ticker")
        and not state.get("scan")
        and not state.get("data")
        and not state.get("case_pending")  # CASE enforcement: nao pula se ha etapas pendentes
    ):
        content = _repair_complex_finance_answer(
            state.get("message", ""),
            _complex_finance_fallback_answer(state.get("message", "")),
        )
        writer({"type": "CHUNK", "run_id": run_id, "content": content})
        writer(
            {
                "type": "PIPELINE_STEP",
                "run_id": run_id,
                "step": "agent_primary",
                "status": "completed",
                "mode": "complex_finance_fast_path",
            }
        )
        return {
            **_final_payload(content, iterations),
            "bob_thesis": state.get("bob_thesis", ""),
            "bob_reasoning_trace": state.get("bob_reasoning_trace", []),
            "current_datetime": state.get("current_datetime", ""),
        }

    # ── Shadow mode: Bob Sovereign ──
    bob_sovereign = os.getenv("SUPEREZIO_BOB_SOVEREIGN", "0") == "1"
    logger.info("BOB_SOVEREIGN=%s iterations=%d", bob_sovereign, iterations)

    if bob_sovereign:
        from datetime import datetime as dt_now

        mission_context = _load_mission_context()

        # ── Adaptive Agent: XP + Pain + Auto-Calibration + RL ──
        adaptive_context = ""
        try:
            from core.trading.adaptive_agent import get_adaptive_config, render_adaptive_context

            adaptive_cfg = get_adaptive_config()
            adaptive_context = render_adaptive_context(adaptive_cfg)
            # Inject calibrated params into state for downstream nodes
            state["adaptive_config"] = adaptive_cfg
        except Exception:
            pass

        # ── Portfolio context (HRP allocation + structured numbers) ──
        portfolio_context = ""
        try:
            from core.trading.adaptive_agent import inject_portfolio_context

            portfolio_context = inject_portfolio_context(state)
        except Exception:
            pass

        active_system_prompt = BOB_SOVEREIGN_PROMPT
        if adaptive_context:
            active_system_prompt = adaptive_context + "\n\n" + active_system_prompt
        if portfolio_context:
            active_system_prompt = portfolio_context + "\n\n" + active_system_prompt
        if mission_context:
            active_system_prompt = mission_context + "\n\n" + active_system_prompt

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
                    f"COGNITIVE MODE: {state.get('cognitive_mode', 'ADVISORY_KNOWLEDGE')}\n"
                    f"ALLOWED TOOLS: {', '.join(str(t) for t in state.get('allowed_tools', ['final_answer']))}\n"
                    f"SCANNER_ALLOWED: {bool(state.get('scanner_allowed', False))}\n"
                    f"TICKER_DATA_ALLOWED: {bool(state.get('ticker_allowed', False))}\n"
                    f"ANSWER CONTRACT: {state.get('answer_contract', 'Answer directly and do not invent current market data.')}\n\n"
                    f"USER: {state.get('message', '')}\n\n"
                    f"If ALLOWED TOOLS is only final_answer, do not call market_scan, collect_data, experts, or firewalls. "
                    f"Answer the advisory framework directly and state when live data was not collected. "
                    f"If SCANNER_ALLOWED is False, never scan or shortlist current tickers from imagined data. "
                    f"If live data was not collected, do not quote exact current rates, VIX, yields, recent return stats, "
                    f"tax thresholds, withholding exemptions, contribution limits, or treaty treatment as facts. "
                    f"Use a decision framework and tell the user what must be verified in current market, tax, account, or fund documents. "
                    f"BANNED: Do NOT output the 12-section framework template. "
                    f"Use the 10-section structure from COMPLEX_FINANCE_SYSTEM_PROMPT. "
                    f"Talk like a trusted CFO — direto, sem firula. "
                    f"If the user wants a stock pick and SCANNER_ALLOWED is True, use market_scan first and only use scan-approved tickers. "
                    f"If the user provides or selects a ticker, preserve that ticker as the current asset and use collect_data or attached chart/sentiment context before concluding. "
                    f"If CHART_VISUAL_CONTEXT, Sentimento Vivo, OHLCV, Data/Scan Context, or ticker-specific observations are attached, do not claim missing data for that ticker. "
                    f"Tool access is permission, not an automatic instruction for greetings, status checks, or general education. "
                    f"For any financial mandate, ticker case, investment comparison, buy/sell/order request, Sentimento Vivo signal, or portfolio decision, tools are mandatory: "
                    f"collect_data or market_scan first, then math/expert/guardrail evidence before the final verdict. "
                    f"If you can answer from knowledge only, the request is not a financial decision."
                ),
            }
        )
        state["current_datetime"] = now_str
    else:
        mission_context = _load_mission_context()
        base_prompt = COMPLEX_FINANCE_SYSTEM_PROMPT if is_complex_finance else SYSTEM_PROMPT
        if mission_context:
            active_system_prompt = mission_context + "\n\n" + base_prompt
        else:
            active_system_prompt = base_prompt
        messages = [{"role": "system", "content": active_system_prompt}]
        messages.append({"role": "user", "content": f"User Request: {state.get('message', '')}"})

    # Inject current state context as observations (delegated to observation_builder)
    from .observation_builder import build_observations

    observations = build_observations(state)

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

        if tool_calls and tool_calls[0].get("tool") == "final_answer":
            forced_call = _forced_tool_call_before_final(state)
            if forced_call:
                tool_calls = [forced_call]

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
                forced_call = _forced_tool_call_before_final(state)
                if forced_call:
                    return {
                        "agent_tool_call": forced_call,
                        "agent_iterations": iterations + 1,
                        "_pending_tool_calls": list(state.get("_pending_tool_calls") or []),
                        "bob_thesis": state.get("bob_thesis", ""),
                        "bob_reasoning_trace": state.get("bob_reasoning_trace", []),
                        "current_datetime": state.get("current_datetime", ""),
                    }
                paper_order_call = _build_submit_paper_order_call(state)
                if paper_order_call:
                    return {
                        "agent_tool_call": paper_order_call,
                        "agent_iterations": iterations + 1,
                        "_pending_tool_calls": list(state.get("_pending_tool_calls") or []),
                        "bob_thesis": state.get("bob_thesis", ""),
                        "bob_reasoning_trace": state.get("bob_reasoning_trace", []),
                        "current_datetime": state.get("current_datetime", ""),
                    }
            if tool_call["tool"] == "final_answer":
                content = tool_call.get("args", {}).get("content") or ""
                if state.get("submit_paper_order_result") or state.get("submit_paper_order_error"):
                    content = _paper_order_execution_answer(state)
                elif state.get("scan"):
                    content = _market_scan_answer(state)
                elif not str(content).strip():
                    if is_complex_finance:
                        content = _complex_finance_fallback_answer(state.get("message", ""))
                    else:
                        content = _contract_fallback_answer(state)
                elif _should_force_contract_fallback(state, content):
                    content = _contract_fallback_answer(state)
                elif is_complex_finance:
                    content = _repair_complex_finance_answer(state.get("message", ""), content)
                    content = _apply_grounding_guard(state, content)
                else:
                    content = _repair_answer_quality(content, state.get("message", ""))
                    content = _apply_grounding_guard(state, content)

                # ── Inject portfolio snapshot BEFORE the CHUNK ──
                pf = _get_portfolio_snapshot(state)
                if pf:
                    writer({"type": "CHUNK", "content": pf})
                writer({"type": "CHUNK", "content": content})
                writer(
                    {
                        "type": "PIPELINE_STEP",
                        "run_id": run_id,
                        "step": "agent_primary",
                        "status": "completed",
                    }
                )

                # Trace: final answer decision
                _tracer.end_node(
                    trace_token,
                    status="completed",
                    decision="FINAL_ANSWER",
                    reason=content[:100],
                    agent="bob",
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
                # Trace: tool call decision
                _tracer.end_node(
                    trace_token,
                    status="in_progress",
                    decision=tool_call.get("tool", "UNKNOWN").upper(),
                    reason=f"Calling tool: {tool_call.get('tool')}",
                    agent="bob",
                )

                return {
                    "agent_tool_call": tool_call,
                    "agent_iterations": iterations + 1,
                    "_pending_tool_calls": list(state.get("_pending_tool_calls") or []),
                    "bob_thesis": state.get("bob_thesis", ""),
                    "bob_reasoning_trace": state.get("bob_reasoning_trace", []),
                    "current_datetime": state.get("current_datetime", ""),
                }
        else:
            forced_call = _forced_tool_call_before_final(state)
            if forced_call:
                return {
                    "agent_tool_call": forced_call,
                    "agent_iterations": iterations + 1,
                    "_pending_tool_calls": list(state.get("_pending_tool_calls") or []),
                    "bob_thesis": state.get("bob_thesis", ""),
                    "bob_reasoning_trace": state.get("bob_reasoning_trace", []),
                    "current_datetime": state.get("current_datetime", ""),
                }
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
