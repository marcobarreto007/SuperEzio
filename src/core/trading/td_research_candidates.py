"""TD research candidates backed by the local universe and dated price history."""

from __future__ import annotations

import csv
import json
import math
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .td_direct_ticket import load_td_commission_free_manifest

ROOT = Path(__file__).resolve().parents[3]


def load_research_candidates(root: Path = ROOT) -> dict[str, Any]:
    """Expose historical research inputs, never synthetic quotes or trade approvals.

    All numbers come from the effective-universe artifact or its CSV history.
    List membership is checked again against the official commission manifest.
    No provider calls, model inference, account balance or order transmission.
    """
    manifest = load_td_commission_free_manifest(root / "config/td_direct_commission_free_etfs.json")
    artifact_path = root / "config/td_universe_effective.json"
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    now = datetime.now(UTC)
    generated = datetime.fromisoformat(artifact["generated_at"])
    if generated.tzinfo is None or not 0 <= (now - generated).total_seconds() <= 7 * 86400:
        raise ValueError("effective_universe_stale_or_future")
    symbols = artifact["symbols"]
    if not isinstance(symbols, dict):
        raise TypeError("invalid_effective_universe")

    rows = []
    excluded = []
    for symbol in sorted(set(manifest["symbols"]["CAN"])):
        item = symbols.get(symbol, {})
        if not isinstance(item, dict) or item.get("listing_currency") != "CAD":
            continue
        if item.get("eligible_strict") is not True:
            continue
        # Derive the filename from a validated symbol, never an artifact path.
        if not re.fullmatch(r"[A-Z0-9]+(?:\.[A-Z0-9]+)?", symbol):
            continue
        ticker = symbol.replace(".", "-") + ".TO"
        history_path = root / "data/reference/effective_universe/ohlcv" / f"{ticker}.csv"
        try:
            with history_path.open(encoding="utf-8", newline="") as handle:
                latest = max(csv.DictReader(handle), key=lambda row: row["Date"])
            as_of = datetime.fromisoformat(latest["Date"]).date()
            close = float(latest["Close"])
            spread = float(item["friction"]["spread_pct_corwin_schultz_mean"])
            if not math.isfinite(close) or close <= 0:
                raise ValueError("invalid_close")
            if not math.isfinite(spread) or not 0 <= spread <= 0.5:
                raise ValueError("invalid_estimated_spread")
            if not 0 <= (now.date() - as_of).days <= 7:
                raise ValueError("history_stale_or_future")
        except (OSError, KeyError, TypeError, ValueError) as exc:
            excluded.append({"ticker": ticker, "reason": type(exc).__name__})
            continue
        rows.append(
            {
                "ticker": ticker,
                "name": item.get("fund_name") or symbol,
                "cluster": item.get("correlation_cluster"),
                "signal": "PESQUISA",
                "price": None,
                "historical_close": close,
                "price_as_of": as_of.isoformat(),
                "price_kind": "adjusted_daily_close",
                "friction": f"estimativa {spread:.4f}%",
                "estimated_spread_pct": spread,
                "commission": None,
                "commission_preview_required": True,
                "meta_labeling_p": None,
                "execution_ready": False,
                "provenance": {
                    "historical_close": {
                        "source": "yfinance",
                        "path": history_path.relative_to(root).as_posix(),
                        "as_of": as_of.isoformat(),
                        "adjusted": True,
                    },
                    "estimated_spread_pct": {
                        "path": artifact_path.relative_to(root).as_posix(),
                        "method": "Corwin-Schultz mean",
                        "is_estimate": True,
                        "as_of": artifact["generated_at"],
                    },
                    "commission_eligibility": {
                        "source_url": manifest["source_url"],
                        "verified_at": manifest["verified_at"],
                    },
                },
            }
        )
    return {
        "status": "research_only" if rows else "unavailable",
        "scanned_at": None,
        "reference_generated_at": artifact["generated_at"],
        "count": min(len(rows), 10),
        "available_count": len(rows),
        "total_universe": len(manifest["symbols"]["CAN"]) + len(manifest["symbols"]["US"]),
        "currency": "CAD",
        "selection": "alphabetical; not a return ranking",
        "message": "Candidatos para pesquisa. Fechamentos ajustados históricos; confirme cotação e custos antes de montar uma ordem.",
        "opportunities": rows[:10],
        "excluded": excluded,
    }
