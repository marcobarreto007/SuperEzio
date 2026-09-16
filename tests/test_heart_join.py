from datetime import datetime
from zoneinfo import ZoneInfo

from core.heart.attribution import attribute_move
from core.heart.event_book import MarketEvent

ET = ZoneInfo("America/New_York")

MOVE = {
    "mic_code": "XNAS",
    "symbol": "FTFT",
    "first_seen": "2020-01-02",
    "session_date": "2026-09-14",
    "abnormal_ret": 0.0,
    "gross_ret": -0.23,
    "surprise_q": 0.0,
    "ewma_vol": 0.0,
}


def test_luld_pause_joins_same_session_and_auto_accepts():
    event = MarketEvent(
        identity="nyse-halt:FTFT:2026-09-14T14:44:20-04:00",
        source="nyse_halts",
        event_type="nyse.luld_pause",
        occurred_at=datetime(2026, 9, 14, 14, 44, 20, tzinfo=ET),
        timestamp_precision="second",
        symbol="FTFT",
        mic_code="XNAS",
    )
    result = attribute_move(MOVE, [event])
    assert result["event_identity"] == event.identity
    assert result["confidence"] >= 0.6
