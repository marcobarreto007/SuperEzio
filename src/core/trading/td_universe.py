"""TD Direct Investing tradable universe contract (operator decision 2026-08-23).

SuperEzio is specialized to instruments tradable through TD Direct
Investing: listed equities on TSX/TSXV/NYSE/NASDAQ — no OTC/pink sheets —
plus the official commission-free ETF universe (108 symbols, manifest
verified 2026-08-18 in config/td_direct_commission_free_etfs.json).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

# Explicit exclusion markers for non-listed venues. Listing is determined by
# the absence of these markers rather than an exchange allowlist: provider
# exchange codes vary (yfinance "TSE"/"NMS"/"PCX", Finnhub "US"), and a false
# negative on the listing side would silently shrink the tradable universe.
_OTC_MARKERS = ("OTC", "PINK", "PNK", "GREY", "GRAY")

_MANIFEST_PATH = (
    Path(__file__).resolve().parents[3] / "config" / "td_direct_commission_free_etfs.json"
)


@lru_cache(maxsize=1)
def commission_free_universe() -> dict[str, frozenset[str]]:
    """Load the official TD commission-free manifest -> {group: frozenset}."""
    data: dict[str, Any] = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    symbols = data.get("symbols") or {}
    return {
        group: frozenset(str(s).strip().upper() for s in symbols.get(group, []))
        for group in ("CAN", "US")
    }


def is_commission_free(symbol: str) -> bool:
    """True when *symbol* is in the TD commission-free ETF universe."""
    sym = (symbol or "").strip().upper()
    universe = commission_free_universe()
    return sym in universe["CAN"] or sym in universe["US"]


def is_td_tradable_exchange(exchange: str | None) -> bool:
    """True for listed venues; OTC/pink-sheet markers are excluded.

    A missing exchange is NOT tradable (fail closed: an instrument whose
    listing venue is unknown must not enter the TD flow).
    """
    if not exchange:
        return False
    ex = str(exchange).strip().upper()
    return not any(marker in ex for marker in _OTC_MARKERS)


def td_universe_summary() -> dict[str, int]:
    """Size of the commission-free universe by listing group."""
    universe = commission_free_universe()
    return {
        "commission_free_can": len(universe["CAN"]),
        "commission_free_us": len(universe["US"]),
        "commission_free_total": len(universe["CAN"]) + len(universe["US"]),
    }
