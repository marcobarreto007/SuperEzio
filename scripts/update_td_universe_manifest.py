#!/usr/bin/env python
"""Build config/td_tradable_universe.json — the full TD tradable ticker manifest.

Sources (validated 2026-08-23):
  US  Nasdaq Trader Symbol Directory (keyless, daily):
      https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt   -> NASDAQ
      https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt    -> NYSE / NYSE American / NYSE Arca
      (otherlisted exchange codes kept: N=NYSE, A=NYSE American, P=NYSE Arca;
       Z=Cboe BZX and V=IEXG are SKIPPED — not confirmed TD-supported)
  CA  Twelve Data /stocks?exchange=XTSE|XTSX (paginated, 8 req/min free tier):
      requires TWELVE_DATA_API_KEY in the environment or .env/.env.local.
      Symbols are stored in data form (.TO for TSX, .V for TSXV) so providers
      can price them directly. Dual-listed symbols are stored in BOTH forms —
      they are distinct instruments (currency/venue) for the data layer.

Output schema (v2), consumed by core.trading.td_universe:
  {schema_version, generated_at, ttl_days, sources, exchanges: {<CANONICAL>: [...]}}
  Fresh manifest (within ttl_days) lets is_td_tradable() vouch for a symbol
  when the venue string is missing/generic; stale/missing degrades to the
  exchange allowlist (explicit, never silent).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = PROJECT_ROOT / "config" / "td_tradable_universe.json"
SCHEMA_VERSION = 2
DEFAULT_TTL_DAYS = 7

_NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
_OTHER_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"
_TWELVE_STOCKS_URL = "https://api.twelvedata.com/stocks"

# otherlisted.txt "Exchange" column -> canonical TD exchange
_OTHER_LISTED_CODE_MAP = {
    "N": "NYSE",
    "A": "NYSEAMERICAN",
    "P": "NYSEARCA",
}

# Twelve Data exchange codes -> (canonical exchange, data-form suffix)
_TWELVE_EXCHANGES = {
    "XTSE": ("TSX", ".TO"),
    "XTSX": ("TSXV", ".V"),
}
_TWELVE_TYPES = {"Common Stock", "ETF", "ETP"}
_TWELVE_PAGE_SIZE = 100
_TWELVE_MAX_PAGES = 40
_TWELVE_REQUEST_GAP_S = 7.5  # free tier: 8 requests/min


def _log(message: str) -> None:
    print(f"[td-universe] {message}", flush=True)


def _load_env_file_keys() -> dict[str, str]:
    """Minimal KEY=VALUE parser for .env.local / .env (no dotenv dependency)."""
    keys: dict[str, str] = {}
    for name in (".env.local", ".env"):
        path = PROJECT_ROOT / name
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            keys.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    return keys


def _twelve_api_key() -> str | None:
    env = _load_env_file_keys()
    value = os.environ.get("TWELVE_DATA_API_KEY") or env.get("TWELVE_DATA_API_KEY")
    return value or None


# ── US: Nasdaq Trader Symbol Directory ──────────────────────────────────────


def _fetch_text(url: str) -> str:
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.text


def _parse_pipe_rows(text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return rows
    header = [col.strip("|").strip() for col in lines[0].split("|")]
    for line in lines[1:]:
        if line.startswith("File Creation Time"):
            continue
        values = line.split("|")
        rows.append(dict(zip(header, values)))
    return rows


def fetch_us_universe() -> dict[str, list[str]]:
    """NASDAQ + NYSE + NYSE American + NYSE Arca listed symbols (test issues out)."""
    exchanges: dict[str, list[str]] = {
        "NASDAQ": [],
        "NYSE": [],
        "NYSEAMERICAN": [],
        "NYSEARCA": [],
    }

    nasdaq_rows = _parse_pipe_rows(_fetch_text(_NASDAQ_LISTED_URL))
    for row in nasdaq_rows:
        symbol = (row.get("Symbol") or "").strip().upper()
        test_issue = (row.get("Test Issue") or "").strip().upper()
        if not symbol or test_issue == "Y":
            continue
        exchanges["NASDAQ"].append(symbol)

    other_rows = _parse_pipe_rows(_fetch_text(_OTHER_LISTED_URL))
    for row in other_rows:
        symbol = (row.get("ACT Symbol") or row.get("Symbol") or "").strip().upper()
        code = (row.get("Exchange") or "").strip().upper()
        test_issue = (row.get("Test Issue") or "").strip().upper()
        canonical = _OTHER_LISTED_CODE_MAP.get(code)
        if not symbol or test_issue == "Y" or canonical is None:
            continue
        exchanges[canonical].append(symbol)

    return {name: sorted(set(symbols)) for name, symbols in exchanges.items()}


# ── CA: Twelve Data (XTSE=TSX, XTSX=TSXV) ───────────────────────────────────


def fetch_ca_universe(api_key: str) -> dict[str, list[str]]:
    exchanges: dict[str, list[str]] = {"TSX": [], "TSXV": []}

    for exchange_code, (canonical, suffix) in _TWELVE_EXCHANGES.items():
        for page in range(1, _TWELVE_MAX_PAGES + 1):
            if page > 1:
                time.sleep(_TWELVE_REQUEST_GAP_S)
            try:
                response = requests.get(
                    _TWELVE_STOCKS_URL,
                    params={
                        "exchange": exchange_code,
                        "apikey": api_key,
                        "page_size": _TWELVE_PAGE_SIZE,
                        "page": page,
                    },
                    timeout=30,
                )
                response.raise_for_status()
            except requests.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else 0
                # Never let the apikey (embedded in the request URL) reach logs.
                hint = (
                    "quota exhausted — retry after the daily/minute reset"
                    if status == 429
                    else "url redacted (contains apikey)"
                )
                raise RuntimeError(
                    f"Twelve Data {exchange_code} page {page}: HTTP {status} — {hint}"
                ) from None
            payload = response.json()
            if payload.get("status") == "error":
                raise RuntimeError(
                    f"Twelve Data error for {exchange_code}: {payload.get('message')}"
                )
            entries = payload.get("data") or []
            for entry in entries:
                symbol = str(entry.get("symbol") or "").strip().upper()
                entry_type = str(entry.get("type") or "").strip()
                if not symbol or entry_type not in _TWELVE_TYPES:
                    continue
                exchanges[canonical].append(symbol + suffix)
            total = int(payload.get("meta", {}).get("count") or 0)
            fetched = page * _TWELVE_PAGE_SIZE
            _log(f"Twelve Data {exchange_code}: page {page}, total reported {total}")
            if fetched >= total or not entries:
                break
        else:
            raise RuntimeError(f"Twelve Data {exchange_code}: exceeded {_TWELVE_MAX_PAGES} pages")

    return {name: sorted(set(symbols)) for name, symbols in exchanges.items()}


# ── Manifest assembly ───────────────────────────────────────────────────────


def build_manifest(sections: dict[str, list[str]], sources: dict[str, str]) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "ttl_days": DEFAULT_TTL_DAYS,
        "sources": sources,
        "exchanges": sections,
    }


def write_manifest(manifest: dict) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = MANIFEST_PATH.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp_path.replace(MANIFEST_PATH)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", choices=("us", "ca", "all"), default="all")
    parser.add_argument("--dry-run", action="store_true", help="print counts without writing")
    args = parser.parse_args()

    sections: dict[str, list[str]] = {}
    sources: dict[str, str] = {}
    failures: list[str] = []

    if args.only in ("us", "all"):
        try:
            _log("fetching US universe (Nasdaq Trader Symbol Directory)...")
            us = fetch_us_universe()
            sections.update(us)
            sources["us_nasdaq_trader"] = _NASDAQ_LISTED_URL
            for name, symbols in us.items():
                _log(f"  {name}: {len(symbols)} symbols")
        except Exception as exc:  # noqa: BLE001 — report and continue to CA
            failures.append(f"us: {exc}")
            _log(f"US fetch FAILED: {exc}")

    if args.only in ("ca", "all"):
        api_key = _twelve_api_key()
        if not api_key:
            message = "TWELVE_DATA_API_KEY not set (env or .env/.env.local)"
            if args.only == "ca":
                _log(f"CA fetch FAILED: {message}")
                return 1
            failures.append(f"ca: {message}")
            _log(f"CA fetch SKIPPED: {message}")
        else:
            try:
                _log("fetching CA universe (Twelve Data XTSE/XTSX; paced 8/min)...")
                ca = fetch_ca_universe(api_key)
                sections.update(ca)
                sources["ca_twelve_data"] = _TWELVE_STOCKS_URL
                for name, symbols in ca.items():
                    _log(f"  {name}: {len(symbols)} symbols")
            except Exception as exc:  # noqa: BLE001
                failures.append(f"ca: {exc}")
                _log(f"CA fetch FAILED: {exc}")

    if not sections:
        _log("no source succeeded; manifest NOT written")
        for failure in failures:
            _log(f"  failure: {failure}")
        return 1

    manifest = build_manifest(sections, sources)
    total = sum(len(symbols) for symbols in sections.values())
    _log(f"manifest total: {total} symbols across {len(sections)} exchanges")
    for failure in failures:
        _log(f"  partial failure: {failure}")

    if args.dry_run:
        _log("dry-run: manifest NOT written")
        return 0

    write_manifest(manifest)
    _log(f"manifest written: {MANIFEST_PATH}")
    return 0 if not failures else 2


if __name__ == "__main__":
    sys.exit(main())
