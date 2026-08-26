"""Structured security evidence used to validate generated market claims."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class GroundedSecurityClaim:
    ticker: str
    evidence_id: str
    source: str
    as_of: str
    price: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def collect_security_claims(state: Mapping[str, Any]) -> dict[str, GroundedSecurityClaim]:
    """Build one evidence-bound claim per security found in pipeline state."""
    claims: dict[str, GroundedSecurityClaim] = {}

    def add(payload: Mapping[str, Any], fallback_ticker: Any = None) -> None:
        ticker = _ticker(payload.get("ticker") or payload.get("symbol") or fallback_ticker)
        if not ticker:
            return
        source = str(payload.get("provider") or payload.get("source") or "pipeline_state")
        as_of = str(
            payload.get("as_of")
            or payload.get("collected_at")
            or payload.get("timestamp")
            or "unknown"
        )
        price = _positive_float(payload.get("price") or payload.get("latest_price"))
        evidence_id = str(payload.get("evidence_id") or "")
        if not evidence_id:
            material = f"{ticker}|{source}|{as_of}|{price}"
            evidence_id = "security:" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
        claims[ticker] = GroundedSecurityClaim(ticker, evidence_id, source, as_of, price)

    state_ticker = state.get("ticker")
    if state_ticker:
        add({}, state_ticker)

    data = state.get("data") or {}
    if isinstance(data, Mapping):
        price_payload = data.get("price")
        if isinstance(price_payload, Mapping):
            add({**data, **price_payload}, state_ticker)
        else:
            add(data, state_ticker)

    # MathHub report — ticker and latest_price after numerical analysis
    # Only extract if math_report has a real ticker (avoid overwriting existing claims)
    math_report = state.get("math_report") or {}
    mr_ticker = math_report.get("ticker") if isinstance(math_report, Mapping) else None
    if mr_ticker:
        _numbers = math_report.get("numbers") or {}
        _summary = math_report.get("summary") or {}
        mr_price = (_numbers.get("latest_price") if isinstance(_numbers, Mapping) else None) or (
            _summary.get("latest_price") if isinstance(_summary, Mapping) else None
        )
        add(
            {
                "ticker": mr_ticker,
                "price": mr_price,
                "source": "math_hub",
                "as_of": math_report.get("generated_at"),
            },
            state_ticker,
        )

    scan = state.get("scan") or {}
    if isinstance(scan, Mapping):
        for candidate in scan.get("candidates") or []:
            if isinstance(candidate, Mapping):
                add(candidate)
        for entry in scan.get("ranked_candidates") or []:
            if isinstance(entry, Mapping) and isinstance(entry.get("candidate"), Mapping):
                add(entry["candidate"])
    return claims


def mentioned_security_symbols(
    text: str,
    *,
    grounded: set[str],
    exclusions: set[str],
    prose_words: set[str],
) -> set[str]:
    """Extract symbols while allowing a grounded ticker to override prose ambiguity."""
    symbols = {
        _ticker(match.group(0))
        for match in re.finditer(r"\b[A-Z][A-Z0-9]{1,4}(?:\.[A-Z]{1,2})?\b", text or "")
    }
    return {
        symbol
        for symbol in symbols
        if symbol and symbol not in exclusions and (symbol in grounded or symbol not in prose_words)
    }


def mismatched_price_symbols(
    text: str, claims: Mapping[str, GroundedSecurityClaim], *, tolerance: float = 0.02
) -> set[str]:
    """Reject numeric prices that contradict the structured evidence for a ticker."""
    mismatches: set[str] = set()
    for ticker, claim in claims.items():
        if claim.price is None:
            continue
        pattern = rf"\b{re.escape(ticker)}\b[^\n]{{0,40}}?\$\s*([0-9][0-9,]*(?:\.[0-9]+)?)"
        for match in re.finditer(pattern, text or "", flags=re.IGNORECASE):
            cited = float(match.group(1).replace(",", ""))
            if abs(cited - claim.price) / claim.price > tolerance:
                mismatches.add(ticker)
    return mismatches


def _ticker(value: Any) -> str:
    return str(value or "").strip().upper().rstrip(".,:;!?)")


def _positive_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None
