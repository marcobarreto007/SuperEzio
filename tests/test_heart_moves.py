import json
import math
from pathlib import Path

from core.heart.moves import daily_moves_from_bars
from core.heart.universe import ListingRow
from core.math.risk import log_return

BARS = json.loads(
    (Path(__file__).resolve().parent / "fixtures" / "heart" / "spine" / "bars.json").read_text(encoding="utf-8")
)


def test_september_14_move_is_log_return_with_honest_zeros():
    listing = ListingRow(
        mic_code="XNAS",
        symbol="FTFT",
        name="Future FinTech Group Inc.",
        exchange="Q",
        source="nasdaqtraded",
    )
    moves = daily_moves_from_bars(bars=BARS, listing=listing, first_seen="2020-01-02")
    target = next(m for m in moves if m["session_date"] == "2026-09-14")
    assert target["mic_code"] == "XNAS"
    assert target["symbol"] == "FTFT"
    assert target["first_seen"] == "2020-01-02"
    assert target["gross_ret"] == log_return(8.0, 10.1)
    assert target["abnormal_ret"] == 0.0
    assert target["surprise_q"] == 0.0
    assert target["ewma_vol"] == 0.0
    assert math.isclose(target["gross_ret"], math.log(8.0 / 10.1))
