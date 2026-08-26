"""Trinity deliberation node — GENIE + DEEP bilateral LLM dialogue.

Responsibility: Two LLMs deliberate on a trading decision during the pipeline.
Genie provides quick tactical reads; Deep provides rigorous quantitative
analysis. Consensus/dissent drives the final verdict for Bob.

This module runs real-time LLM-to-LLM dialogue inside the pipeline
execution, as opposed to aggregating pre-computed expert verdicts.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from langgraph.config import get_stream_writer

from core.math.math_hub import MathHub
from core.pipeline.prompts.math_prompt import format_math_context
from core.pipeline.prompts.sentiment_prompt import format_sentiment_context

from .expert_dialogue import ExpertDialogue

NEGATIVE_VERDICTS = {
    "AVOID",
    "BLOCK",
    "MANIPULATED",
    "SUSPICIOUS",
    "OVERVALUED",
    "BEARISH",
    "RISK_OFF",
}
BLOCK_VERDICTS = {"AVOID", "BLOCK", "MANIPULATED"}


def _safe_writer():
    try:
        return get_stream_writer()
    except Exception:
        return lambda _event: None


def _dig(mapping: Mapping[str, Any], *path: str) -> Any:
    current: Any = mapping
    for key in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _number(value: Any) -> float | None:
    if value in (None, "", [], {}):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _confidence_text(value: Any) -> str:
    number = _number(value)
    if number is None:
        return "?"
    return str(int(number)) if number.is_integer() else f"{number:.1f}"


def _round_line(item: Mapping[str, Any]) -> str:
    round_no = item.get("round", "?")
    if not item.get("ok"):
        return f"  Round {round_no}: ERROR - {item.get('error', 'unknown')}"
    verdict = str(item.get("verdict") or "UNKNOWN").upper()
    confidence = _confidence_text(item.get("confidence"))
    reasoning = str(item.get("reasoning") or item.get("response") or "").strip().replace("\n", " ")
    return f'  Round {round_no}: {verdict} ({confidence}) - "{reasoning[:220]}"'


def _dialogue_lines(label: str, verdict: Mapping[str, Any]) -> list[str]:
    history = verdict.get("history") if isinstance(verdict.get("history"), list) else []
    lines = [f"{label}:"]
    if not history:
        lines.append("  skipped")
        return lines
    lines.extend(_round_line(item) for item in history if not item.get("skipped"))
    return lines


def _format_trinity_report(
    *,
    genie: Mapping[str, Any],
    deep: Mapping[str, Any],
    consensus: str,
    bob_decision: str,
    override: str,
) -> str:
    lines = ["=== TRINITY DELIBERATION ===", ""]
    lines.extend(_dialogue_lines("GENIE (sentiment)", genie))
    lines.append("")
    lines.extend(_dialogue_lines("DEEP (fundamental)", deep))
    lines.append("")
    lines.append(f"CONSENSUS: {consensus}")
    lines.append(f"BOB DECISION: {bob_decision}")
    lines.append(f"OVERRIDE: {override}")
    lines.append("")
    lines.append("=== END TRINITY ===")
    return "\n".join(lines)


def _requires_deep_follow_up(math_report: Mapping[str, Any], verdict: Mapping[str, Any]) -> str:
    price = _number(_dig(math_report, "summary", "latest_price"))
    dcf = _number(_dig(math_report, "modules", "dcf_proxy", "values", "dcf_value_per_share"))
    if price is not None and dcf is not None and dcf < price * 0.95:
        gap = (price - dcf) / max(price, 1e-9) * 100
        return (
            f"Bob follow-up: DCF fair value is {gap:.1f}% below market price. "
            "Does this change your final verdict?"
        )
    confidence = _number(verdict.get("confidence"))
    if confidence is not None and confidence < 70:
        return "Bob follow-up: Confidence is below 70. What evidence would change the verdict?"
    return ""


def _requires_genie_follow_up(state: Mapping[str, Any], verdict: Mapping[str, Any]) -> str:
    reddit = _dig(state, "data", "reddit") or {}
    signal = str(_dig(reddit, "signal_label") or "").lower() if isinstance(reddit, Mapping) else ""
    suspicious = (
        _dig(reddit, "suspicious_accounts")
        or _dig(reddit, "suspect_accounts")
        or _dig(reddit, "suspicious_accounts_count")
    )
    if suspicious or any(token in signal for token in ("spike", "suspicious", "manipulated")):
        return (
            "Bob follow-up: Validate whether the Reddit/social spike is organic or coordinated. "
            "Call out duplicate text, new accounts, or pump risk."
        )
    confidence = _number(verdict.get("confidence"))
    if confidence is not None and confidence < 70:
        return "Bob follow-up: Confidence is below 70. Which sentiment source is weakest?"
    return ""


def _consensus_and_decision(
    genie: Mapping[str, Any], deep: Mapping[str, Any]
) -> tuple[str, str, bool]:
    genie_verdict = str(genie.get("verdict") or "UNKNOWN").upper()
    deep_verdict = str(deep.get("verdict") or "UNKNOWN").upper()

    if genie_verdict in BLOCK_VERDICTS and deep_verdict in BLOCK_VERDICTS:
        return "BLOCK unanimous: Genie and Deep both reject the opportunity.", "BLOCK", True
    if genie_verdict in NEGATIVE_VERDICTS and deep_verdict in NEGATIVE_VERDICTS:
        return "Both negative. No divergence.", "WAIT", False
    if genie_verdict == "UNKNOWN" and deep_verdict == "UNKNOWN":
        return "No reliable external expert verdict.", "CONTINUE_WITH_BOB", False
    if genie_verdict == deep_verdict:
        return f"Aligned on {genie_verdict}.", genie_verdict, False
    return f"Divergence: Genie={genie_verdict}, Deep={deep_verdict}.", "BOB_ARBITRATE", False


async def _run_dialogue(
    *,
    gateway,
    role: str,
    provider: str,
    system_prompt: str,
    user_prompt: str,
    follow_up_question: str = "",
    max_rounds: int,
) -> dict[str, Any]:
    dialogue = ExpertDialogue(gateway, max_rounds=max_rounds)
    await dialogue.ask(role, provider, system_prompt, user_prompt)
    verdict = dialogue.get_verdict()
    if follow_up_question and max_rounds > 1:
        await dialogue.follow_up(role, provider, follow_up_question)
        verdict = dialogue.get_verdict()
    return verdict


async def node_trinity(state: dict[str, Any], *, gateway=None) -> dict[str, Any]:
    """
    Run Bob -> Genie/Deep -> Bob follow-up deliberation before final answer.

    Returns trinity_report, trinity_structured, trinity_blocked, math_prompt, and
    sentiment_prompt without executing broker actions.
    """

    writer = _safe_writer()
    run_id = state.get("run_id", "")
    ticker = str(state.get("ticker") or _dig(state, "data", "ticker") or "").upper()

    writer(
        {
            "type": "PIPELINE_STEP",
            "run_id": run_id,
            "step": "trinity",
            "status": "started",
            "ticker": ticker,
        }
    )

    math_report = state.get("math_report") or MathHub().calculate_all(state)
    math_context = format_math_context(math_report)
    sentiment_context = format_sentiment_context({**state, "ticker": ticker})

    if gateway is None or not ticker:
        reason = "gateway_unavailable" if gateway is None else "missing_ticker"
        report = _format_trinity_report(
            genie={"history": []},
            deep={"history": []},
            consensus=f"Trinity skipped: {reason}.",
            bob_decision="CONTINUE_WITH_BOB",
            override="None",
        )
        structured = {"skipped": True, "reason": reason}
        writer(
            {
                "type": "TRINITY_DELIBERATION",
                "run_id": run_id,
                "ticker": ticker,
                "report": report,
                "structured": structured,
                "blocked": False,
                "consensus": f"Trinity skipped: {reason}.",
            }
        )
        writer(
            {
                "type": "PIPELINE_STEP",
                "run_id": run_id,
                "step": "trinity",
                "status": "skipped",
                "reason": reason,
            }
        )
        return {
            "math_prompt": math_context,
            "sentiment_prompt": sentiment_context,
            "trinity_report": report,
            "trinity_structured": structured,
            "trinity_blocked": False,
        }

    max_rounds = int(os.getenv("SUPEREZIO_TRINITY_ROUNDS", "3"))

    deep_system = (
        "You are Deep, SuperEzio's fundamental and math adviser. "
        "Use only the supplied math context. Output raw JSON with verdict, "
        "confidence, reasoning, top_signals, top_risks, and bob_readable."
    )
    deep_user = f"Ticker: {ticker}\n\n{math_context}\n\nGive the fundamental/value verdict for Bob."
    deep_first = ExpertDialogue(gateway, max_rounds=max_rounds)
    await deep_first.ask("fundamental_value", "deepseek", deep_system, deep_user)
    deep_prelim = deep_first.get_verdict()
    deep_follow = _requires_deep_follow_up(math_report, deep_prelim)
    if deep_follow:
        await deep_first.follow_up("fundamental_value", "deepseek", deep_follow)
    deep_verdict = deep_first.get_verdict()

    genie_system = (
        "You are Genie, SuperEzio's sentiment and information-quality adviser. "
        "Use only the supplied sentiment context. Output raw JSON with verdict, "
        "confidence, reasoning, top_signals, top_risks, and bob_readable."
    )
    genie_user = (
        f"Ticker: {ticker}\n\n"
        f"{sentiment_context}\n\n"
        "Give the sentiment/social-forensics verdict for Bob."
    )
    genie_first = ExpertDialogue(gateway, max_rounds=max_rounds)
    await genie_first.ask("sentiment", "gemini", genie_system, genie_user)
    genie_prelim = genie_first.get_verdict()
    genie_follow = _requires_genie_follow_up(state, genie_prelim)
    if genie_follow:
        await genie_first.follow_up("sentiment", "gemini", genie_follow)
    genie_verdict = genie_first.get_verdict()

    consensus, bob_decision, blocked = _consensus_and_decision(genie_verdict, deep_verdict)
    report = _format_trinity_report(
        genie=genie_verdict,
        deep=deep_verdict,
        consensus=consensus,
        bob_decision=(
            f"{bob_decision} ({_confidence_text(deep_verdict.get('confidence'))})"
            if bob_decision not in {"BOB_ARBITRATE", "CONTINUE_WITH_BOB"}
            else bob_decision
        ),
        override="None",
    )
    structured = {
        "ticker": ticker,
        "genie": genie_verdict,
        "deep": deep_verdict,
        "consensus": consensus,
        "bob_decision": bob_decision,
        "blocked": blocked,
    }

    writer(
        {
            "type": "TRINITY_DELIBERATION",
            "run_id": run_id,
            "ticker": ticker,
            "report": report,
            "structured": structured,
            "blocked": blocked,
            "consensus": consensus,
        }
    )
    writer(
        {
            "type": "PIPELINE_STEP",
            "run_id": run_id,
            "step": "trinity",
            "status": "completed",
            "blocked": blocked,
            "consensus": consensus,
        }
    )
    return {
        "math_report": math_report,
        "math_prompt": math_context,
        "sentiment_prompt": sentiment_context,
        "trinity_report": report,
        "trinity_structured": structured,
        "trinity_blocked": blocked,
    }


__all__ = ["node_trinity"]
