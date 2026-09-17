"""Curate the data river: join moves to events for path rows. No training here."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from core.heart.attribution import DailyMove, attribute_move, move_key


def build_path_rows(
    moves: Sequence[DailyMove],
    events: Sequence[Any],
    *,
    path_id: str,
) -> list[dict[str, Any]]:
    """Join moves with events into flat rows for downstream path curation."""
    if not moves:
        return []
    rows: list[dict[str, Any]] = []
    for move in moves:
        att = attribute_move(move, events)
        rows.append(
            {
                "move_key": move_key(move),
                "symbol": move["symbol"],
                "session_date": move["session_date"],
                "gross_ret": move["gross_ret"],
                "event_identity": att["event_identity"],
                "path_id": path_id,
            }
        )
    return rows
