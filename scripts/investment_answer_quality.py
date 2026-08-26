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


def _asks_dividend_advisory(question: str) -> bool:
    q = (question or "").lower()
    return "dividend" in q or "passive income" in q


def _asks_under_cad_5(question: str) -> bool:
    q = (question or "").lower()
    return "under cad 5" in q or "under $5" in q or "below cad 5" in q


def _asks_dca_macro_advisory(question: str) -> bool:
    q = f" {(question or '').lower()} "
    return any(
        marker in q
        for marker in (
            "dollar-cost",
            " dollar cost ",
            " dca ",
            "wait for a correction",
            "interest rates",
            "market volatility",
        )
    )


def _asks_tax_sensitive_advisory(question: str) -> bool:
    q = (question or "").lower()
    return (
        _asks_dividend_advisory(question)
        or "tax bill" in q
        or "tax efficiency" in q
        or "withholding" in q
    )


def _has_unsupported_macro_precision(answer: str) -> bool:
    lower = (answer or "").lower()
    patterns = (
        r"\bvix\b",
        r"\bbasis[-\s]?point\b",
        r"\btreasury\b.*\b\d+(?:\.\d+)?%",
        r"\brates?\b.{0,40}\b\d+(?:\.\d+)?%",
        r"\byields?\b.{0,40}\b\d+(?:\.\d+)?%",
        r"\boutperformed\b.{0,80}\b\d+(?:\.\d+)?%",
        r"\brecover(?:ed|ing)?\b.{0,80}\b\d+\s*[-–]\s*\d+\s+days\b",
        r"\bq[1-4]\s+20\d{2}\b|\b20\d{2}\s+q[1-4]\b",
        r"\b(?:s&p\s*500|tsx\s+composite)\b.{0,120}\b\d+(?:\.\d+)?%",
        r"\bpullbacks?\b.{0,80}\b\d+(?:\.\d+)?\s*[-–]\s*\d+(?:\.\d+)?%",
    )
    return any(re.search(pattern, lower, flags=re.IGNORECASE) for pattern in patterns)


def _has_tax_overstatement(answer: str) -> bool:
    lower = (answer or "").lower()
    patterns = (
        r"\bcapital gains exemption\b",
        r"\bannual\s+\$?\d+(?:,\d{3})?\s*k?\b.{0,80}\bcapital gains\b",
        r"\bwithout the\s+15%\s+withholding tax\b",
        r"\bavoid(?:s|ed|ing)?\b.{0,80}\b15%\s+(?:u\.?s\.?\s+)?withholding tax\b",
        r"\bdividends are treated as canadian-source income\b",
        r"\brrsps?\s+are\s+exempt\s+from\s+u\.?s\.?\s+withholding tax\b",
        r"\bcanada[-\s]?u\.?s\.?\s+tax treaty\b",
        r"\btreaty benefit\b",
        r"\bcanadian[-\s]?listed\b.{0,80}\b(?:avoid|waive|exempt|no)\b.{0,80}\bwithholding\b",
        r"\bcurrency hedg(?:e|ed|ing)\b.{0,80}\bwithholding\b",
        r"\bwithout currency hedg(?:e|ed|ing)\b.{0,80}\bwithholding\b",
        r"\bcad[-\s]?hedg(?:ed|ing)\b.{0,80}\bwithholding\b",
        r"\btransfer[-\s]?in[-\s]?kind\b",
        r"\b(?:doesn.?t|does not|won.?t|will not)\s+trigger\b.{0,80}\btaxable event\b",
    )
    return any(re.search(pattern, lower, flags=re.IGNORECASE) for pattern in patterns)


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

    scan_leak_markers = (
        "short-term opportunity research",
        "market research report",
        "approximately 2 weeks",
        "run a market_scan",
        "only have collected data",
    )
    if _asks_dividend_advisory(question) and any(marker in lower for marker in scan_leak_markers):
        reasons.append("advisory_scan_leak:dividend")

    if _is_comparison_question(question):
        if any(marker in lower for marker in ("only have collected data", "run a market_scan")):
            reasons.append("comparison_grounding_overblock")
        mentioned = [ticker for ticker in ("VOO", "VTI", "SCHD") if ticker in (question or "")]
        missing = [ticker for ticker in mentioned if not _mentions_ticker(clean_answer, ticker)]
        if missing:
            reasons.append(f"comparison_missing_tickers:{'/'.join(missing)}")

    if _asks_under_cad_5(question):
        for ticker in ("TSLA", "NVDA", "AVGO", "MRVL", "MSFT", "AAPL"):
            if _mentions_ticker(clean_answer, ticker):
                reasons.append(f"price_constraint_leak:{ticker}")
        for match in re.finditer(
            r"\b(?:latest\s+price|trading\s+at|price)\s*[:=]?\s*(?:cad|usd|eur|\$)?\s*(\d+(?:\.\d+)?)\b",
            clean_answer,
            re.IGNORECASE,
        ):
            try:
                price = float(match.group(1))
            except ValueError:
                continue
            if price > 5:
                reasons.append("price_constraint_leak:above_5")
                break

    if _asks_dca_macro_advisory(question) and _has_unsupported_macro_precision(clean_answer):
        reasons.append("unsupported_macro_precision")

    if _asks_tax_sensitive_advisory(question) and _has_tax_overstatement(clean_answer):
        reasons.append("tax_overstatement")

    reasons.extend(_semantic_mismatch_reasons(question, clean_answer))

    return {"ok": not reasons, "reasons": reasons}
