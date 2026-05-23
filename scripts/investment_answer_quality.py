"""Shared QA contract for Bob investment answers.

This lives under scripts/ so product runtime does not depend on the test harness.
"""

from __future__ import annotations

import re
from typing import Any


BAD_FALLBACK_MARKERS = (
    "could not finalize",
    "couldn't decide on a tool",
    "request might be malformed",
    "bob failed to produce",
    "bob could not produce",
    "bob could not execute",
    "blocked tool",
    "tool was already used",
    "bloqueei a ferramenta",
    "ja foi usada nesta rodada",
)

FAKE_TICKERS = ("VOOE", "SPYY", "VTII", "VXUSS", "BNDD", "SLVV", "QQQE")

OVERLAP_GROUPS = (
    ("SPY", "VTI", "VOO", "IVV"),
    ("QQQ", "QQQM"),
    ("VXUS", "VEU"),
)

COMPARISON_WORDS = ("compare", "comparison", "versus", " vs ", "difference between")


def _mentions_ticker(text: str, ticker: str) -> bool:
    return bool(re.search(rf"\b{re.escape(ticker)}\b", text or "", re.IGNORECASE))


def _is_comparison_question(question: str) -> bool:
    q = f" {(question or '').lower()} "
    return any(word in q for word in COMPARISON_WORDS)


def _contains_allocation_percentages(answer: str) -> bool:
    return bool(re.search(r"\b\d{1,3}\s*%", answer or ""))


def evaluate_answer_quality(
    question: str,
    answer: str,
    *,
    min_chars: int = 120,
) -> dict[str, Any]:
    """Return ok/reasons for a streamed Bob answer."""
    reasons: list[str] = []
    clean_answer = answer or ""
    lower = clean_answer.lower()

    if len(clean_answer.strip()) < min_chars:
        reasons.append("answer_too_short")

    for marker in BAD_FALLBACK_MARKERS:
        if marker in lower:
            reasons.append(f"bad_fallback_text:{marker}")

    for ticker in FAKE_TICKERS:
        if _mentions_ticker(clean_answer, ticker):
            reasons.append(f"fake_ticker:{ticker}")

    if _contains_allocation_percentages(clean_answer) and not _is_comparison_question(question):
        for group in OVERLAP_GROUPS:
            present = [ticker for ticker in group if _mentions_ticker(clean_answer, ticker)]
            if len(present) > 1:
                reasons.append(f"etf_overlap:{'/'.join(present)}")

    return {"ok": not reasons, "reasons": reasons}
