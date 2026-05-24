"""Expert nodes — fan-out execution and result collection via ModelGateway."""

from __future__ import annotations

import asyncio
import os
from collections import deque
from typing import Any

from langgraph.config import get_stream_writer

# Module-level dedup: prevent collect_experts from running twice per run_id
# when both pennylab and f51_verdict paths converge on it.
# Without this, the entire downstream chain (neural → rag → ceo → explanation)
# executes twice, doubling latency.
_COLLECT_SEEN: deque[str] = deque(maxlen=64)


# Expert roles mapped to provider names
EXPERT_PROVIDERS: dict[str, str] = {
    # 4 New experts
    "macro_risk": "deepseek",
    "fundamental_value": "deepseek",
    "momentum_technical": "deepseek",
    "contrarian_opportunity": "deepseek",
    # Compatibility mapping for old roles
    "fundamental": "deepseek",
    "technical": "deepseek",
    "risk": "deepseek",
    "macro": "deepseek",
    "quant": "deepseek",
    "sentiment": "deepseek",
    "reddit": "deepseek",
    "crypto": "deepseek",
    "options": "deepseek",
    "esg": "deepseek",
    "fixed_income": "deepseek",
    "forex": "deepseek",
}

EXPERT_PROMPTS: dict[str, tuple[str, str]] = {
    "macro_risk": (
        "You are SuperEzio's Macro/Risk expert. Analyze macro indicators, rates, volatility (VIX), "
        "currency, market regime (risk-on/risk-off), yield curves, and credit spreads. "
        "Provide a structured, quantitative assessment.",
        "Analyze macro factors and systemic risks for {ticker}.\n\nContext:\n{context}\n",
    ),
    "fundamental_value": (
        "You are SuperEzio's Fundamental & Value expert. Focus on financial statements, valuation metrics (P/E, EV/EBITDA, FCF yield), "
        "debt coverage, revenue/earnings growth, and competitive advantages.",
        "Analyze fundamentals and valuation for {ticker}.\n\nContext:\n{context}\n",
    ),
    "momentum_technical": (
        "You are SuperEzio's Momentum & Technical expert. Focus on trend indicators, moving averages, support/resistance levels, "
        "RSI, ATR, volume patterns, and short-term price momentum.",
        "Analyze price action and technical setup for {ticker}.\n\nContext:\n{context}\n",
    ),
    "contrarian_opportunity": (
        "You are SuperEzio's Contrarian & Opportunity expert. Identify oversold opportunities, extreme market fear, "
        "insider buying, high short interest, market asymmetries, and potential recovery plays.",
        "Analyze contrarian setups and market sentiment for {ticker}.\n\nContext:\n{context}\n",
    ),
}


async def node_expert(state: dict, *, gateway=None) -> dict:
    """Execute a single expert agent via ModelGateway.

    This is the fan-out target (Send). Each instance runs one role.
    """
    writer = get_stream_writer()
    role: str = state["role"]
    ticker: str = state["ticker"]
    context: str = state.get("data_context", "")
    provider_name: str = EXPERT_PROVIDERS.get(role, "deepseek")

    if gateway is None:
        writer(
            {
                "type": "EXPERT_SKIPPED",
                "role": role,
                "provider": provider_name,
                "reason": "gateway_unavailable",
            }
        )
        return {
            "expert_results": [
                {
                    "role": role,
                    "ok": False,
                    "error": "gateway_unavailable",
                    "provider": provider_name,
                }
            ]
        }

    writer(
        {
            "type": "EXPERT_STARTED",
            "role": role,
            "provider": provider_name,
        }
    )

    timeout = int(os.getenv("SUPEREZIO_EXPERT_TIMEOUT", "60"))

    try:
        prompts = EXPERT_PROMPTS.get(
            role,
            (
                f"You are SuperEzio's {role} expert. Provide concise, data-driven analysis in English. Be quantitative.",
                f"Analyze {ticker} as a {role} expert.\n\nContext:\n{context[:3000]}\n\nProvide a structured assessment with key metrics and risk flags.",
            ),
        )
        system_prompt, user_prompt_template = prompts
        user_prompt = user_prompt_template.format(ticker=ticker, context=context[:3000])

        response = await asyncio.wait_for(
            gateway.chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                preferred_provider=provider_name,
                temperature=0.2,
                max_tokens=600,
            ),
            timeout=timeout,
        )

        response_text = str(response)
        writer(
            {
                "type": "EXPERT_DONE",
                "role": role,
                "ok": True,
                "provider": provider_name,
                "response": response_text,
            }
        )
        return {
            "expert_results": [
                {
                    "role": role,
                    "ok": True,
                    "response": response_text,
                    "provider": provider_name,
                }
            ]
        }

    except Exception as exc:
        writer(
            {
                "type": "EXPERT_DONE",
                "role": role,
                "ok": False,
                "provider": provider_name,
                "error": str(exc)[:200],
            }
        )
        return {
            "expert_results": [
                {
                    "role": role,
                    "ok": False,
                    "error": str(exc)[:200],
                    "provider": provider_name,
                }
            ]
        }


async def node_collect_experts(state: dict) -> dict:
    """Aggregate results from all expert fan-out executions."""
    writer = get_stream_writer()
    run_id = state.get("run_id", "")

    # Dedup guard: this node has 2+ incoming paths (pennylab + f51→experts).
    # LangGraph may trigger it once per converging branch. The first execution
    # writes expert_summary; subsequent triggers must be no-ops, otherwise the
    # entire downstream chain (neural_decision → rag → ceo → explanation) runs twice.
    dedup_key = f"experts_{run_id}"
    if dedup_key in _COLLECT_SEEN:
        writer(
            {
                "type": "PIPELINE_STEP",
                "run_id": run_id,
                "step": "experts",
                "status": "skipped_duplicate",
            }
        )
        return {}
    _COLLECT_SEEN.append(dedup_key)

    results_list: list[dict[str, Any]] = state.get("expert_results") or []

    if not results_list:
        data = state.get("data") or {}
        if state.get("route") == "ticker_analysis" and data.get("data_quality") == "partial":
            summary = (
                "Experts were expected for partial DataCollector evidence, "
                "but no expert result was produced."
            )
            writer(
                {
                    "type": "PIPELINE_STEP",
                    "run_id": run_id,
                    "step": "experts",
                    "status": "error",
                    "reason": "partial_data_without_expert_results",
                }
            )
            return {
                "expert_summary": summary,
                "errors": state.get("errors", []) + ["partial_data_without_expert_results"],
            }

        summary = "Experts were not triggered for this route."
        writer(
            {
                "type": "PIPELINE_STEP",
                "run_id": run_id,
                "step": "experts",
                "status": "skipped",
            }
        )
        return {"expert_summary": summary}

    # Build results dict by role
    results: dict[str, Any] = {}
    for i, r in enumerate(results_list):
        key = r.get("role", str(i))
        results[key] = r

    ok_count = sum(1 for r in results.values() if r.get("ok"))
    fail_count = len(results) - ok_count

    # Build summary
    lines = ["=== EXPERTS ==="]
    for role, r in results.items():
        ok = "ok" if r.get("ok") else "fail"
        resp = str(r.get("response", "")).replace("\n", " ")
        lines.append(f"[{role}][{ok}] {resp[:900]}")

    failed = [role for role, r in results.items() if not r.get("ok")]
    if failed:
        lines.append("=== FAILED EXPERTS ===")
        for role in failed:
            lines.append(f"[{role}] {results[role].get('error', 'unknown')}")

    summary = "\n".join(lines)

    writer(
        {
            "type": "PIPELINE_STEP",
            "run_id": run_id,
            "step": "experts",
            "status": "completed",
            "completed": ok_count,
            "failed": fail_count,
        }
    )
    return {"expert_summary": summary}
