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

SMALL_CAP_WORDS = ("small cap", "small-cap", "smallcap")

ETF_SEMANTIC_FORBIDDEN = {
    "VTV": {"small_cap": SMALL_CAP_WORDS},
    "VOO": {"small_cap": SMALL_CAP_WORDS},
    "SPY": {"small_cap": SMALL_CAP_WORDS},
    "IVV": {"small_cap": SMALL_CAP_WORDS},
    "VTI": {"small_cap_value": ("small cap value", "small-cap value")},
    "VXUS": {
        "us_large_cap": ("us large cap", "u.s. large cap", "s&p 500", "sp500"),
        "small_cap": SMALL_CAP_WORDS,
    },
    "BND": {
        "equity": ("stock", "equity", "large cap", "small cap", "dividend stock"),
        "reit": ("reit", "real estate"),
    },
    "VNQ": {
        "bond": ("bond", "fixed income", "treasury"),
        "small_cap": SMALL_CAP_WORDS,
    },
}

MUTUAL_FUNDS_MISLABELED_AS_ETFS = ("VWENX",)


def _mentions_ticker(text: str, ticker: str) -> bool:
    return bool(re.search(rf"\b{re.escape(ticker)}\b", text or "", re.IGNORECASE))


def _is_comparison_question(question: str) -> bool:
    q = f" {(question or '').lower()} "
    return any(word in q for word in COMPARISON_WORDS)


def _contains_allocation_percentages(answer: str) -> bool:
    return bool(re.search(r"\b\d{1,3}\s*%", answer or ""))


def _sentences(text: str) -> list[str]:
    return [part.strip().lower() for part in re.split(r"[\n.;,]+", text or "") if part.strip()]


def _semantic_mismatch_reasons(question: str, answer: str) -> list[str]:
    if _is_comparison_question(question) or not _contains_allocation_percentages(answer):
        return []

    reasons: list[str] = []
    for sentence in _sentences(answer):
        if "etf" in sentence:
            for ticker in MUTUAL_FUNDS_MISLABELED_AS_ETFS:
                if _mentions_ticker(sentence, ticker):
                    reasons.append(f"fund_semantic_mismatch:{ticker}:not_etf")

        for ticker, forbidden_categories in ETF_SEMANTIC_FORBIDDEN.items():
            if not _mentions_ticker(sentence, ticker):
                continue
            for category, patterns in forbidden_categories.items():
                if any(pattern in sentence for pattern in patterns):
                    reasons.append(f"etf_semantic_mismatch:{ticker}:{category}")

    return sorted(set(reasons))


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

    reasons.extend(_semantic_mismatch_reasons(question, clean_answer))

    return {"ok": not reasons, "reasons": reasons}
