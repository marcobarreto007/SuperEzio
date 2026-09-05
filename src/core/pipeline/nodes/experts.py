"""Expert nodes — fan-out execution and result collection via ModelGateway."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from collections import deque
from typing import Any

from langgraph.config import get_stream_writer

from core.audit.decision_trace import DecisionTraceLogger
from core.model_serving.providers import get_deepseek_max_tokens
from core.trading.outcome_learning import get_effective_expert_weights

from .expert_dialogue import ExpertDialogue

logger = logging.getLogger(__name__)

# Module-level dedup: prevent collect_experts from running twice per run_id
# when both pennylab and f51_verdict paths converge on it.
# Without this, the entire downstream chain (neural → rag → ceo → explanation)
# executes twice, doubling latency.
_COLLECT_SEEN: deque[str] = deque(maxlen=64)
# Expert cache: on by default since 2026-09-05 with a short TTL. The key
# includes data_context, so a fresh quote naturally breaks the cache; the TTL
# bounds staleness for repeated identical contexts (same ticker, same window).
_EXPERT_CACHE_TTL_S = int(os.getenv("SUPEREZIO_EXPERT_CACHE_TTL", "300"))
_EXPERT_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_EXPERT_CACHE_LOCK = asyncio.Lock()
_RESEARCH_BUDGET_LOCK = asyncio.Lock()
_RESEARCH_TOKENS_SPENT = 0

# Trace logger singleton
_tracer = DecisionTraceLogger()

_POSITIVE_VERDICTS = {
    "RISK_ON",
    "UNDERVALUED",
    "BULLISH",
    "OVERSOLD",
    "OPPORTUNITY",
    "CLEAN",
}
_NEGATIVE_VERDICTS = {
    "RISK_OFF",
    "OVERVALUED",
    "BEARISH",
    "OVERBOUGHT",
    "TRAP",
    "MANIPULATED",
    "SUSPICIOUS",
}

# Every verdict value the analyst prompts can emit (EXPERT_PROMPTS below).
# Used to repair the observed key-swap corruption where the model writes the
# verdict into the "ticker" field (e.g. {"expert":"macro_risk",
# "ticker":"CAUTIOUS","confidence":62}) — measured 2026-08-24.
_KNOWN_VERDICTS = frozenset(
    {
        # macro_risk
        "RISK_ON",
        "RISK_OFF",
        "CAUTIOUS",
        "NEUTRAL",
        "NO_DATA",
        # fundamental_value
        "UNDERVALUED",
        "FAIR",
        "OVERVALUED",
        # momentum_technical
        "BULLISH",
        "BEARISH",
        "OVERSOLD",
        "OVERBOUGHT",
        # contrarian_opportunity
        "OPPORTUNITY",
        "TRAP",
        "NO_EDGE",
        # sentiment
        "FEARFUL",
        "EUPHORIC",
        # social_forensics
        "MANIPULATED",
        "SUSPICIOUS",
        "CLEAN",
        "INCONCLUSIVE",
    }
)


def calculate_weighted_expert_consensus(
    parsed: dict[str, dict], weights: dict[str, float]
) -> dict[str, Any]:
    """Produce a deterministic decision from expert verdicts and learned weights."""
    by_role: dict[str, list[float]] = {}
    for role_key, payload in parsed.items():
        role = role_key.split("#", 1)[0]
        verdict = str(payload.get("verdict") or "").upper()
        polarity = (
            1.0 if verdict in _POSITIVE_VERDICTS else -1.0 if verdict in _NEGATIVE_VERDICTS else 0.0
        )
        try:
            confidence = float(payload.get("confidence", 0.0) or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        if confidence > 1.0:
            confidence /= 100.0
        by_role.setdefault(role, []).append(polarity * max(0.0, min(1.0, confidence)))

    weighted_score = 0.0
    coverage = 0.0
    for role, signals in by_role.items():
        weight = float(weights.get(role, 0.0))
        if weight <= 0 or not signals:
            continue
        weighted_score += weight * (sum(signals) / len(signals))
        coverage += weight

    score = weighted_score / coverage if coverage > 0 else 0.0
    decision = "SUPPORT" if score >= 0.15 else "BLOCK" if score <= -0.15 else "NEUTRAL"
    return {
        "decision": decision,
        "score": round(score, 6),
        "weight_coverage": round(coverage, 6),
    }


def _safe_int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _is_strict_json_enabled() -> bool:
    return os.getenv("SUPEREZIO_EXPERT_STRICT_JSON", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _is_cache_enabled() -> bool:
    return os.getenv("SUPEREZIO_CACHE_LLM_RESPONSES", "1").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _has_valid_json_payload(text: str) -> bool:
    clean = str(text or "").strip()
    if not clean:
        return False
    if clean.startswith("```"):
        lines = clean.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        clean = "\n".join(lines).strip()
    if clean.lower().startswith("json"):
        clean = clean[4:].strip()
    try:
        parsed = json.loads(clean)
    except json.JSONDecodeError:
        start = clean.find("{")
        end = clean.rfind("}")
        if start < 0 or end <= start:
            return False
        try:
            parsed = json.loads(clean[start : end + 1])
        except json.JSONDecodeError:
            return False
    return isinstance(parsed, dict)


def _cache_key(role: str, ticker: str, provider_name: str, context: str) -> str:
    payload = f"{role}|{ticker}|{provider_name}|{context[:6000]}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def _reserve_research_tokens(requested_tokens: int) -> tuple[bool, int, int]:
    """Reserve estimated tokens against SUPEREZIO_RESEARCH_TOKEN_BUDGET.

    Returns (allowed, spent_after, budget).
    """

    global _RESEARCH_TOKENS_SPENT
    budget = _safe_int_env("SUPEREZIO_RESEARCH_TOKEN_BUDGET", 0)
    if budget <= 0:
        return True, _RESEARCH_TOKENS_SPENT, budget

    async with _RESEARCH_BUDGET_LOCK:
        projected = _RESEARCH_TOKENS_SPENT + max(0, int(requested_tokens))
        if projected > budget:
            return False, _RESEARCH_TOKENS_SPENT, budget
        _RESEARCH_TOKENS_SPENT = projected
        return True, _RESEARCH_TOKENS_SPENT, budget


# Expert roles mapped to the provider-pinned external DeepSeek boundary.
EXPERT_ROLES: list[str] = [
    "macro_risk",
    "fundamental_value",
    "momentum_technical",
    "contrarian_opportunity",
    "sentiment",
    "social_forensics",
]

EXPERT_PROVIDERS: dict[str, str] = {
    "macro_risk": "deepseek",
    "fundamental_value": "deepseek",
    "momentum_technical": "deepseek",
    "contrarian_opportunity": "deepseek",
    "sentiment": "deepseek",
    "social_forensics": "deepseek",
}

# Anti-guessing contract appended to every expert system prompt. Modeled on
# TradingAgents' (Xiao et al., arXiv:2412.20138) role-scoped analyst design —
# each analyst is only given the tools/data relevant to its function — and on
# FinRobot's (AI4Finance-Foundation, arXiv:2405.14767) hard separation between
# deterministic financial computation (Python) and LLM narration: the model
# explains and ranks, it never invents a number that isn't in its section.
_ANTI_GUESSING_CONTRACT = (
    "You only see the data section provided below — no other expert's data, "
    "no other expert's verdict. If a field you would need is missing or not "
    "in your section, say so explicitly (NO_DATA) instead of estimating or "
    "inventing a number. Never state a specific price, ratio, or percentage "
    "that is not present in your section."
)

# Roles mapped to the math_report module(s) each one is allowed to see.
# Mirrors TradingAgents' per-analyst tool scoping: the Technical analyst gets
# indicators, not fundamentals; the Sentiment analyst gets sentiment/social
# signals, not technicals. "core" fields (ticker, latest price) are always
# included so every expert can anchor its answer to the same instrument.
EXPERT_CONTEXT_MODULES: dict[str, tuple[str, ...]] = {
    "macro_risk": ("crisis_aggregate", "var_cvar", "drawdown", "portfolio_hrp"),
    "fundamental_value": ("dcf_proxy", "return_metrics", "price_series"),
    "momentum_technical": ("technical_indicators", "price_series", "penny_momentum"),
    "contrarian_opportunity": (
        "technical_indicators",
        "sharpe_sortino",
        "kelly",
        "penny_momentum",
    ),
    # Sentiment and social_forensics deliberately do NOT receive
    # technical_indicators/dcf_proxy — per AIMM (arXiv:2512.16103), social
    # manipulation scoring should be driven by coordination/engagement
    # signals and raw price/volume, not by indicators that could bias the
    # analyst toward rationalizing a technical narrative from social noise.
    "sentiment": ("price_series",),
    "social_forensics": ("price_series", "penny_momentum"),
}

EXPERT_PROMPTS: dict[str, tuple[str, str]] = {
    "macro_risk": (
        "You are SuperEzio's Macro/Risk analyst, modeled on the Risk Manager "
        "role in multi-agent trading frameworks (Xiao et al. 2024, "
        "TradingAgents). Your job is to size systemic and regime risk, not "
        "to pick a direction. Weigh crisis regime, VaR/CVaR, drawdown, and "
        "portfolio concentration. " + _ANTI_GUESSING_CONTRACT + "\n"
        "Output ONLY raw JSON, no markdown, no backticks.\n"
        'Format: {"expert":"macro_risk","ticker":"...","verdict":"RISK_ON|RISK_OFF|CAUTIOUS|NEUTRAL|NO_DATA",'
        '"confidence":0-100,"top_signals":["signal1","signal2"],"top_risks":["risk1","risk2"],'
        '"bob_readable":"1 sentence Bob can quote"}',
        "Macro/risk data for {ticker}.\n{context}\n",
    ),
    "fundamental_value": (
        "You are SuperEzio's Fundamental/Value analyst (Fundamentals Analyst "
        "role, TradingAgents). Judge whether the instrument is priced above "
        "or below a defensible intrinsic-value estimate using ONLY the DCF "
        "proxy and return series given to you — you do not see technical "
        "indicators, this is deliberate so your verdict is not anchored to "
        "chart shape. " + _ANTI_GUESSING_CONTRACT + "\n"
        "Output ONLY raw JSON, no markdown, no backticks.\n"
        'Format: {"expert":"fundamental_value","ticker":"...","verdict":"UNDERVALUED|FAIR|OVERVALUED|NO_DATA",'
        '"confidence":0-100,"top_signals":["signal1","signal2"],"top_risks":["risk1","risk2"],'
        '"bob_readable":"1 sentence Bob can quote"}',
        "Fundamental data for {ticker}.\n{context}\n",
    ),
    "momentum_technical": (
        "You are SuperEzio's Momentum/Technical analyst (Technical Analyst "
        "role, TradingAgents). You see indicators, price series, and the "
        "penny-momentum backtest signal — you do NOT see fundamentals, "
        "macro/crisis data, or sentiment. Judge trend and momentum on chart "
        "evidence alone. " + _ANTI_GUESSING_CONTRACT + "\n"
        "Output ONLY raw JSON, no markdown, no backticks.\n"
        'Format: {"expert":"momentum_technical","ticker":"...","verdict":"BULLISH|BEARISH|NEUTRAL|OVERSOLD|OVERBOUGHT|NO_DATA",'
        '"confidence":0-100,"top_signals":["signal1","signal2"],"top_risks":["risk1","risk2"],'
        '"bob_readable":"1 sentence Bob can quote"}',
        "Technical data for {ticker}.\n{context}\n",
    ),
    "contrarian_opportunity": (
        "You are SuperEzio's Contrarian/Opportunity analyst — modeled on the "
        "Bear Researcher half of the TradingAgents debate stage. Your job is "
        "to actively argue AGAINST the momentum consensus: look for "
        "overextension, risk/reward asymmetry (Kelly, Sharpe/Sortino), and "
        "traps that a trend-following read would miss. You do not see "
        "fundamentals or macro data — argue from price behavior and "
        "risk-adjusted return only. " + _ANTI_GUESSING_CONTRACT + "\n"
        "Output ONLY raw JSON, no markdown, no backticks.\n"
        'Format: {"expert":"contrarian","ticker":"...","verdict":"OPPORTUNITY|TRAP|NEUTRAL|NO_EDGE|NO_DATA",'
        '"confidence":0-100,"top_signals":["signal1","signal2"],"top_risks":["risk1","risk2"],'
        '"bob_readable":"1 sentence Bob can quote"}',
        "Contrarian-relevant data for {ticker}.\n{context}\n",
    ),
    "sentiment": (
        "You are SuperEzio's Sentiment analyst (Sentiment Analyst role, "
        "TradingAgents — reads social/news signal, not chart data). You "
        "receive only price context plus whatever sentiment/news text is "
        "supplied in the message — you do NOT see technical indicators or "
        "the fundamental valuation, so your read is not contaminated by "
        "chart or DCF framing. " + _ANTI_GUESSING_CONTRACT + "\n"
        "Output ONLY raw JSON, no markdown, no backticks.\n"
        'Format: {"expert":"sentiment","ticker":"...","verdict":"BULLISH|BEARISH|NEUTRAL|FEARFUL|EUPHORIC|NO_DATA",'
        '"confidence":0-100,"sentiment_score":-1.0-1.0,"top_signals":["signal1","signal2"],'
        '"bob_readable":"1 sentence Bob can quote"}',
        "Sentiment-relevant data for {ticker}.\n{context}\n",
    ),
    "social_forensics": (
        "You are SuperEzio's Social Forensics analyst, modeled on "
        "manipulation-risk scoring frameworks that fuse coordination/"
        "engagement signals with raw price-volume behavior (AIMM, "
        "arXiv:2512.16103) rather than technical indicators. You look for "
        "pump-and-dump patterns: abnormal volume vs. price-series shape "
        "without a fundamental trigger, and any coordination language "
        "explicitly present in your data. You do NOT see technical "
        "indicators, DCF, or macro data — do not let chart-pattern "
        "reasoning substitute for actual evidence of coordination. "
        + _ANTI_GUESSING_CONTRACT
        + "\n"
        "Output ONLY raw JSON, no markdown, no backticks.\n"
        'Format: {"expert":"social_forensics","ticker":"...","verdict":"MANIPULATED|SUSPICIOUS|CLEAN|INCONCLUSIVE|NO_DATA",'
        '"confidence":0-100,"manipulation_score":0-100,'
        '"suspicious_accounts":["name1","name2"],"recommendation":"AVOID|MONITOR|NO_THREAT",'
        '"bob_readable":"1 sentence Bob can quote"}',
        "Social forensics data for {ticker}.\n{context}\n",
    ),
}

# Judge/auditor roles never see the raw math_report — per TradingAgents'
# Risk Manager stage, they arbitrate the analysts' own verdicts, not the
# underlying market data directly. Populated by _build_judge_context().
_JUDGE_ROLE_PREFIXES = ("judge_agent", "auditor_agent")


def _format_module_section(name: str, module: Any) -> str:
    if not isinstance(module, dict):
        return f"[{name}] unavailable"
    status = module.get("status", "unknown")
    if status != "ok":
        return f"[{name}] {status}: {module.get('reason', 'no data')}"
    values = module.get("values", {})
    parts = ", ".join(f"{k}={v}" for k, v in values.items() if not isinstance(v, (dict, list)))
    return f"[{name}] {parts}" if parts else f"[{name}] ok (no scalar fields)"


def build_role_context(role: str, math_report: dict[str, Any] | None, raw_context: str) -> str:
    """Slice math_report down to the module(s) a given role is allowed to see.

    Falls back to the full raw_context (existing behaviour) for roles not in
    EXPERT_CONTEXT_MODULES (red team, judge, auditor, or unknown roles) —
    those are handled separately by build_judge_context for judge/auditor.
    """
    modules_allowed = EXPERT_CONTEXT_MODULES.get(role)
    if not modules_allowed or not isinstance(math_report, dict):
        return raw_context

    modules = math_report.get("modules", {})
    ticker = math_report.get("ticker", "")
    price = (modules.get("price_series", {}) or {}).get("values", {}).get("latest_price")
    lines = [f"Ticker: {ticker} | Price: {price if price is not None else 'N/A'}"]
    for name in modules_allowed:
        if name in modules:
            lines.append(_format_module_section(name, modules[name]))
    return "\n".join(lines)


def build_judge_context(expert_results: list[dict[str, Any]]) -> str:
    """Summarize expert verdicts for the judge/auditor stage.

    Per TradingAgents' Risk Manager design, the arbitration stage sees the
    analysts' own conclusions (verdict + confidence + top signals/risks),
    not the raw market data again — that keeps the judge's job as
    "arbitrate disagreement", not "re-run the same analysis a 7th time".
    """
    if not expert_results:
        return "No expert verdicts available."
    lines = []
    for r in expert_results:
        if not isinstance(r, dict) or not r.get("ok"):
            continue
        role = r.get("role", "unknown")
        parsed = r.get("parsed") if isinstance(r.get("parsed"), dict) else {}
        verdict = parsed.get("verdict") or r.get("verdict") or "UNKNOWN"
        confidence = parsed.get("confidence") or r.get("confidence")
        signals = parsed.get("top_signals") or []
        risks = parsed.get("top_risks") or []
        lines.append(
            f"- {role} (replica {r.get('replica_id', 1)}): verdict={verdict}, "
            f"confidence={confidence}, signals={signals}, risks={risks}"
        )
    return "\n".join(lines) if lines else "Experts ran but produced no parsable verdicts."


async def node_expert(state: dict, *, gateway=None) -> dict:
    """Execute a single expert agent via ModelGateway.

    This is the fan-out target (Send). Each instance runs one role.
    """
    writer = get_stream_writer()
    run_id = state.get("run_id", "")
    role: str = state["role"]
    ticker: str = state["ticker"]
    replica_id: int = int(state.get("replica_id") or 1)
    raw_context: str = state.get("data_context", "")
    provider_name: str = str(state.get("provider_name") or EXPERT_PROVIDERS.get(role, "deepseek"))
    expert_max_tokens = get_deepseek_max_tokens()

    # Role-scoped context: judge/auditor arbitrate expert verdicts (not raw
    # market data again); analysts with a module allowlist only see their
    # slice of math_report; everything else (red team, unknown roles) keeps
    # the previous full-context behaviour.
    if role.startswith(_JUDGE_ROLE_PREFIXES) or provider_name in {
        "daytrade_judge",
        "daytrade_auditor",
    }:
        context = build_judge_context(state.get("expert_results") or [])
    else:
        context = build_role_context(role, state.get("math_report"), raw_context)

    cache_key = _cache_key(role, ticker, provider_name, context)
    if _is_cache_enabled():
        async with _EXPERT_CACHE_LOCK:
            entry = _EXPERT_CACHE.get(cache_key)
            if entry is not None and time.monotonic() - entry[0] >= _EXPERT_CACHE_TTL_S:
                _EXPERT_CACHE.pop(cache_key, None)
                entry = None
            cached = entry[1] if entry is not None else None
        if cached:
            return {"expert_results": [{**cached, "cached": True, "replica_id": replica_id}]}

    budget_ok, spent_after, budget_total = await _reserve_research_tokens(expert_max_tokens)
    if not budget_ok:
        return {
            "expert_results": [
                {
                    "role": role,
                    "replica_id": replica_id,
                    "ok": False,
                    "error": "research_token_budget_exceeded",
                    "provider": provider_name,
                    "tokens_spent_estimate": spent_after,
                    "tokens_budget": budget_total,
                }
            ]
        }

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
                    "replica_id": replica_id,
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
        role_prompt = EXPERT_PROMPTS.get(role)
        if role_prompt is not None:
            system_prompt, user_prompt_template = role_prompt
            # Templates in EXPERT_PROMPTS use literal {ticker}/{context}
            # placeholders and are safe to .format() here.
            user_prompt = user_prompt_template.format(ticker=ticker, context=context[:3000])
        else:
            # Fallback for roles with no dedicated prompt (red team, and any
            # future unnamed role): built directly via f-string, NOT passed
            # through .format() again. context/math_report text is external,
            # untrusted content that may itself contain literal "{...}"
            # sequences (e.g. dict-repr fragments like "{provider}" copied
            # from another expert's raw output) — re-running .format() over
            # already-interpolated text made str.format() treat that stray
            # "{provider}" as a placeholder and raise KeyError('provider'),
            # which crashed every red_team_agent_N run (see docs/audit).
            system_prompt = (
                f"You are SuperEzio's {role} expert. Provide concise, "
                "data-driven analysis in English. Be quantitative."
            )
            user_prompt = (
                f"Analyze {ticker} as a {role} expert.\n\n"
                f"Context:\n{context[:3000]}\n\n"
                "Provide a structured assessment with key metrics and risk flags."
            )

        dialogue = ExpertDialogue(
            gateway,
            max_rounds=int(os.getenv("SUPEREZIO_EXPERT_DIALOGUE_ROUNDS", "1")),
        )
        round_result = await dialogue.ask(role, provider_name, system_prompt, user_prompt)
        if not round_result.get("ok"):
            raise RuntimeError(round_result.get("error") or "expert_dialogue_failed")

        response_text = str(round_result.get("response") or "")
        if _is_strict_json_enabled() and not _has_valid_json_payload(response_text):
            raise RuntimeError("strict_json_validation_failed")

        writer(
            {
                "type": "EXPERT_DONE",
                "role": role,
                "replica_id": replica_id,
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

        result_payload = {
            "role": role,
            "replica_id": replica_id,
            "ok": True,
            "response": response_text,
            "provider": provider_name,
            "dialogue": dialogue.history,
            "tokens_spent_estimate": spent_after,
            "tokens_budget": budget_total,
        }
        if _is_cache_enabled():
            async with _EXPERT_CACHE_LOCK:
                _EXPERT_CACHE[cache_key] = (time.monotonic(), result_payload)

        return {"expert_results": [result_payload]}

    except Exception as exc:  # noqa: BLE001 — catch amplo deliberado: falha do expert vira payload de erro no stream, não derruba o grafo
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
                    "replica_id": replica_id,
                    "ok": False,
                    "error": str(exc)[:200],
                    "provider": provider_name,
                    "tokens_spent_estimate": spent_after,
                    "tokens_budget": budget_total,
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

    # Build results dict by role (+ replica when present)
    results: dict[str, Any] = {}
    for i, r in enumerate(results_list):
        key = r.get("role", str(i))
        replica = r.get("replica_id")
        if replica not in (None, ""):
            key = f"{key}#r{replica}"
        results[key] = r

    ok_count = sum(1 for r in results.values() if r.get("ok"))
    fail_count = len(results) - ok_count

    # Parse expert JSON responses and build structured summary for Bob
    import json as _json

    parsed: dict[str, dict] = {}
    bob_lines: list[str] = []
    raw_lines: list[str] = []
    expert_weights = get_effective_expert_weights()

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

            # (a) Repair the observed key-swap corruption: the model
            # sometimes writes the verdict into "ticker" and leaves verdict
            # missing or holding the ticker symbol (measured 2026-08-24:
            # {"expert":"macro_risk","ticker":"CAUTIOUS","confidence":62}).
            # Move the enum value back to verdict; ticker is restored from
            # context instead of guessing.
            ticker_field = json_match.get("ticker")
            verdict_field = json_match.get("verdict")
            if (
                str(ticker_field).strip().upper() in _KNOWN_VERDICTS
                and str(verdict_field).strip().upper() not in _KNOWN_VERDICTS
            ):
                json_match["verdict"] = str(ticker_field).strip().upper()
                json_match["ticker"] = (
                    state.get("ticker")
                    or (state.get("data") or {}).get("ticker")
                    or (state.get("math_report") or {}).get("ticker")
                    or ""
                )
                verdict_field = json_match["verdict"]
                logger.warning(
                    "expert_verdict_key_swap_repaired: role=%s verdict=%s",
                    role,
                    verdict_field,
                )

            # (c) Entries with neither a verdict nor a Bob-readable summary
            # carry no content — drop them instead of surfacing a "? 0%"
            # line in the report and a zero-weight phantom in the consensus.
            empty_verdict = (
                not str(verdict_field or "").strip() or str(verdict_field).strip() == "?"
            )
            if empty_verdict and not str(json_match.get("bob_readable") or "").strip():
                logger.warning("expert_json_empty_discarded: role=%s", role)
                bob_lines.append(f"[{role}] [EMPTY] discarded (no verdict, no summary)")
                raw_lines.append(f"[{role}][discarded] {raw[:200]}")
                continue
            parsed[role] = json_match

            verdict = json_match.get("verdict", "?")
            confidence = json_match.get("confidence", "?")
            try:
                normalized_confidence = float(confidence)
                if normalized_confidence > 1.0:
                    normalized_confidence /= 100.0
                r["confidence"] = max(0.0, min(1.0, normalized_confidence))
            except (TypeError, ValueError):
                pass
            bob_readable = json_match.get("bob_readable", "")
            score = ""
            for score_key in ("sentiment_score", "manipulation_score", "score"):
                if score_key in json_match and json_match[score_key] is not None:
                    score = json_match[score_key]
                    break

            # Build Bob-readable summary line
            score_str = f" score={score}" if score != "" else ""
            base_role = role.split("#", 1)[0]
            reliability = expert_weights.get(base_role)
            weight_str = f" reliability={reliability:.3f}" if reliability is not None else ""
            bob_lines.append(
                f"[{role}] -> {verdict} (confidence={confidence}{score_str}{weight_str})"
            )
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

        except (_json.JSONDecodeError, ValueError, TypeError) as exc:
            # (b) Malformed JSON (observed "}": "PAR", "verdict" fragments):
            # the entry is discarded entirely — never stored in
            # expert_structured and never echoed into the summary — the
            # fragment is only logged, so it cannot leak into downstream
            # reports or the consensus.
            logger.warning("expert_json_discarded: role=%s err=%s", role, str(exc)[:200])
            bob_lines.append(f"[{role}] [INVALID_JSON] discarded (malformed response)")
            raw_lines.append(f"[{role}][discarded] {raw[:200]}")

    failed = [role for role, r in results.items() if not r.get("ok")]
    if failed:
        bob_lines.append(f"--- FAILED: {', '.join(failed)}")

    expert_summary = "\n".join(bob_lines)
    raw_summary = "\n".join(raw_lines)  # kept for backward compat in traces
    weighted_consensus = calculate_weighted_expert_consensus(parsed, expert_weights)
    expert_summary += (
        f"\n[WEIGHTED_CONSENSUS] {weighted_consensus['decision']} "
        f"score={weighted_consensus['score']:.3f} "
        f"coverage={weighted_consensus['weight_coverage']:.3f}"
    )

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
        "expert_weights": expert_weights,
        "expert_consensus": weighted_consensus,
    }


def expert_concurrency(role_count: int) -> int:
    """Concurrency for the cloud expert committee (2026-09-05).

    The old concurrency=1 pinned a single local llama-server inference slot;
    experts now run on the DeepSeek API and may fan out. Default is all roles
    in parallel; override with SUPEREZIO_EXPERT_CONCURRENCY (1..role_count).
    """
    raw = os.getenv("SUPEREZIO_EXPERT_CONCURRENCY", "").strip()
    if not raw:
        return max(1, role_count)
    try:
        value = int(raw)
    except ValueError:
        return max(1, role_count)
    return min(max(1, value), max(1, role_count))


async def run_experts_parallel(
    expert_state: dict, roles: list[str], *, gateway=None
) -> list[dict[str, Any]]:
    """Fan-out do comite de experts em paralelo (melhor esforco).

    Um expert que falha vira resultado estruturado de erro — nunca aborta o
    comite. Cada resultado carrega role/provider/replica_id para o collect.
    """
    concurrency = expert_concurrency(len(roles))
    semaphore = asyncio.Semaphore(concurrency)

    async def _run_one(role: str) -> list[dict[str, Any]]:
        async with semaphore:
            try:
                res = await node_expert({**expert_state, "role": role}, gateway=gateway)
                out: list[dict[str, Any]] = []
                for expert_result in res.get("expert_results", []):
                    expert_result.setdefault("role", role)
                    expert_result.setdefault("replica_id", 1)
                    expert_result.setdefault("provider", EXPERT_PROVIDERS.get(role, "unknown"))
                    out.append(expert_result)
                return out
            except Exception as exc:  # noqa: BLE001 — melhor esforco: falha vira erro estruturado
                return [
                    {
                        "role": role,
                        "replica_id": 1,
                        "ok": False,
                        "error": str(exc)[:200],
                        "provider": EXPERT_PROVIDERS.get(role, "?"),
                    }
                ]

    results: list[dict[str, Any]] = []
    for batch in await asyncio.gather(*(_run_one(role) for role in roles)):
        results.extend(batch)
    return results
