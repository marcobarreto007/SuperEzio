"""Finnhub symbol normalization for FinanceDatabase / scan tickers."""

from __future__ import annotations


def finnhub_symbol_variants(symbol: str, market: str | None = None) -> list[str]:
    """Return Finnhub symbol variants to try, most likely first."""
    raw = (symbol or "").strip().upper()
    if not raw:
        return []

    variants: list[str] = [raw]

    # Class shares: FinanceDatabase may use BRK-B while Finnhub expects BRK.B.
    if "-" in raw and "." not in raw:
        variants.append(raw.replace("-", "."))
    if "." in raw and "-" not in raw and not raw.endswith((".TO", ".V", ".CN")):
        variants.append(raw.replace(".", "-"))

    # Canadian listings: try bare symbol and .TO suffix.
    market_l = (market or "").lower()
    if raw.endswith(".TO"):
        base = raw[:-3]
        if base:
            variants.append(base)
    elif raw.endswith(".V"):
        base = raw[:-2]
        if base:
            variants.append(base)
            variants.append(f"{base}.V")
    elif "canada" in market_l:
        variants.append(f"{raw}.TO")

    seen: set[str] = set()
    ordered: list[str] = []
    for item in variants:
        if item and item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered
