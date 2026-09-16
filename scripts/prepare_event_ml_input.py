"""Freeze a declared historical cohort for the offline ML experiment.

No downloads, eligibility filtering, recommendations, or broker connections.
Current adjusted histories are not point-in-time vendor snapshots.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SYMBOLS = ("VAB.TO", "VCE.TO", "VFV.TO", "TDB.TO", "TPE.TO")


def prepare(root: Path, output: Path, cutoff: str, symbols=DEFAULT_SYMBOLS) -> dict:
    cutoff_time = pd.Timestamp(cutoff)
    if cutoff_time.tzinfo is not None:
        raise ValueError("cutoff must be a calendar date without timezone")
    frames, sources = [], []
    for symbol in symbols:
        if not symbol.endswith(".TO") or not symbol.replace(".", "").isalnum():
            raise ValueError("invalid ticker filename")
        path = root / "data/reference/effective_universe/ohlcv" / f"{symbol}.csv"
        raw = path.read_bytes()
        frame = pd.read_csv(io.BytesIO(raw)).rename(columns=str.lower)
        frame["date"] = pd.to_datetime(frame["date"], errors="raise")
        frame = frame.loc[frame["date"] <= cutoff_time].copy()
        if frame.empty:
            raise ValueError(f"empty history before cutoff: {symbol}")
        frame.insert(0, "symbol", symbol)
        frames.append(frame[["symbol", "date", "open", "high", "low", "close", "volume"]])
        sources.append(
            {
                "symbol": symbol,
                "path": path.relative_to(root).as_posix(),
                "source_sha256": hashlib.sha256(raw).hexdigest(),
                "rows": len(frame),
                "first_date": str(frame.date.min().date()),
                "last_date": str(frame.date.max().date()),
            }
        )
    combined = pd.concat(frames).sort_values(["date", "symbol"])
    output.mkdir(parents=True, exist_ok=True)
    csv_path = output / "bars.csv"
    csv_temp = output / "bars.csv.tmp"
    combined.to_csv(csv_temp, index=False, date_format="%Y-%m-%d")
    csv_temp.replace(csv_path)
    manifest = {
        "schema_version": 1,
        "synthetic": False,
        "research_only": True,
        "cohort_rule": "Declared fixed CAD ETF cohort; no return-based or current eligibility filter",
        "symbols": list(symbols),
        "cutoff": cutoff,
        "rows": len(combined),
        "provider": "yfinance (per local acquisition code and universe manifest)",
        "acquisition_manifest": "config/td_universe_effective.json",
        "acquisition_manifest_sha256": hashlib.sha256(
            (root / "config/td_universe_effective.json").read_bytes()
        ).hexdigest(),
        "adjustment": "auto_adjust=True; retrospective adjusted daily OHLC",
        "input_sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
        "sources": sources,
        "limitations": [
            "Current surviving ETFs selected for a plumbing and historical signal experiment.",
            "Not a historical point-in-time universe; no claim of unbiased market-wide alpha.",
            "Adjusted bars can be revised; this hash freezes only the current local snapshot.",
            "No event/news features, order-book spreads, commissions, or LIMIT fill observations.",
            "Next-open fills are hypothetical research outcomes, not executable orders.",
        ],
    }
    manifest_temp = output / "input_manifest.json.tmp"
    manifest_temp.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    manifest_temp.replace(output / "input_manifest.json")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cutoff", default="2026-08-31")
    args = parser.parse_args()
    print(json.dumps(prepare(ROOT, args.output, args.cutoff), indent=2))


if __name__ == "__main__":
    main()
