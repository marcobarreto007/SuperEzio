from datetime import datetime
from zoneinfo import ZoneInfo

from core.heart.attribution import attribute_move, attribute_moves, move_key
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


def test_attribute_moves_empty_returns_empty_dict():
    assert attribute_moves([], []) == {}


def test_attribute_moves_batch_hydration():
    event = MarketEvent(
        identity="nyse-halt:FTFT:2026-09-14T14:44:20-04:00",
        source="nyse_halts",
        event_type="nyse.luld_pause",
        occurred_at=datetime(2026, 9, 14, 14, 44, 20, tzinfo=ET),
        timestamp_precision="second",
        symbol="FTFT",
        mic_code="XNAS",
    )
    other_move = {
        **MOVE,
        "symbol": "OTHER",
        "session_date": "2026-09-15",
    }
    result = attribute_moves([MOVE, other_move], [event])
    key_ftft = move_key(MOVE)
    key_other = move_key(other_move)
    assert set(result) == {key_ftft, key_other}
    assert result[key_ftft]["event_identity"] == event.identity
    assert result[key_ftft]["confidence"] >= 0.6
    assert result[key_other]["event_identity"] is None
    assert result[key_other]["confidence"] == 0.0
    assert result[key_other]["evidence"]["reason"] == "no_event_in_window"


def test_attribute_moves_honest_zero_no_events():
    result = attribute_moves([MOVE], [])
    key = move_key(MOVE)
    assert result[key]["event_identity"] is None
    assert result[key]["confidence"] == 0.0
    assert result[key]["evidence"]["reason"] == "no_event_in_window"
