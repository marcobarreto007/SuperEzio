"""Expert nodes — fan-out execution and result collection via ModelGateway."""

from __future__ import annotations

import os
from collections import deque
from typing import Any

from langgraph.config import get_stream_writer

from core.audit.decision_trace import DecisionTraceLogger
from .expert_dialogue import ExpertDialogue

# Module-level dedup: prevent collect_experts from running twice per run_id
# when both pennylab and f51_verdict paths converge on it.
# Without this, the entire downstream chain (neural → rag → ceo → explanation)
# executes twice, doubling latency.
_COLLECT_SEEN: deque[str] = deque(maxlen=64)

# Trace logger singleton
_tracer = DecisionTraceLogger()


# Expert roles mapped to provider names
EXPERT_PROVIDERS: dict[str, str] = {
    # Cloud experts
    "macro_risk": "deepseek",
    "fundamental_value": "deepseek",
    "momentum_technical": "deepseek",
    "contrarian_opportunity": "deepseek",
    # Gemini experts
    "sentiment": "gemini",
    "social_forensics": "gemini",
}

EXPERT_PROMPTS: dict[str, tuple[str, str]] = {
    "macro_risk": (
        "You are SuperEzio's Macro/Risk expert. Output ONLY raw JSON, no markdown, no backticks.\n"
        'Format: {"expert":"macro_risk","ticker":"...","verdict":"RISK_ON|RISK_OFF|CAUTIOUS|NEUTRAL",'
        '"confidence":0-100,"top_signals":["signal1","signal2"],"top_risks":["risk1","risk2"],'
        '"bob_readable":"1 sentence Bob can quote"}',
        "Macro factors for {ticker}.\nContext:\n{context}\n",
    ),
    "fundamental_value": (
        "You are SuperEzio's Fundamental & Value expert. Output ONLY raw JSON, no markdown, no backticks.\n"
        'Format: {"expert":"fundamental_value","ticker":"...","verdict":"UNDERVALUED|FAIR|OVERVALUED|NO_DATA",'
        '"confidence":0-100,"top_signals":["signal1","signal2"],"top_risks":["risk1","risk2"],'
        '"bob_readable":"1 sentence Bob can quote"}',
        "Fundamentals for {ticker}.\nContext:\n{context}\n",
    ),
    "momentum_technical": (
        "You are SuperEzio's Momentum & Technical expert. Output ONLY raw JSON, no markdown, no backticks.\n"
        'Format: {"expert":"momentum_technical","ticker":"...","verdict":"BULLISH|BEARISH|NEUTRAL|OVERSOLD|OVERBOUGHT",'
        '"confidence":0-100,"top_signals":["signal1","signal2"],"top_risks":["risk1","risk2"],'
        '"bob_readable":"1 sentence Bob can quote"}',
        "Technicals for {ticker}.\nContext:\n{context}\n",
    ),
    "contrarian_opportunity": (
        "You are SuperEzio's Contrarian & Opportunity expert. Output ONLY raw JSON, no markdown, no backticks.\n"
        'Format: {"expert":"contrarian","ticker":"...","verdict":"OPPORTUNITY|TRAP|NEUTRAL|NO_EDGE",'
        '"confidence":0-100,"top_signals":["signal1","signal2"],"top_risks":["risk1","risk2"],'
        '"bob_readable":"1 sentence Bob can quote"}',
        "Contrarian view for {ticker}.\nContext:\n{context}\n",
    ),
    "sentiment": (
        "You are SuperEzio's Sentiment expert. Output ONLY raw JSON, no markdown, no backticks.\n"
        'Format: {"expert":"sentiment","ticker":"...","verdict":"BULLISH|BEARISH|NEUTRAL|FEARFUL|EUPHORIC",'
        '"confidence":0-100,"sentiment_score":-1.0-1.0,"top_signals":["signal1","signal2"],'
        '"bob_readable":"1 sentence Bob can quote"}',
        "Sentiment for {ticker}.\nContext:\n{context}\n",
    ),
    "social_forensics": (
        "You are SuperEzio's Social Forensics expert. Output ONLY raw JSON, no markdown, no backticks.\n"
        'Format: {"expert":"social_forensics","ticker":"...","verdict":"MANIPULATED|SUSPICIOUS|CLEAN|INCONCLUSIVE",'
        '"confidence":0-100,"manipulation_score":0-100,'
        '"suspicious_accounts":["name1","name2"],"recommendation":"AVOID|MONITOR|NO_THREAT",'
        '"bob_readable":"1 sentence Bob can quote"}',
        "Social forensics for {ticker}.\nData:\n{context}\n",
    ),
}


async def node_expert(state: dict, *, gateway=None) -> dict:
    """Execute a single expert agent via ModelGateway.

    This is the fan-out target (Send). Each instance runs one role.
    """
    writer = get_stream_writer()
    run_id = state.get("run_id", "")
    role: str = state["role"]
    ticker: str = state["ticker"]
    context: str = state.get("data_context", "")
    provider_name: str = EXPERT_PROVIDERS.get(role, "deepseek")

    # Start trace
    trace_token = _tracer.start_node(
        run_id=run_id,
        node=f"expert.{role}",
        agent=provider_name,
        payload={"ticker": ticker, "role": role},
    )

    if gateway is None:
        writer(
            {
                "type": "EXPERT_SKIPPED",
                "role": role,
                "provider": provider_name,
                "reason": "gateway_unavailable",
            }
        )
        _tracer.end_node(
            trace_token,
            status="skipped",
            decision="SKIP",
            reason="Gateway unavailable",
            agent=provider_name,
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

        dialogue = ExpertDialogue(
            gateway,
            max_rounds=int(os.getenv("SUPEREZIO_EXPERT_DIALOGUE_ROUNDS", "1")),
        )
        round_result = await dialogue.ask(role, provider_name, system_prompt, user_prompt)
        if not round_result.get("ok"):
            raise RuntimeError(round_result.get("error") or "expert_dialogue_failed")

        response_text = str(round_result.get("response") or "")
        writer(
            {
                "type": "EXPERT_DONE",
                "role": role,
                "ok": True,
                "provider": provider_name,
                "response": response_text,
            }
        )

        # End trace
        _tracer.end_node(
            trace_token,
            status="completed",
            decision="COMPLETE",
            reason=response_text[:100],
            agent=provider_name,
        )

        return {
            "expert_results": [
                {
                    "role": role,
                    "ok": True,
                    "response": response_text,
                    "provider": provider_name,
                    "dialogue": dialogue.history,
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

        # End trace with error
        _tracer.error_node(trace_token, exc, payload={"role": role, "provider": provider_name})

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

    # Parse expert JSON responses and build structured summary for Bob
    import json as _json

    parsed: dict[str, dict] = {}
    bob_lines: list[str] = []
    raw_lines: list[str] = []

    for role, r in results.items():
        ok = r.get("ok", False)
        raw = str(r.get("response", ""))
        if not ok or not raw.strip():
            bob_lines.append(f"[{role}] [FAIL] {r.get('error', 'no response')}")
            raw_lines.append(f"[{role}][fail] {raw[:200]}")
            continue

        # Try to parse JSON from expert
        try:
            # Strip markdown code fences and leading/trailing whitespace
            clean = raw.strip()
            # Remove ```json ... ``` blocks
            if clean.startswith("```"):
                lines = clean.split("\n")
                # Remove opening ```json or ```
                if lines and lines[0].startswith("```"):
                    lines = lines[1:]
                # Remove closing ```
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                clean = "\n".join(lines).strip()
            # Remove any "json" prefix some models add
            if clean.lower().startswith("json"):
                clean = clean[4:].strip()
            try:
                json_match = _json.loads(clean)
            except _json.JSONDecodeError:
                start = clean.find("{")
                end = clean.rfind("}")
                if start == -1 or end == -1 or end <= start:
                    raise
                json_match = _json.loads(clean[start : end + 1])
            parsed[role] = json_match

            verdict = json_match.get("verdict", "?")
            confidence = json_match.get("confidence", "?")
            bob_readable = json_match.get("bob_readable", "")
            score = ""
            for score_key in ("sentiment_score", "manipulation_score", "score"):
                if score_key in json_match and json_match[score_key] is not None:
                    score = json_match[score_key]
                    break

            # Build Bob-readable summary line
            score_str = f" score={score}" if score != "" else ""
            bob_lines.append(f"[{role}] -> {verdict} (confidence={confidence}{score_str})")
            if bob_readable:
                bob_lines.append(f"  Bob: {bob_readable}")

            # Extract signals for Bob (new simplified format: top_signals is list of strings)
            signals = json_match.get("top_signals", [])
            for sig in signals[:3]:
                bob_lines.append(f"  - {sig}")

            # Extract risks for Bob
            risks = json_match.get("top_risks", [])
            for risk in risks[:3]:
                bob_lines.append(f"  [RISK] {risk}")

            # Social forensics: suspicious accounts
            accounts = json_match.get("suspicious_accounts", [])
            for acct in accounts[:3]:
                bob_lines.append(f"  [FLAG] {acct}")

            # Recommendation
            rec = json_match.get("recommendation", "")
            if rec:
                bob_lines.append(f"  -> {rec}")

            raw_lines.append(f"[{role}][ok] {bob_readable[:200]}")

        except (_json.JSONDecodeError, ValueError, TypeError):
            # Not valid JSON: use raw text truncated.
            bob_lines.append(f"[{role}] [RAW] not JSON:")
            bob_lines.append(f"  {raw[:300]}")
            raw_lines.append(f"[{role}][ok] {raw[:900]}")

    failed = [role for role, r in results.items() if not r.get("ok")]
    if failed:
        bob_lines.append(f"--- FAILED: {', '.join(failed)}")

    expert_summary = "\n".join(bob_lines)
    raw_summary = "\n".join(raw_lines)  # kept for backward compat in traces

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
    return {
        "expert_summary": expert_summary,
        "expert_raw": raw_summary,
        "expert_structured": parsed,
    }
