"""Orchestrator node — passthrough puro, sem classificacao."""

from __future__ import annotations


from langgraph.config import get_stream_writer

# Legacy constants — referenced by contract tests
ALLOWED_ROUTES = {"general", "ticker_analysis", "market_scan", "needs_scope"}
ALLOWED_INTENTS = {
    "general_question", "explain_capabilities", "ticker_analysis",
    "market_scan", "missing_required_slot", "unsafe_unspecified_recommendation",
    "capital_allocation", "personal_finance",
}


async def node_orchestrator(state: dict, *, gateway=None, config=None) -> dict:
    """Passthrough puro — sem classificacao, sem regex, sem rotas.

    O Bob de 80B recebe a mensagem crua e decide TUDO:
    qual ticker, quais tools, qual acao.

    A esteira e: usuario -> Bob -> tools -> Bob -> tools -> ... -> resposta.
    """
    writer = get_stream_writer()
    run_id = state.get("run_id", "")
    message = state.get("message", "")

    writer({
        "type": "PIPELINE_STEP",
        "run_id": run_id,
        "step": "orchestrator_primary",
        "status": "started",
    })

    # ── Plano unico: FULL_ACCESS, Bob decide tudo ──
    plan = {
        "run_id": run_id,
        "session_id": state.get("session_id", ""),
        "message": message,
        "context": state.get("context", ""),
        "rigor": state.get("rigor", "strict"),

        # Rota unica — sem desvios
        "route": "agent",
        "intent": "bob_decides",
        "action": "analyze_and_execute",
        "ticker": "",
        "filters": {},

        # Contrato FULL_ACCESS
        "cognitive_mode": "FULL_ACCESS",
        "allowed_tools": [
            "market_scan", "collect_data", "f51_firewall", "pennylab",
            "run_experts", "neural_decision", "sdca_firewall",
            "rag_forensics", "bob_search", "submit_paper_order", "final_answer",
        ],
        "scanner_allowed": True,
        "ticker_allowed": True,
        "ticket_allowed": True,
        "market_context_allowed": True,
        "answer_contract": (
            "Voce e Bob, CEO da SuperEzio. Acesso TOTAL a todas as ferramentas. "
            "Recebe mensagem crua do usuario. Voce decide o que fazer. "
            "Se o usuario pede compra/venda: analise com tools e emita PAPER_TICKET. "
            "Se pede scan: chame market_scan. Se pede analise: chame collect_data. "
            "Se perguntar sobre IBKR/carteira: responda com dados do sistema. "
            "Fale na lingua do usuario. Seja direto, sem disclaimer. "
            "Voce TEM permissao total para executar ordens paper na IBKR."
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
    }

    writer({
        "type": "PIPELINE_STEP",
        "run_id": run_id,
        "step": "orchestrator_primary",
        "status": "completed",
        "route": "agent",
        "intent": "bob_decides",
        "model_status": "passthrough",
    })

    return plan


# ── Legacy stubs (contract tests reference these) ──

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
        message, re.IGNORECASE,
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
