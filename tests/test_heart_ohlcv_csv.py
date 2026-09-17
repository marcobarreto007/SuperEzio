"""Bridge effective_universe OHLCV CSV → DailyMove (offline, no Yahoo)."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from core.heart.ohlcv_csv import (
    bars_from_yahoo_csv,
    last_session_moves,
    listing_guess_from_filename,
)
from core.math.risk import log_return

_HEADER = "Date,Open,High,Low,Close,Volume\n"


@pytest.fixture
def tiny_csv(tmp_path: Path) -> Path:
    path = tmp_path / "DEMO.csv"
    path.write_text(
        _HEADER
        + "2026-09-12,10.0,10.5,9.8,10.2,1000\n"
        + "2026-09-13,10.2,10.4,10.0,10.0,1100\n"
        + "2026-09-14,10.0,10.1,8.0,8.0,1200\n",
        encoding="utf-8",
    )
    return path


def test_bars_from_yahoo_csv_parses_three_sessions(tiny_csv: Path):
    bars = bars_from_yahoo_csv(tiny_csv)
    assert len(bars) == 3
    assert bars[0] == {
        "session_date": "2026-09-12",
        "open": 10.0,
        "high": 10.5,
        "low": 9.8,
        "close": 10.2,
        "volume": 1000.0,
    }
    assert bars[-1]["session_date"] == "2026-09-14"
    assert bars[-1]["close"] == 8.0


def test_bars_from_yahoo_csv_missing_file_raises():
    with pytest.raises(FileNotFoundError, match="ohlcv csv not found"):
        bars_from_yahoo_csv("/nonexistent/path/DEMO.csv")


def test_bars_from_yahoo_csv_header_only_returns_empty(tmp_path: Path):
    path = tmp_path / "empty.csv"
    path.write_text(_HEADER, encoding="utf-8")
    assert bars_from_yahoo_csv(path) == []


def test_listing_guess_us_symbol():
    row = listing_guess_from_filename("FTFT.csv")
    assert row.mic_code == "XNAS"
    assert row.symbol == "FTFT"
    assert row.source == "effective_universe_csv"


def test_listing_guess_tsx_simple():
    row = listing_guess_from_filename("VFV.TO.csv")
    assert row.mic_code == "XTSX"
    assert row.symbol == "VFV"
    assert row.source == "effective_universe_csv"


def test_listing_guess_tsx_yahoo_dash_class():
    """BTCX-B.TO.csv is Yahoo cache name; listing symbol is BTCX.B."""
    row = listing_guess_from_filename("BTCX-B.TO.csv")
    assert row.mic_code == "XTSX"
    assert row.symbol == "BTCX.B"


def test_last_session_moves_returns_last_n_with_log_returns(tiny_csv: Path):
    listing = listing_guess_from_filename("DEMO.csv")
    moves = last_session_moves(
        tiny_csv,
        listing,
        first_seen="2020-01-02",
        last_n_sessions=2,
    )
    assert len(moves) == 2
    assert [m["session_date"] for m in moves] == ["2026-09-13", "2026-09-14"]
    assert moves[0]["mic_code"] == "XNAS"
    assert moves[0]["symbol"] == "DEMO"
    assert moves[0]["first_seen"] == "2020-01-02"
    assert moves[0]["gross_ret"] == log_return(10.0, 10.2)
    assert moves[1]["gross_ret"] == log_return(8.0, 10.0)
    assert moves[0]["abnormal_ret"] == 0.0
    assert moves[0]["surprise_q"] == 0.0
    assert moves[0]["ewma_vol"] == 0.0
    assert math.isclose(moves[1]["gross_ret"], math.log(8.0 / 10.0))
