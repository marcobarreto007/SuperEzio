from datetime import datetime
from zoneinfo import ZoneInfo

from core.heart.event_book import MarketEvent
from core.heart.ml.dataset import build_path_rows
from core.heart.paths import SPINE_PATH

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

LULD_EVENT = MarketEvent(
    identity="nyse-halt:FTFT:2026-09-14T14:44:20-04:00",
    source="nyse_halts",
    event_type="nyse.luld_pause",
    occurred_at=datetime(2026, 9, 14, 14, 44, 20, tzinfo=ET),
    timestamp_precision="second",
    symbol="FTFT",
    mic_code="XNAS",
)


def test_build_path_rows_empty_moves():
    assert build_path_rows([], [LULD_EVENT], path_id=SPINE_PATH.path_id) == []


def test_build_path_rows_joins_move_to_event():
    rows = build_path_rows([MOVE], [LULD_EVENT], path_id=SPINE_PATH.path_id)
    assert len(rows) == 1
    row = rows[0]
    assert row["move_key"] == "XNAS:FTFT:2020-01-02:2026-09-14"
    assert row["symbol"] == "FTFT"
    assert row["session_date"] == "2026-09-14"
    assert row["gross_ret"] == -0.23
    assert row["event_identity"] == LULD_EVENT.identity
    assert row["path_id"] == SPINE_PATH.path_id


def test_build_path_rows_no_match_yields_null_event_identity():
    other = MarketEvent(
        identity="nyse-halt:ZZZZ:2026-09-14T14:44:20-04:00",
        source="nyse_halts",
        event_type="nyse.luld_pause",
        occurred_at=datetime(2026, 9, 14, 14, 44, 20, tzinfo=ET),
        timestamp_precision="second",
        symbol="ZZZZ",
        mic_code="XNAS",
    )
    rows = build_path_rows([MOVE], [other], path_id=SPINE_PATH.path_id)
    assert rows[0]["event_identity"] is None
