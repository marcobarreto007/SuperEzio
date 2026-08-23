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
    from core.pipeline.intents import _is_casual_message, infer_cognitive_contract

    is_casual = _is_casual_message(message)
    incoming_ticker = "" if is_casual else str(state.get("ticker") or "").strip().upper()

    writer(
        {
            "type": "PIPELINE_STEP",
            "run_id": run_id,
            "step": "orchestrator_primary",
            "status": "started",
        }
    )

    # ── CASE: contrato financeiro obrigatorio ──
    from core.pipeline.case import create_case

    financial_case = create_case(message, ticker=incoming_ticker, run_id=run_id)
    case_state = financial_case.to_state()
    case_context = financial_case.to_context()

    cognitive_contract = infer_cognitive_contract(
        message,
        route="agent",
        intent="bob_decides",
        action="answer",
        ticker=incoming_ticker,
    )

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

    # Plano unico com contrato de ferramentas derivado da mensagem.
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
        # Contrato de ferramentas vem do mesmo gate usado pelo parser.
        "cognitive_mode": cognitive_contract["cognitive_mode"],
        "allowed_tools": list(cognitive_contract["allowed_tools"]),
        "scanner_allowed": cognitive_contract["scanner_allowed"],
        "ticker_allowed": cognitive_contract["ticker_allowed"],
        "ticket_allowed": cognitive_contract["ticket_allowed"],
        "market_context_allowed": cognitive_contract["market_context_allowed"],
        "answer_contract": cognitive_contract["answer_contract"],
        "information_need": cognitive_contract["information_need"],
        "time_horizon": "14 days",
        "risk_tolerance": "moderada",
        "bob_intent": cognitive_contract["information_need"],
        "intent_source": "passthrough",
        "intent_confidence": 1.0,
        "intent_reasons": ["no_classifier_pure_agent_loop"],
        "required_slots": [],
        "entities": {},
        "errors": [],
        "orchestrator_plan": "Bob decides within the active cognitive tool contract.",
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
