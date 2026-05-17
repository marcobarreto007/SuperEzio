"""Orchestrator node — intent classification + route decision."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from langgraph.config import get_stream_writer

from ..intents import (
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
    """Determine which node to execute next based on intent route."""
    route = state.get("route", "general")
    if route == "needs_scope":
        return "respond_blocked"
    if route in ("ticker_analysis", "market_scan"):
        return "data"
    return "ceo_primary"


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
    parsed = parse_user_intent(message, rigor=rigor, ticker=ticker)
    plan = parsed.to_plan()
    plan["intent_source"] = "deterministic"

    # 2. Golden dataset match
    golden = match_golden_intent(message, rigor=rigor)
    if golden:
        plan = golden.to_plan()
        plan["intent_source"] = "golden"
        plan["fallback_route"] = parsed.route
        plan["intent_confidence"] = max(plan.get("intent_confidence", 0), 0.97)

    # 3. LLM fallback (if needed)
    if plan.get("intent_source") != "golden" and _should_use_llm(
        message, plan, gateway
    ):
        try:
            raw = await asyncio.wait_for(
                _ask_intent_classifier(message, plan, context, gateway),
                timeout=float(os.getenv("SUPEREZIO_INTENT_LLM_TIMEOUT", "4")),
            )
            candidate = extract_json_object(raw)
            validated = validate_intent_candidate(
                message, candidate or {}, fallback=parsed
            )
            if validated:
                plan = validated.to_plan()
                plan["intent_source"] = "llm_fallback"
                plan["fallback_route"] = parsed.route
                plan["fallback_intent"] = parsed.intent
        except Exception as exc:
            plan["intent_fallback_error"] = str(exc)[:200]

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


async def _ask_intent_classifier(
    message: str, plan: dict, context: str, gateway
) -> str:
    """Ask an LLM to classify the user intent. Returns raw JSON string."""
    system_prompt = (
        "You are SuperEzio's intent classifier. Return only one JSON object. "
        "Allowed routes: general, ticker_analysis, market_scan, needs_scope. "
        "Allowed intents: general_question, explain_capabilities, "
        "ticker_analysis, market_scan, missing_required_slot, "
        "unsafe_unspecified_recommendation. Never invent a ticker. "
        "If no ticker appears in the user message, ticker must be empty and "
        "route cannot be ticker_analysis. "
        "Never extract common language words, prepositions, pronouns, or conjunctions "
        "(e.g. 'me', 'de', 'do', 'da', 'to', 'for', 'the', 'it', 'us') as tickers. "
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
