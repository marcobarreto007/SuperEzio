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
}


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


def route_after_orchestrator(state: dict) -> str:
    """All routes go through the full pipeline — CEO gets complete context."""
    return "data"


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
    """Classify user intent and determine the pipeline route.

    Uses deterministic parser first, golden dataset second, LLM fallback
    third (if threshold not met).
    """
    writer = get_stream_writer()
    run_id = state.get("run_id", "")
    message = state.get("message", "")
    rigor = state.get("rigor", "strict")
    context = state.get("context", "")
    ticker = state.get("ticker", "")

    writer(
        {
            "type": "PIPELINE_STEP",
            "run_id": run_id,
            "step": "orchestrator_primary",
            "status": "started",
        }
    )

    # 1. Deterministic parse
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

    # 3. CEO model as PRIMARY intent classifier
    #    The CEO model was trained to understand natural language Portuguese
    #    financial requests. Regex is a fast-path safety net, not the authority.
    if gateway is not None and message.strip() and plan.get("intent_source") != "golden":
        try:
            raw = await asyncio.wait_for(
                _ask_intent_classifier(message, plan, context, gateway),
                timeout=float(os.getenv("SUPEREZIO_INTENT_LLM_TIMEOUT", "6")),
            )
            candidate = extract_json_object(raw)
            validated = validate_intent_candidate(message, candidate or {}, fallback=parsed)
            if validated:
                plan = validated.to_plan()
                plan["intent_source"] = "ceo_model"
                plan["fallback_route"] = parsed.route
                plan["fallback_intent"] = parsed.intent
                # Guard: CEO model was trained with needs_scope examples in
                # its dataset. Never let it downgrade a market_scan or
                # ticker_analysis to needs_scope — the deterministic parser
                # is the safety floor for non-blocking routes.
                if plan.get("route") == "needs_scope" and parsed.route in (
                    "market_scan",
                    "ticker_analysis",
                    "general",
                ):
                    plan = parsed.to_plan()
                    plan["intent_source"] = "ceo_model_overridden"
                    plan["ceo_original_route"] = "needs_scope"
                # Guard: complex finance questions must not be routed to
                # market_scan. The deterministic parser is the authority.
                if plan.get("route") == "market_scan" and detect_complex_finance_intent(message):
                    plan = parsed.to_plan()
                    plan["intent_source"] = "ceo_model_overridden_complex_finance"
                    plan["ceo_original_route"] = "market_scan"
                # Guard: trade-order follow-ups must stay on market_scan.
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
            # If CEO model fails, trust deterministic as final authority
            plan["intent_source"] = "deterministic_final"

    # Extract time horizon from user message (e.g. "14 days", "2 weeks", "1 month")
    plan["time_horizon"] = _extract_time_horizon(message) or trade_order_context.get(
        "time_horizon", ""
    )

    # Add meta
    plan["orchestrator_plan"] = _render_plan(plan)
    plan["orchestrator_model_status"] = plan.get("intent_source", "deterministic")

    # Emit events
    if plan.get("ticker"):
        writer({"type": "CHART_DATA", "ticker": plan["ticker"]})

    writer(
        {
            "type": "INTENT_CLASSIFIED",
            "route": plan.get("route"),
            "intent": plan.get("intent"),
            "action": plan.get("action"),
            "confidence": plan.get("intent_confidence"),
            "source": plan.get("intent_source"),
            "ticker": plan.get("ticker", ""),
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
        "unsafe_unspecified_recommendation. "
        "CRITICAL ROUTING RULES: "
        "1. If the user asks for a decision framework, thesis, scenario analysis, "
        "comparison (rental property vs equities), capital allocation strategy, "
        "macro economic thesis, or investment evaluation WITHOUT requesting "
        "specific tickers to scan or list, route to general with intent=general_question. "
        "2. Only use market_scan when the user explicitly asks you to find, scan, "
        "search, list, or shortlist specific tickers or securities. "
        "3. Complex advisory questions about investment strategy, risk frameworks, "
        "asset allocation, or financial planning are general_question, NOT market_scan. "
        "4. Only use needs_scope for truly unanswerable requests (empty, nonsense). "
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
            "intent": "general_question|explain_capabilities|ticker_analysis|market_scan|missing_required_slot|unsafe_unspecified_recommendation",
            "action": "answer|answer_directly|collect_data|scan_market|ask_for_ticker|ask_for_scope",
            "ticker": "exact ticker or empty string",
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
