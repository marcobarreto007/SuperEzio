"""TD Direct Investing tradable universe contract (operator decision 2026-08-23).

Single source of truth for what SuperEzio may scan, analyze and ticket:
instruments listed on exchanges supported by TD Direct Investing — TSX,
TSXV, NYSE, NASDAQ, NYSE American and NYSE Arca — plus the official
commission-free ETF universe (108 symbols, manifest verified 2026-08-18 in
config/td_direct_commission_free_etfs.json).

Everything else — OTC/pink sheets, CSE (.CN), NEO/Cboe Canada (.NE),
foreign exchanges (LSE, B3/BVMF, ...) — is rejected fail-closed until the
operator confirms official TD support. Previous per-module venue lists
(scanner whitelists, ticket currency map, professional collector) were
drift-prone duplicates; they now derive from this module.

The full per-exchange ticker manifest (config/td_tradable_universe.json,
schema v2, built by scripts/update_td_universe_manifest.py) refines the
gate when fresh: membership vouches for a listing even when the venue
string is missing or generic. When the manifest is stale or absent the
gate degrades to the exchange allowlist only — never to "allow all" —
and the degradation is surfaced via tradable_universe_state().
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

# Explicit exclusion markers for non-listed venues. Kept as a distinct
# concept from the allowlist so OTC gets its own rejection reason
# ("otc_filtered") in the scan gate instead of the generic one.
_OTC_MARKERS = ("OTC", "PINK", "PNK", "GREY", "GRAY", "OCT", "OTCM")

# Canonical TD-supported exchanges and their settlement currency. NYSE
# American (AMEX) and NYSE Arca are required: the commission-free manifest
# includes Arca-listed ETFs (SPY, GLD, SMH, GDX) and AMEX listings.
TD_EXCHANGE_CURRENCY: dict[str, str] = {
    "TSX": "CAD",
    "TSXV": "CAD",
    "NYSE": "USD",
    "NASDAQ": "USD",
    "NYSEAMERICAN": "USD",
    "NYSEARCA": "USD",
}

# Raw provider spellings -> canonical exchange. Covers Yahoo /
# FinanceDatabase codes (TOR/TSV/NYQ/NMS/NGM/NCM/ASE/PCX), Twelve Data
# ISO MIC codes (XTSE/XTSX) and common long spellings (compared with
# spaces/hyphens/dots stripped, uppercased). A generic "US" (Finnhub
# bucket code) is deliberately NOT mapped: it cannot distinguish a listed
# venue from an OTC one, so it fails closed.
_EXCHANGE_ALIASES: dict[str, str] = {
    # canonical spellings
    "TSX": "TSX",
    "TSXV": "TSXV",
    "NYSE": "NYSE",
    "NASDAQ": "NASDAQ",
    "NYSEAMERICAN": "NYSEAMERICAN",
    "NYSEARCA": "NYSEARCA",
    # Yahoo / FinanceDatabase exchange codes
    "TOR": "TSX",
    "TSE": "TSX",
    "TSV": "TSXV",
    "NYQ": "NYSE",
    "NMS": "NASDAQ",
    "NGM": "NASDAQ",
    "NCM": "NASDAQ",
    "ASE": "NYSEAMERICAN",
    "PCX": "NYSEARCA",
    # Twelve Data ISO MIC codes
    "XTSE": "TSX",
    "XTSX": "TSXV",
    # common spellings (separators already stripped by the normalizer)
    "AMEX": "NYSEAMERICAN",
    "NYSEMKT": "NYSEAMERICAN",
    "NYSEALTAM": "NYSEAMERICAN",
    "ARCA": "NYSEARCA",
    "TSXVENTURE": "TSXV",
    "TORONTO": "TSX",
}

_MANIFEST_PATH = (
    Path(__file__).resolve().parents[3] / "config" / "td_direct_commission_free_etfs.json"
)

_TRADABLE_MANIFEST_PATH = (
    Path(__file__).resolve().parents[3] / "config" / "td_tradable_universe.json"
)
_TRADABLE_MANIFEST_TTL_DAYS = 7
_TRADABLE_MANIFEST_SCHEMA_VERSION = 2


def normalize_td_exchange(raw: str | None) -> str | None:
    """Normalize any provider venue spelling to a canonical TD exchange.

    Returns None for unknown/unsupported venues (fail closed): CSE, NEO,
    OTC buckets, generic "US", foreign exchanges.
    """
    if not raw:
        return None
    key = re.sub(r"[\s\-_.]+", "", str(raw)).upper()
    if not key:
        return None
    return _EXCHANGE_ALIASES.get(key)


def has_otc_marker(raw: str | None) -> bool:
    """True when the venue string carries an OTC/pink-sheet marker."""
    if not raw:
        return False
    ex = str(raw).strip().upper()
    return any(marker in ex for marker in _OTC_MARKERS)


def is_td_tradable_exchange(exchange: str | None) -> bool:
    """True only for venues that normalize to a TD-supported exchange.

    Allowlist semantics (operator decision 2026-08-23): a missing or
    unknown venue is NOT tradable (fail closed). An instrument whose
    listing venue is unknown must not enter the TD flow.
    """
    return normalize_td_exchange(exchange) is not None


def td_canonical_exchanges() -> frozenset[str]:
    """Canonical TD-supported exchange names."""
    return frozenset(TD_EXCHANGE_CURRENCY)


def td_exchange_alias_codes(canonicals: Iterable[str] | None = None) -> frozenset[str]:
    """Raw venue spellings (incl. canonical names) accepted for *canonicals*.

    Backs the scanner whitelists so every module compares the same codes.
    """
    wanted = set(canonicals) if canonicals is not None else set(TD_EXCHANGE_CURRENCY)
    return frozenset(code for code, canon in _EXCHANGE_ALIASES.items() if canon in wanted)


def exchange_currency(exchange: str | None) -> str | None:
    """Settlement currency for a venue spelling, or None when unsupported."""
    canon = normalize_td_exchange(exchange)
    return TD_EXCHANGE_CURRENCY.get(canon) if canon else None


# ── Commission-free ETF manifest (curated, operator-verified) ───────────────


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


# ── Full tradable ticker manifest (schema v2, TTL fail-closed) ──────────────


def _load_tradable_manifest() -> dict[str, Any] | None:
    try:
        data = json.loads(_TRADABLE_MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    if data.get("schema_version") != _TRADABLE_MANIFEST_SCHEMA_VERSION:
        return None
    return data


def _manifest_age_days(data: dict[str, Any]) -> float | None:
    generated = str(data.get("generated_at") or "")
    try:
        stamp = datetime.fromisoformat(generated.replace("Z", "+00:00"))
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - stamp).total_seconds() / 86400.0


def tradable_universe_state() -> dict[str, Any]:
    """State of the full ticker manifest: fresh / stale / missing / invalid.

    Degrading to the exchange allowlist when stale is explicit, never
    silent — consumers surface this in summaries and health.
    """
    if not _TRADABLE_MANIFEST_PATH.exists():
        return {"state": "missing"}
    data = _load_tradable_manifest()
    if data is None:
        # Present but unreadable or wrong schema_version — invalid, not missing.
        return {"state": "invalid"}
    age_days = _manifest_age_days(data)
    if age_days is None:
        return {"state": "invalid"}
    ttl_days = data.get("ttl_days") or _TRADABLE_MANIFEST_TTL_DAYS
    try:
        ttl_days = int(ttl_days)
    except (TypeError, ValueError):
        ttl_days = _TRADABLE_MANIFEST_TTL_DAYS
    exchanges = data.get("exchanges") or {}
    counts = {
        str(name): len(entries) for name, entries in exchanges.items() if isinstance(entries, list)
    }
    return {
        "state": "fresh" if age_days <= ttl_days else "stale",
        "generated_at": data.get("generated_at"),
        "age_days": round(age_days, 2),
        "ttl_days": ttl_days,
        "symbol_counts": counts,
        "symbol_total": sum(counts.values()),
    }


@lru_cache(maxsize=1)
def _tradable_symbols_cached() -> frozenset[str] | None:
    """Symbols vouched by a FRESH manifest; None when missing/stale/invalid."""
    if tradable_universe_state().get("state") != "fresh":
        return None
    data = _load_tradable_manifest() or {}
    symbols: set[str] = set()
    for entries in (data.get("exchanges") or {}).values():
        if isinstance(entries, list):
            symbols.update(str(s).strip().upper() for s in entries if s)
    return frozenset(symbols) if symbols else None


def is_td_tradable(symbol: str, exchange: str | None = None) -> bool:
    """True when the instrument is locked inside the TD tradable universe.

    Venue route: any spelling that normalizes to a TD exchange passes.
    Symbol-only route (venue missing/generic): passes only when the fresh
    full manifest vouches for the exact data-form symbol (e.g. "TD.TO" or
    "AAPL" as stored by the manifest builder). Fail closed otherwise.
    """
    if is_td_tradable_exchange(exchange):
        return True
    sym = (symbol or "").strip().upper()
    if not sym:
        return False
    symbols = _tradable_symbols_cached()
    return symbols is not None and sym in symbols


def td_universe_summary() -> dict[str, Any]:
    """Universe sizes and manifest state for summaries and health checks."""
    universe = commission_free_universe()
    summary: dict[str, Any] = {
        "commission_free_can": len(universe["CAN"]),
        "commission_free_us": len(universe["US"]),
        "commission_free_total": len(universe["CAN"]) + len(universe["US"]),
        "supported_exchanges": sorted(TD_EXCHANGE_CURRENCY),
    }
    state = tradable_universe_state()
    summary["tradable_manifest_state"] = state.get("state")
    if state.get("state") == "fresh":
        summary["tradable_symbol_total"] = state.get("symbol_total", 0)
    return summary
