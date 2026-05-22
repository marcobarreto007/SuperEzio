"""Agent node — the core LLM orchestrator using ReAct / Tool Calling."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from langgraph.config import get_stream_writer

from ..intents import detect_complex_finance_intent

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """
You are Bob, the SuperEzio CEO and autonomous financial agent.
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
   
9. final_answer
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
You are Bob, the SuperEzio CEO and autonomous financial agent.
The user is asking a complex financial advisory/strategy question.
You must provide a SERIOUS, QUANTITATIVE decision framework answer, NOT a market scan.
Your answer should feel like a family CFO framework, not a generic financial blog.

Do NOT call market_scan. Do NOT call collect_data. Do NOT look up tickers.
Call final_answer directly with your comprehensive analysis.

You must NOT provide regulated personalized financial advice as a licensed advisor.
But you MUST provide educational frameworks, hypothetical capital allocations under explicit assumptions, scenario analysis, decision gates, missing data checklists, conditional recommendations, and risk warnings.

OVERBLOCKING PROTECTION RULE:
For PERSONAL_FINANCE, CAPITAL_ALLOCATION, ASSET_ALLOCATION, EDUCATION_INVESTMENT, BUSINESS_CAPITAL:
Do not refuse unless the user asks for:
- guaranteed returns
- exact personalized investment orders
- legal/tax filing instructions as a substitute for a professional
- deception, evasion, or fraud

Otherwise, you MUST answer. Your answer MUST follow this exact 12-section structure:

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
Allowed:
"This is an educational framework, not personalized financial advice."
Forbidden:
"I cannot provide a capital allocation plan."
"Please consult a CFP" as the full response.
"I cannot help with this."

Rules:
- Use numbers, thresholds, ranges, formulas, or decision gates whenever possible.
- Avoid fake precision: do not present annualized return ranges as forecasts unless backed by an explicit data/source. Do NOT invent exact expected returns or probabilities unless they are explicitly sourced.
- Label all scenario numbers, returns, and probabilities as illustrative assumptions.
- Ensure portfolio allocations sum to exactly 100%. Every allocation must include why each bucket gets that percentage.
- If required data is missing, state assumptions instead of pretending certainty.
- For Canadian personal finance, mention TFSA/RRSP/RESP/FHSA only when relevant, and explicitly state that tax rules depend on the individual's situation.
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

You must ONLY output a valid JSON object:
{"tool": "final_answer", "args": {"content": "your full analysis here"}}
"""


def _parse_tool_call(text: str) -> dict[str, Any] | None:
    try:
        # Extract JSON if there's markdown
        match = re.search(r"\{.*\}", text.strip(), re.DOTALL)
        if match:
            return json.loads(match.group(0))
        return json.loads(text.strip())
    except Exception:
        return None


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


def _top_rejection_reasons(
    summary: dict[str, int], labels: dict[str, str], limit: int = 3
) -> list[str]:
    if not summary:
        return []
    ordered = sorted(summary.items(), key=lambda kv: kv[1], reverse=True)[:limit]
    return [
        f"{labels.get(reason, reason)} — {count}" for reason, count in ordered
    ]


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
    invalid = (
        item.get("invalidation")
        or item.get("invalidation_condition")
        or "—"
    )
    confidence = item.get("confidence") or "research-only"
    return [
        f"- {ticker} ({name})",
        f"  Market: {market}",
        f"  Latest price: {price} {currency}",
        f"  Volume/liquidity: {volume}",
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
    invalid = (
        item.get("invalidation")
        or item.get("invalidation_condition")
        or "—"
    )
    confidence = item.get("confidence") or "pesquisa-apenas"
    return [
        f"- {ticker} ({name})",
        f"  Mercado: {market}",
        f"  Preco atual: {price} {currency}",
        f"  Volume/liquidez: {volume}",
        f"  Razao/catalisador (2 sem.): {catalyst}",
        f"  Risco: {risk}",
        f"  Invalidacao: {invalid}",
        f"  Confianca: {confidence}",
    ]


def _market_scan_answer(state: dict) -> str:
    """Render the gated market scan into a structured 8-section answer.

    The output is bilingual (PT/EN) and never advertises candidates that
    failed the data-quality gate. When zero candidates pass, the answer
    still includes filters, rejection counts, the top rejection reasons,
    and a safer follow-up prompt so the user gets actionable guidance.
    """
    message = state.get("message", "")
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
            "Bob CEO: este e um relatorio de pesquisa de mercado, nao uma "
            "ordem de compra. Lucro nao e garantido."
        )
        sections.append("")
        sections.append("1) Classificacao: pesquisa de oportunidade de curto prazo.")
        sections.append("2) Horizonte: aproximadamente 2 semanas (curto prazo).")
        sections.append(f"3) Universo do scan: {universe}")
        sections.append(
            "4) Gate de qualidade de dados: ticker, exchange, preco atual, "
            "volume/liquidez, catalisador de curto prazo, risco e condicao "
            "de invalidacao sao obrigatorios. Sem todos esses campos, o "
            "candidato e rejeitado."
        )
        sections.append("")
        sections.append("5) Candidatos:")
        if candidates:
            for item in candidates[:6]:
                sections.extend(_format_candidate_block_pt(item))
        else:
            sections.append(
                "Nenhum candidato passou nos gates minimos de qualidade de "
                "dados para uma ideia de pesquisa de 2 semanas."
            )
        sections.append("")
        sections.append(
            f"6) Resumo de rejeicoes: {rejected_count} ticker(s) descartado(s)."
        )
        if top_reasons:
            sections.append("   Principais motivos:")
            for reason in top_reasons:
                sections.append(f"   - {reason}")
        sections.append(
            f"   Filtros usados: paises={filters.get('resolved_countries')}, "
            f"setor={filters.get('sector')}, "
            f"permitir_penny_otc={filters.get('allow_penny_otc')}, "
            f"permitir_microcap={filters.get('allow_microcap')}."
        )
        sections.append("")
        sections.append("7) Controles de risco:")
        sections.append(
            "   - Defina perda maxima por posicao antes de qualquer ordem."
        )
        sections.append(
            "   - Exija liquidez suficiente para entrar e sair sem spread absurdo."
        )
        sections.append(
            "   - Confirme catalisador verificavel (filing, earnings, evento) "
            "e nao hype social."
        )
        sections.append(
            "   - Estabeleca condicao de invalidacao tecnica/fundamentalista clara."
        )
        sections.append("")
        sections.append(
            "8) Aviso: apenas pesquisa. Sem garantia de lucro. Decisao de "
            "compra/venda e sua responsabilidade."
        )
        if not candidates:
            sections.append("")
            sections.append(
                "Proximo prompt sugerido: 'Faca uma checagem ticker-por-ticker "
                "de AAPL, MSFT e SPY com preco, volume, ATR de 14 dias e proximo "
                "evento conhecido.'"
            )
        if errors:
            sections.append("")
            sections.append(
                "Limite de dados: " + "; ".join(str(err) for err in errors[:3])
            )
        return "\n".join(sections)

    sections = []
    sections.append(
        "Bob CEO: this is a market research report, not a buy order. "
        "Profit is not guaranteed."
    )
    sections.append("")
    sections.append("1) Classification: short-term opportunity research.")
    sections.append("2) Time horizon: approximately 2 weeks (short term).")
    sections.append(f"3) Scan universe: {universe}")
    sections.append(
        "4) Data quality gate: ticker, exchange, latest price, "
        "volume/liquidity, short-term catalyst, downside risk and an "
        "invalidation condition are all required. Without every field, "
        "a candidate is rejected."
    )
    sections.append("")
    sections.append("5) Candidates:")
    if candidates:
        for item in candidates[:6]:
            sections.extend(_format_candidate_block_en(item))
    else:
        sections.append(
            "No candidate passed the minimum data-quality gates for a "
            "2-week research idea."
        )
    sections.append("")
    sections.append(
        f"6) Rejected candidates summary: {rejected_count} ticker(s) discarded."
    )
    if top_reasons:
        sections.append("   Top reasons:")
        for reason in top_reasons:
            sections.append(f"   - {reason}")
    sections.append(
        f"   Filters used: countries={filters.get('resolved_countries')}, "
        f"sector={filters.get('sector')}, "
        f"allow_penny_otc={filters.get('allow_penny_otc')}, "
        f"allow_microcap={filters.get('allow_microcap')}."
    )
    sections.append("")
    sections.append("7) Risk controls:")
    sections.append(
        "   - Define maximum loss per position before placing any order."
    )
    sections.append(
        "   - Require liquidity sufficient to enter and exit without "
        "extreme spreads."
    )
    sections.append(
        "   - Confirm a verifiable catalyst (filing, earnings, event) "
        "rather than social hype."
    )
    sections.append(
        "   - Set a clear technical/fundamental invalidation condition."
    )
    sections.append("")
    sections.append(
        "8) Caveat: research only. No guaranteed profit. The buy/sell "
        "decision is your own responsibility."
    )
    if not candidates:
        sections.append("")
        sections.append(
            "Suggested next prompt: 'Run a ticker-by-ticker check on AAPL, "
            "MSFT and SPY with price, volume, 14-day ATR and the next known "
            "event.'"
        )
    if errors:
        sections.append("")
        sections.append("Data limit: " + "; ".join(str(err) for err in errors[:3]))
    return "\n".join(sections)


def _loop_failsafe_answer(state: dict) -> str:
    if state.get("scan"):
        return _market_scan_answer(state)
    if _is_portuguese_request(state.get("message", "")):
        return (
            "Bob CEO: encerrei o ciclo de ferramentas antes de gastar mais tempo. "
            "Ainda posso ajudar, mas preciso reduzir o escopo: mande um ticker, setor, pais ou diga se quer somente uma watchlist de estudo."
        )
    return (
        "Bob CEO: I stopped the tool cycle before wasting more time. "
        "Narrow the scope to a ticker, sector, country, or a study watchlist and I can continue."
    )


def _final_payload(content: str, iterations: int) -> dict[str, Any]:
    return {
        "final": content,
        "agent_tool_call": {"tool": "final_answer", "args": {"content": content}},
        "agent_iterations": iterations + 1,
    }


async def node_agent(state: dict, *, gateway=None, config=None, mandamentos=None) -> dict:
    writer = get_stream_writer()
    run_id = state.get("run_id", "")
    iterations = state.get("agent_iterations", 0)

    if iterations > 7:
        content = _loop_failsafe_answer(state)
        writer({"type": "CHUNK", "content": content})
        return _final_payload(content, iterations)

    if gateway is None:
        return {"errors": state.get("errors", []) + ["no_gateway"]}

    if state.get("route") == "market_scan" and state.get("scan"):
        content = _market_scan_answer(state)
        writer({"type": "CHUNK", "content": content})
        writer(
            {
                "type": "PIPELINE_STEP",
                "run_id": run_id,
                "step": "market_scan_answer",
                "status": "completed",
                "provider": "deterministic_market_scan",
            }
        )
        return _final_payload(content, iterations)

    writer(
        {
            "type": "PIPELINE_STEP",
            "run_id": run_id,
            "step": "ceo_primary",
            "status": "started",
        }
    )

    # Build ReAct Prompt — use complex finance prompt for advisory questions
    is_complex_finance = detect_complex_finance_intent(state.get("message", ""))
    active_system_prompt = COMPLEX_FINANCE_SYSTEM_PROMPT if is_complex_finance else SYSTEM_PROMPT
    messages = [{"role": "system", "content": active_system_prompt}]
    messages.append({"role": "user", "content": f"User Request: {state.get('message', '')}"})

    # Inject current state context as observations
    observations = []
    if state.get("ticker"):
        observations.append(f"Current Ticker: {state.get('ticker')}")
    if state.get("data_context"):
        observations.append(f"Data Collected:\n{state.get('data_context')[:1500]}")
    if state.get("f51_verdict"):
        observations.append(f"F51 Verdict:\n{json.dumps(state.get('f51_verdict'))}")
    if state.get("expert_summary"):
        observations.append(f"Expert Committee:\n{state.get('expert_summary')}")
    if state.get("neural_decision"):
        observations.append(f"Neural Decision:\n{json.dumps(state.get('neural_decision'))}")
    if state.get("sdca_firewall"):
        observations.append(f"SDCA Firewall:\n{json.dumps(state.get('sdca_firewall'))}")
    if state.get("pennylab_result") or state.get("pennylab"):
        observations.append(
            f"PennyLab:\n{json.dumps(state.get('pennylab_result') or state.get('pennylab'))}"
        )
    if state.get("scan"):
        observations.append(
            f"Market Scan Results:\n{json.dumps(state.get('scan').get('candidates', []))}"
        )

    if observations:
        messages.append(
            {"role": "user", "content": "Observations so far:\n" + "\n\n".join(observations)}
        )

    if is_complex_finance:
        messages.append(
            {
                "role": "user",
                "content": (
                    "This is a complex finance question. You MUST call the 'final_answer' tool "
                    "in this turn, and you MUST provide your complete, detailed 12-section analysis "
                    "directly inside the 'content' argument of that tool call. Do not summarize, "
                    "do not defer the analysis, and do not call other tools."
                ),
            }
        )
    else:
        messages.append(
            {
                "role": "user",
                "content": "What is the next tool you want to call? Remember to output ONLY JSON.",
            }
        )

    try:
        from ...model_serving.providers import CEO_PROVIDER_NAME

        raw = await gateway.chat_completion(
            messages=messages,
            temperature=0.1,
            max_tokens=3072 if is_complex_finance else 1024,
            preferred_provider=CEO_PROVIDER_NAME,
            json_mode=True,
        )

        # Clean thinking blocks
        if "<think>" in raw:
            raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()

        tool_call = _parse_tool_call(raw)

        if tool_call and "tool" in tool_call:
            if tool_call["tool"] == "final_answer":
                # Final output — never emit a blank bubble if the model returns "".
                content = tool_call.get("args", {}).get("content") or ""
                if not str(content).strip():
                    content = (
                        "Bob could not finalize this answer. "
                        "Try a narrower prompt (specific ticker, sector, or timeframe)."
                    )
                writer({"type": "CHUNK", "content": content})
                writer(
                    {
                        "type": "PIPELINE_STEP",
                        "run_id": run_id,
                        "step": "ceo_primary",
                        "status": "completed",
                    }
                )
                return {
                    "final": content,
                    "agent_tool_call": tool_call,
                    "agent_iterations": iterations + 1,
                }
            else:
                return {"agent_tool_call": tool_call, "agent_iterations": iterations + 1}
        else:
            # Fallback
            return {
                "agent_tool_call": {
                    "tool": "final_answer",
                    "args": {
                        "content": "I couldn't decide on a tool. The request might be malformed."
                    },
                }
            }

    except Exception as exc:
        logger.error(f"Agent error: {exc}")
        return {
            "agent_tool_call": {
                "tool": "final_answer",
                "args": {"content": f"Internal agent error: {exc}"},
            }
        }
