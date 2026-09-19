"""Honest refusal when Heart OHLCV store cannot support path weighting.

No LightGBM, CatBoost, or river — only inspects on-disk bars and DailyMove rows.
"""

from __future__ import annotations

from pathlib import Path

from core.heart.moves import daily_moves_from_bars
from core.heart.ohlcv_csv import bars_from_yahoo_csv, listing_guess_from_filename
from core.heart.paths import PathDecision


def _first_seen_from_bars(bars: list[dict]) -> str:
    if not bars:
        return "1970-01-01"
    ordered = sorted(bars, key=lambda bar: str(bar["session_date"]))
    return str(ordered[0]["session_date"])


def _collect_daily_moves(store_dir: Path) -> list:
    moves: list = []
    for csv_path in sorted(store_dir.glob("*.csv")):
        try:
            bars = bars_from_yahoo_csv(csv_path)
        except (OSError, ValueError, FileNotFoundError):
            continue
        if not bars:
            continue
        listing = listing_guess_from_filename(csv_path.name)
        first_seen = _first_seen_from_bars(bars)
        moves.extend(daily_moves_from_bars(bars=bars, listing=listing, first_seen=first_seen))
    return moves


def _store_has_bars(store_dir: Path) -> bool:
    for csv_path in store_dir.glob("*.csv"):
        try:
            bars = bars_from_yahoo_csv(csv_path)
        except (OSError, ValueError, FileNotFoundError):
            continue
        if bars:
            return True
    return False


def decide_or_refuse(store_dir: Path, path_id: str) -> PathDecision:
    """Refuse to weight when the store is empty; never invent a trained weight."""
    store = Path(store_dir)
    if not store.is_dir():
        return PathDecision(path_id=path_id, status="refused_empty_store", weight=0.0)

    if not any(store.glob("*.csv")):
        return PathDecision(path_id=path_id, status="refused_empty_store", weight=0.0)

    if not _store_has_bars(store):
        return PathDecision(path_id=path_id, status="refused_empty_store", weight=0.0)

    if not _collect_daily_moves(store):
        return PathDecision(path_id=path_id, status="refused_empty_store", weight=0.0)

    return PathDecision(path_id=path_id, status="unweighted", weight=0.0)
