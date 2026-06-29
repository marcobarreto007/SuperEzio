"""Orchestrator node â€” passthrough puro, sem classificacao."""

from __future__ import annotations


from langgraph.config import get_stream_writer

# Legacy constants â€” referenced by contract tests
ALLOWED_ROUTES = {"agent", "general", "ticker_analysis", "market_scan", "needs_scope"}
ALLOWED_INTENTS = {
    "bob_decides",
    "general_question",
    "explain_capabilities",
    "ticker_analysis",
    "market_scan",
    "missing_required_slot",
    "unsafe_unspecified_recommendation",
    "capital_allocation",
    "personal_finance",
}


async def node_orchestrator(state: dict, *, gateway=None, config=None) -> dict:
    """Passthrough puro â€” sem classificacao, sem regex, sem rotas.

    O Bob Core recebe a mensagem crua e decide TUDO:
    qual ticker, quais tools, qual acao.

    A esteira e: usuario -> Bob -> tools -> Bob -> tools -> ... -> resposta.
    """
    writer = get_stream_writer()
    run_id = state.get("run_id", "")
    message = state.get("message", "")
    incoming_ticker = str(state.get("ticker") or "").strip().upper()

    writer(
        {
            "type": "PIPELINE_STEP",
            "run_id": run_id,
            "step": "orchestrator_primary",
            "status": "started",
        }
    )

    # â”€â”€ CASE: contrato financeiro obrigatorio â”€â”€
    from core.pipeline.case import create_case

    financial_case = create_case(message, ticker=incoming_ticker, run_id=run_id)
    case_state = financial_case.to_state()
    case_context = financial_case.to_context()

    writer(
        {
            "type": "CASE_OPENED",
            "run_id": run_id,
            "case_type": financial_case.case_type.value,
            "ticker": financial_case.ticker,
            "mandate": financial_case.mandate[:120],
            "required_steps": financial_case.required_steps(),
        }
    )

    # â”€â”€ Plano unico: FULL_ACCESS, Bob decide tudo â”€â”€
    plan = {
        "run_id": run_id,
        "session_id": state.get("session_id", ""),
        "message": message,
        "context": state.get("context", ""),
        "rigor": state.get("rigor", "strict"),
        # Rota unica â€” sem desvios
        "route": "agent",
        "intent": "bob_decides",
        "action": "analyze_and_execute",
        "ticker": incoming_ticker,
        "filters": {},
        # Contrato FULL_ACCESS
        "cognitive_mode": "FULL_ACCESS",
        "allowed_tools": [
            "market_scan",
            "collect_data",
            "f51_firewall",
            "pennylab",
            "run_experts",
            "neural_decision",
            "sdca_firewall",
            "rag_forensics",
            "bob_search",
            "submit_paper_order",
            "final_answer",
            "query_expert",
            "call_math_calculator",
            "get_live_financial_data",
            "calculate",
        ],
        "scanner_allowed": True,
        "ticker_allowed": True,
        "ticket_allowed": True,
        "market_context_allowed": True,
        "answer_contract": (
            "Voce e Bob, CEO em treino da SuperEzio. Acesso TOTAL a todas as "
            "ferramentas, sem classificador e sem freio previo. Permissao nao e "
            "ordem: antes de chamar ferramenta, decida o objetivo da mensagem. "
            "Small talk/status/capacidades: responda curto usando SYSTEM STATUS; "
            "nao chame market_scan. Ticker explicito ou ticker vindo da UI/chart: "
            "trate como ativo atual e use collect_data/chart_context/sentimento "
            "antes de concluir. Se CHART_VISUAL_CONTEXT, Sentimento Vivo, OHLCV "
            "ou data_context estiverem anexados, isso e dado valido; nunca diga "
            "sem dados para esse ticker. Pedido de scan/descoberta/penny: chame "
            "market_scan. Pedido de compra/venda/ordem/PAPER_TICKET: primeiro "
            "colete dados, rode experts, guardrails/firewalls e so depois "
            "submit_paper_order com LMT, qty, limit_price e risco/invalidacao. "
            "Se uma licao aprendida contradiz sua tese, mude o comportamento e "
            "explique a mudanca. Fale na lingua do usuario, direto, sem disclaimer."
        ),
        "information_need": "bob_decides_everything",
        "time_horizon": "14 days",
        "risk_tolerance": "moderada",
        "bob_intent": "full_access",
        "intent_source": "passthrough",
        "intent_confidence": 1.0,
        "intent_reasons": ["no_classifier_pure_agent_loop"],
        "required_slots": [],
        "entities": {},
        "errors": [],
        "orchestrator_plan": "Bob decides everything. Full tool access. No restrictions.",
        "orchestrator_model_status": "passthrough_no_classifier",
        "last_tool_result": "",
        # CASE: contrato obrigatorio â€” Bob so decide depois da mesa
        "financial_case": financial_case,
        "case_context": case_context,
        **case_state,
    }

    writer(
        {
            "type": "PIPELINE_STEP",
            "run_id": run_id,
            "step": "orchestrator_primary",
            "status": "completed",
            "route": "agent",
            "intent": "bob_decides",
            "model_status": "passthrough",
        }
    )

    return plan


# â”€â”€ Legacy stubs (contract tests reference these) â”€â”€


def _render_plan(plan: dict) -> str:
    route = plan.get("route", "agent")
    intent = plan.get("intent", "bob_decides")
    ticker = plan.get("ticker") or "sem ticker"
    confidence = plan.get("intent_confidence", 0)
    return f"Rota={route}; intent={intent}; ticker={ticker}; confidence={confidence}; filtros={plan.get('filters', {})}."


def _extract_time_horizon(message: str) -> str:
    import re

    if not message:
        return ""
    match = re.search(
        r"(\d+)\s*(hour|hours|hora|horas|day|days|week|weeks|month|months|ano|anos|semana|semanas|mes|meses|dia|dias)",
        message,
        re.IGNORECASE,
    )
    if not match:
        return ""
    num = int(match.group(1))
    unit = match.group(2).lower()
    if unit in ("hour", "hours", "hora", "horas"):
        return f"{num} hours"
    if unit in ("day", "days", "dia", "dias"):
        return f"{num} days"
    if unit in ("week", "weeks", "semana", "semanas"):
        return f"{num} weeks"
    if unit in ("month", "months", "mes", "meses"):
        return f"{num} months"
    if unit in ("ano", "anos"):
        return f"{num * 12} months"
    return match.group(0)

