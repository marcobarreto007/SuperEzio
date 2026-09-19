"""NYSE trade-halts CSV → MarketEvent. Spine cycle: LULD Pause only."""

from __future__ import annotations

import csv
from datetime import datetime
from io import StringIO
from zoneinfo import ZoneInfo

from core.heart.event_book import MarketEvent

_NY = ZoneInfo("America/New_York")


def parse_nyse_halts_csv(text: str) -> list[MarketEvent]:
    events: list[MarketEvent] = []
    reader = csv.DictReader(StringIO(text))
    for row in reader:
        reason = (row.get("Reason") or "").strip()
        if "LULD" not in reason:
            continue
        symbol = (row.get("Symbol") or "").strip()
        halt_date = (row.get("Halt Date") or "").strip()
        halt_time = (row.get("Halt Time") or "").strip()
        occurred_at = datetime.strptime(f"{halt_date} {halt_time}", "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=_NY
        )
        exchange = (row.get("Exchange") or "").strip()
        events.append(
            MarketEvent(
                identity=f"nyse-halt:{symbol}:{occurred_at.isoformat()}",
                source="nyse_halts",
                event_type="nyse.luld_pause",
                occurred_at=occurred_at,
                timestamp_precision="second",
                symbol=symbol,
                mic_code="XNAS" if exchange == "Nasdaq" else None,
            )
        )
    return events
