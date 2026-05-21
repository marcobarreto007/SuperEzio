#!/usr/bin/env python3
"""Resolve open official signals using price CSV or manual prices."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

_PKG = Path(__file__).resolve().parent
if str(_PKG) not in sys.path:
    sys.path.insert(0, str(_PKG))

from collector import append_jsonl
from policy import project_root


def _parse_iso(ts: str) -> datetime:
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    return datetime.fromisoformat(ts)


def _horizon_days(horizon: str) -> int:
    if horizon.endswith("d"):
        try:
            return int(horizon[:-1])
        except ValueError:
            pass
    return 5


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def load_prices_csv(path: Path) -> dict[str, list[tuple[datetime, float]]]:
    """CSV columns: ticker,date,close (date YYYY-MM-DD)."""
    by_ticker: dict[str, list[tuple[datetime, float]]] = {}
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ticker = str(row.get("ticker") or row.get("symbol") or "").upper()
            date_s = row.get("date") or row.get("ts")
            close = row.get("close") or row.get("price")
            if not ticker or not date_s or close is None:
                continue
            dt = datetime.strptime(date_s[:10], "%Y-%m-%d").replace(tzinfo=UTC)
            by_ticker.setdefault(ticker, []).append((dt, float(close)))
    for prices in by_ticker.values():
        prices.sort(key=lambda x: x[0])
    return by_ticker


def price_on_or_after(
    series: list[tuple[datetime, float]], target: datetime
) -> float | None:
    for dt, px in series:
        if dt >= target:
            return px
    return None


def resolve_one(
    emit: dict[str, Any],
    *,
    prices: dict[str, list[tuple[datetime, float]]],
    manual: dict[str, float],
    horizon_override: str | None,
) -> dict[str, Any] | None:
    if emit.get("status") != "official":
        return None
    ticker = str(emit.get("ticker") or "").upper()
    action = str(emit.get("action") or "HOLD")
    if action not in ("LONG", "SHORT"):
        return None

    ref_px = emit.get("evidence", {}).get("reference_price")
    if ref_px is None:
        return None
    ref_px = float(ref_px)

    horizon = horizon_override or str(emit.get("resolution_horizon") or "5d")
    days = _horizon_days(horizon)
    emitted_at = _parse_iso(str(emit["emitted_at"]))
    target_dt = emitted_at + timedelta(days=days)

    exit_px: float | None = None
    source = "manual"
    if ticker in manual:
        exit_px = float(manual[ticker])
        source = "manual_cli"
    elif ticker in prices:
        exit_px = price_on_or_after(prices[ticker], target_dt)
        source = f"csv:{horizon}"

    if exit_px is None:
        return None

    if action == "LONG":
        ret = (exit_px - ref_px) / ref_px
        hit = ret > 0
    else:
        ret = (ref_px - exit_px) / ref_px
        hit = ret > 0

    return {
        "record_type": "signal_resolution",
        "signal_id": emit["signal_id"],
        "resolved_at": datetime.now(UTC).isoformat(),
        "resolution_horizon": horizon,
        "exit_price": exit_px,
        "exit_price_source": source,
        "return_pct": round(ret * 100, 4),
        "hit": hit,
        "notes": None,
    }


def main() -> int:
    root = project_root()
    parser = argparse.ArgumentParser(description="Resolve official signals in ledger")
    parser.add_argument(
        "--emitted",
        type=Path,
        default=root / "data" / "signals" / "emitted.jsonl",
    )
    parser.add_argument(
        "--resolutions",
        type=Path,
        default=root / "data" / "signals" / "resolutions.jsonl",
    )
    parser.add_argument(
        "--prices-csv",
        type=Path,
        help="CSV with ticker,date,close for horizon exit",
    )
    parser.add_argument(
        "--manual-price",
        action="append",
        default=[],
        metavar="TICKER=PRICE",
        help="Manual exit price (repeatable)",
    )
    parser.add_argument("--horizon", type=str, help="Override horizon e.g. 5d, 20d")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    manual: dict[str, float] = {}
    for item in args.manual_price:
        if "=" not in item:
            continue
        t, p = item.split("=", 1)
        manual[t.strip().upper()] = float(p)

    prices: dict[str, list[tuple[datetime, float]]] = {}
    if args.prices_csv:
        prices = load_prices_csv(args.prices_csv)

    emitted = load_jsonl(args.emitted)
    existing = {r["signal_id"] for r in load_jsonl(args.resolutions) if r.get("signal_id")}

    written = 0
    skipped = 0
    for emit in emitted:
        sid = emit.get("signal_id")
        if not sid or sid in existing:
            skipped += 1
            continue
        res = resolve_one(
            emit,
            prices=prices,
            manual=manual,
            horizon_override=args.horizon,
        )
        if res is None:
            skipped += 1
            continue
        if args.dry_run:
            print(json.dumps(res, ensure_ascii=False))
        else:
            append_jsonl(args.resolutions, res)
        written += 1

    summary = {"written": written, "skipped": skipped, "dry_run": args.dry_run}
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
