"""
Fraud pattern hooks — integration with FraudPatternMatcher
===========================================================
Reuses fraud_patterns from core without duplicating logic.
If the pattern matcher is unavailable, returns an empty list
without crashing the pipeline.

Principle: patterns remember. Python computes. Marco decides.
"""

from __future__ import annotations

from typing import List


def query_fraud_patterns(ticker: str) -> List[str]:
    """
    Query FraudPatternMatcher for known manipulation patterns
    associated with the ticker or sector.

    Returns a list of evidence strings to inject into the PennylabReport.
    Never raises — degrades gracefully.
    """
    try:
        from core.rag.fraud_rag import fraud_patterns  # type: ignore[import]

        results = fraud_patterns.search_patterns(ticker)
        if not results:
            return []
        # Normalize to string list
        evidence = []
        for r in results:
            if isinstance(r, str):
                evidence.append(f"[fraud/pattern] {r}")
            elif isinstance(r, dict):
                desc = r.get("description") or r.get("pattern") or str(r)
                evidence.append(f"[fraud/pattern] {desc}")
        return evidence
    except ImportError:
        return ["[fraud] pattern matcher unavailable in this environment"]
    except Exception as exc:  # noqa: BLE001
        return [f"[fraud] query error: {type(exc).__name__}"]


def enrich_with_rag(ticker: str, existing_evidence: List[str]) -> List[str]:
    """
    Add pattern-matched evidence to the existing list without duplicates.
    Returns a new combined list.
    """
    rag_evidence = query_fraud_patterns(ticker)
    # Avoid duplicates by text comparison
    combined = list(existing_evidence)
    for ev in rag_evidence:
        if ev not in combined:
            combined.append(ev)
    return combined
