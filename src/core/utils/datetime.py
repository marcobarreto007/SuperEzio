"""Shared ISO datetime parser — single source of truth.

Previously duplicated 4x across:
- core/sentiment/curator.py
- core/sentiment/live_monitor.py
- core/sentiment/watchlist_pulse.py
- agent_server/endpoints.py
"""

from datetime import datetime, timezone
from typing import Any


def parse_iso_datetime(value: Any) -> datetime | None:
    """Parse an ISO 8601 timestamp string, handling Z suffix and missing tzinfo.
    
    Returns None on any parse failure.
    """
    if not value:
        return None
    try:
        text = str(value)
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except (TypeError, ValueError):
        return None
