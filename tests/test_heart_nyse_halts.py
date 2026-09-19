from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from core.heart.nyse_halts import parse_nyse_halts_csv

CSV = (
    Path(__file__).resolve().parent / "fixtures" / "heart" / "spine" / "nyse_halts.csv"
).read_text(encoding="utf-8")


def test_luld_row_becomes_spine_market_event():
    events = parse_nyse_halts_csv(CSV)
    assert len(events) == 1
    ev = events[0]
    assert ev.identity == "nyse-halt:FTFT:2026-09-14T14:44:20-04:00"
    assert ev.source == "nyse_halts"
    assert ev.event_type == "nyse.luld_pause"
    assert ev.timestamp_precision == "second"
    assert ev.symbol == "FTFT"
    assert ev.mic_code == "XNAS"
    assert ev.occurred_at == datetime(2026, 9, 14, 14, 44, 20, tzinfo=ZoneInfo("America/New_York"))
