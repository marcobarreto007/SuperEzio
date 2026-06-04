"""Orchestrator node — intent classification + route decision."""

from __future__ import annotations

import asyncio
import json
import os
import re
from typing import Any

from langgraph.config import get_stream_writer

from ..intents import (
    detect_complex_finance_intent,
    extract_json_object,
    match_golden_intent,
    needs_llm_intent_fallback,
    parse_user_intent,
    validate_intent_candidate,
)

ALLOWED_ROUTES = {"general", "ticker_analysis", "market_scan", "needs_scope"}
ALLOWED_INTENTS = {
    "general_question",
    "explain_capabilities",
    "ticker_analysis",
    "market_scan",
    "missing_required_slot",
    "unsafe_unspecified_recommendation",
    "capital_allocation",
    "personal_finance",
}


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Plan rendering
# ---------------------------------------------------------------------------


def _render_plan(plan: dict[str, Any]) -> str:
    """Render an intent plan as a one-line summary."""
    route = plan.get("route", "general")
    intent = plan.get("intent", "unknown")
    ticker = plan.get("ticker") or "sem ticker"
    confidence = plan.get("intent_confidence", 0)
    return (
        f"Rota={route}; intent={intent}; ticker={ticker}; "
        f"confidence={confidence}; filtros={plan.get('filters', {})}."
    )


def _extract_time_horizon(message: str) -> str:
    """Extract investment time horizon from user message.

    Returns string like '14 days', '2 weeks', '1 month', or '' if not found.
    """
    if not message:
        return ""
    match = re.search(
        r"(\d+)\s*(day|days|week|weeks|month|months|ano|anos|semana|semanas|mes|meses|dia|dias)",
        message,
        re.IGNORECASE,
    )
    if not match:
        return ""
    num = int(match.group(1))
    unit = match.group(2).lower()

    # Normalize to English
    if unit in ("day", "days", "dia", "dias"):
        return f"{num} days"
    if unit in ("week", "weeks", "semana", "semanas"):
        return f"{num} weeks"
    if unit in ("month", "months", "mes", "meses"):
        return f"{num} months"
    if unit in ("ano", "anos"):
        return f"{num * 12} months"
    return match.group(0)


# ---------------------------------------------------------------------------
# Main node
# ---------------------------------------------------------------------------


async def node_orchestrator(state: dict, *, gateway=None, config=None) -> dict:
    """Classify user intent and risk tolerance. Does NOT extract tickers.

    The orchestrator's only job: classify WHAT the user wants and HOW MUCH
    risk they're willing to take. Bob (agent) decides the rest.
    """
    writer = get_stream_writer()
    run_id = state.get("run_id", "")
    message = state.get("message", "")
    rigor = state.get("rigor", "strict")
    context = state.get("context", "")
    ticker = state.get("ticker", "")  # kept for backward compat, not used for routing

    writer(
        {
            "type": "PIPELINE_STEP",
            "run_id": run_id,
            "step": "orchestrator_primary",
            "status": "started",
        }
    )

    is_sovereign = os.getenv("SUPEREZIO_BOB_SOVEREIGN") in ("1", "true", "True")

    if is_sovereign:
        trade_order_context = state.get("trade_order_context") or {}
        parsed = parse_user_intent(
            message,
            rigor=rigor,
            ticker=ticker,
            trade_order_context=trade_order_context,
        )
        plan = parsed.to_plan()
        plan.update(
            {
                "risk_tolerance": _classify_risk_tolerance(message, plan),
                "bob_intent": _classify_bob_intent(message, plan),
                "time_horizon": _extract_time_horizon(message)
                or trade_order_context.get("time_horizon", ""),
                "intent_source": "sovereign_orchestrator",
                "sovereign_mode": True,
            }
        )
        if parsed.route == "needs_scope":
            plan.update(
                {
                    "intent_source": "sovereign_scope_guard",
                    "bob_intent": "missing_scope",
                    "allowed_tools": ["final_answer"],
                    "scanner_allowed": False,
                    "ticker_allowed": False,
                    "market_context_allowed": False,
                }
            )
    else:
        # 1. Deterministic parse — for intent classification only
        trade_order_context = state.get("trade_order_context") or {}
        parsed = parse_user_intent(
            message,
            rigor=rigor,
            ticker=ticker,
            trade_order_context=trade_order_context,
        )
        plan = parsed.to_plan()
        plan["intent_source"] = "deterministic"

        # 2. Golden dataset match
        golden = match_golden_intent(message, rigor=rigor)
        if golden:
            plan = golden.to_plan()
            plan["intent_source"] = "golden"
            plan["fallback_route"] = parsed.route
            plan["intent_confidence"] = max(plan.get("intent_confidence", 0), 0.97)

        # 3. CEO model as intent classifier
        if gateway is not None and message.strip() and plan.get("intent_source") != "golden":
            try:
                raw = await asyncio.wait_for(
                    _ask_intent_classifier(message, plan, context, gateway),
                    timeout=float(os.getenv("SUPEREZIO_INTENT_LLM_TIMEOUT", "6")),
                )
                candidate = extract_json_object(raw)
                ceo_risk_tolerance = ""
                ceo_risk = (candidate or {}).get("risk_tolerance", "").strip().lower()
                if ceo_risk in {"conservadora", "moderada", "alta", "especulativa"}:
                    ceo_risk_tolerance = ceo_risk
                validated = validate_intent_candidate(message, candidate or {}, fallback=parsed)
                if validated:
                    plan = validated.to_plan()
                    plan["intent_source"] = "ceo_model"
                    if ceo_risk_tolerance:
                        plan["ceo_risk_tolerance"] = ceo_risk_tolerance
                    plan["fallback_route"] = parsed.route
                    plan["fallback_intent"] = parsed.intent
                    # Safety: never route complex finance → market_scan
                    if plan.get("route") == "market_scan" and detect_complex_finance_intent(
                        message
                    ):
                        plan = parsed.to_plan()
                        plan["intent_source"] = "ceo_model_overridden_complex_finance"
                        plan["ceo_original_route"] = "market_scan"
                    # Safety: trade follow-ups stay on market_scan
                    if (
                        parsed.intent == "another_trade_recommendation"
                        and plan.get("route") != "market_scan"
                    ):
                        ceo_original = plan.get("route")
                        plan = parsed.to_plan()
                        plan["intent_source"] = "ceo_model_overridden_trade_followup"
                        plan["ceo_original_route"] = ceo_original
            except Exception as exc:
                plan["intent_fallback_error"] = str(exc)[:200]
                plan["intent_source"] = "deterministic_final"

        # ── Extract time horizon ──
        plan["time_horizon"] = _extract_time_horizon(message) or trade_order_context.get(
            "time_horizon", ""
        )

        # ── Classify risk tolerance (CEO model when available, keyword fallback otherwise) ──
        if plan.get("intent_source") == "ceo_model" and "ceo_risk_tolerance" in plan:
            plan["risk_tolerance"] = plan.pop("ceo_risk_tolerance")
        else:
            plan["risk_tolerance"] = _classify_risk_tolerance(message, plan)

        # ── Bob intent (NEW) — cleaned classification for the agent ──
        plan["bob_intent"] = _classify_bob_intent(message, plan)

    # ── Metadata ──
    plan["orchestrator_plan"] = _render_plan(plan)
    plan["orchestrator_model_status"] = plan.get("intent_source", "deterministic")

    # Emit events (no ticker extraction anymore)
    writer(
        {
            "type": "INTENT_CLASSIFIED",
            "route": plan.get("route"),
            "intent": plan.get("intent"),
            "action": plan.get("action"),
            "confidence": plan.get("intent_confidence"),
            "source": plan.get("intent_source"),
            "ticker": plan.get("ticker", ""),
            "risk_tolerance": plan.get("risk_tolerance", "moderada"),
            "required_slots": plan.get("required_slots", []),
            "reasons": plan.get("intent_reasons", []),
        }
    )
    writer(
        {
            "type": "PIPELINE_STEP",
            "run_id": run_id,
            "step": "orchestrator_primary",
            "status": "completed",
            "route": plan.get("route"),
            "intent": plan.get("intent"),
            "ticker": plan.get("ticker", ""),
            "model_status": plan.get("intent_source", "deterministic"),
        }
    )

    return plan


# ── Risk tolerance classifier ──


def _classify_risk_tolerance(message: str, plan: dict) -> str:
    """Classify user's risk tolerance from natural language."""
    msg_lower = message.lower()

    # Especulativa: gambling language, penny stocks, "adrenalina", "aposta"
    speculative_markers = [
        "adrenalina",
        "aposta",
        "apostar",
        "lotto",
        "loteria",
        "cassino",
        "yolo",
        "all in",
        "all-in",
        "arriscar tudo",
        "ficar rico",
        "moeda",
        "lua",
        "moon",
        "100x",
        "1000x",
        "decolar",
        "foguete",
    ]
    if any(m in msg_lower for m in speculative_markers):
        return "especulativa"

    # Alta: short-term, penny, "agressivo", "alto risco"
    high_markers = [
        "penny",
        "small cap",
        "small-cap",
        "microcap",
        "agressivo",
        "alto risco",
        "curto prazo",
        "2 semana",
        "1 semana",
        "day trade",
        "swing trade",
        "alavancado",
        "options",
        "opções",
    ]
    if any(m in msg_lower for m in high_markers):
        return "alta"

    # Conservadora: "seguro", "longo prazo", "dividendo", "aposentadoria"
    conservative_markers = [
        "seguro",
        "segurança",
        "longo prazo",
        "dividendo",
        "dividendos",
        "aposentadoria",
        "conservador",
        "renda fixa",
        "tesouro",
        "cdb",
        "poupança",
        "etf",
        "índice",
        "index",
    ]
    if any(m in msg_lower for m in conservative_markers):
        return "conservadora"

    return "moderada"


def _classify_bob_intent(message: str, plan: dict) -> str:
    """Classify what the user wants in plain language, for Bob to reason about.

    Priority order matters: busca_oportunidade beats alocar_capital when the
    user is asking to FIND something specific.
    """
    msg_lower = message.lower()

    # Buscar/achar/encontrar algo específico beats all else
    if any(
        w in msg_lower
        for w in [
            "acha",
            "achar",
            "encontra",
            "encontrar",
            "recomenda",
            "recomendar",
            "sugestão",
            "indicação",
            "oportunidade",
            "me mostra",
            "me fala",
            "qual",
            "quais",
        ]
    ):
        return "buscar_oportunidade"
    if any(w in msg_lower for w in ["comprar", "investir", "alocar", "aplicar", "por em"]):
        return "alocar_capital"
    if any(w in msg_lower for w in ["analisar", "análise", "o que acha", "vale a pena"]):
        return "analisar_ativo"
    if any(w in msg_lower for w in ["explicar", "o que é", "como funciona", "diferença"]):
        return "pergunta_educacional"
    if any(w in msg_lower for w in ["prever", "previsão", "vai subir", "vai cair", "resultado"]):
        return "previsao"
    return plan.get("intent", "general_question")


# ---------------------------------------------------------------------------
# LLM fallback helpers
# ---------------------------------------------------------------------------


def _should_use_llm(message: str, plan: dict, gateway) -> bool:
    """Decide whether to invoke the LLM intent classifier."""
    if gateway is None:
        return False
    mode = os.getenv("SUPEREZIO_INTENT_LLM_FALLBACK", "auto").lower()
    if mode in {"0", "false", "off", "disabled"}:
        return False
    if mode == "force":
        return True
    threshold = float(os.getenv("SUPEREZIO_INTENT_LLM_THRESHOLD", "0.76"))
    return needs_llm_intent_fallback(message, plan, threshold=threshold)


async def _ask_intent_classifier(message: str, plan: dict, context: str, gateway) -> str:
    """Ask an LLM to classify the user intent. Returns raw JSON string."""
    system_prompt = (
        "You are SuperEzio's intent classifier. Return only one JSON object. "
        "Allowed routes: general, ticker_analysis, market_scan, needs_scope. "
        "Allowed intents: general_question, explain_capabilities, "
        "ticker_analysis, market_scan, missing_required_slot, "
        "unsafe_unspecified_recommendation, capital_allocation, personal_finance. "
        "Allowed risk_tolerance: conservadora, moderada, alta, especulativa.\n"
        "CRITICAL ROUTING RULES:\n"
        "0. If the user is comparing multiple uses of capital (cash vs debt repayment "
        "vs ETF vs stock trade vs business/education), route to general with "
        "intent=capital_allocation or personal_finance. This is NEVER a market_scan.\n"
        "1. If the user asks for a decision framework, thesis, scenario analysis, "
        "comparison (rental property vs equities), capital allocation strategy, "
        "macro economic thesis, or investment evaluation WITHOUT requesting "
        "specific tickers to scan or list, route to general with intent=general_question.\n"
        "2. Only use market_scan when the user explicitly asks you to find, scan, "
        "search, list, or shortlist specific tickers or securities.\n"
        "3. Complex advisory questions about investment strategy, risk frameworks, "
        "asset allocation, or financial planning are general_question, NOT market_scan.\n"
        "4. Only use needs_scope for truly unanswerable requests (empty, nonsense).\n"
        "RISK TOLERANCE RULES:\n"
        "- conservadora: user mentions safety, preservation, retirement, dividends, "
        "low risk, fixed income, treasuries, long term, security.\n"
        "- moderada: user mentions balance, diversification, medium risk, mix of "
        "fixed and variable income, 2-5 year horizon. DEFAULT when unspecified.\n"
        "- alta: user mentions high risk, short term, swing trade, day trade, "
        "small caps, options, leverage, aggressive growth.\n"
        "- especulativa: user mentions gambling language (aposta, loteria, adrenalina), "
        "penny stocks, 10x/100x, crypto all-in, yolo, moon shots.\n"
        "Never invent a ticker. "
        "If no ticker appears in the user message, ticker must be empty and "
        "route cannot be ticker_analysis. "
        "Never extract common language words, prepositions, pronouns, or "
        "conjunctions (e.g. 'me', 'de', 'do', 'da', 'to', 'for', 'the', "
        "'it', 'us') as tickers. "
        "If a word is a normal language word, ticker must be empty."
    )
    prompt = {
        "user_message": message[:2000],
        "context_preview": context[:1000],
        "deterministic_plan": plan,
        "required_json_shape": {
            "route": "general|ticker_analysis|market_scan|needs_scope",
            "intent": "general_question|explain_capabilities|ticker_analysis|market_scan|missing_required_slot|unsafe_unspecified_recommendation|capital_allocation|personal_finance",
            "action": "answer|answer_directly|collect_data|scan_market|ask_for_ticker|ask_for_scope",
            "ticker": "exact ticker or empty string",
            "risk_tolerance": "conservadora|moderada|alta|especulativa",
            "filters": {"country": "optional", "sector": "optional"},
            "required_slots": ["ticker if needed"],
            "confidence": "0.0-0.99",
            "reasons": ["short reason"],
        },
    }
    from ...model_serving.providers import PRIMARY_PROVIDER_NAME

    return await gateway.chat_completion(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
        ],
        preferred_provider=PRIMARY_PROVIDER_NAME,
        json_mode=True,
        temperature=0.0,
        max_tokens=500,
    )
