from datetime import date
from pathlib import Path

from core.heart.listings import ingest_nasdaqtraded_text, parse_nasdaqtraded_lines
from core.heart.universe import UniverseRegistry

_NASDAQ_HEADER = (
    "Nasdaq Traded|Symbol|Security Name|Listing Exchange|Market Category|ETF|"
    "Round Lot Size|Test Issue|Financial Status|CQS Symbol|NASDAQ Symbol|NextShares"
)


def test_ftft_maps_q_to_xnas():
    text = (
        Path(__file__).resolve().parent
        / "fixtures"
        / "heart"
        / "spine"
        / "nasdaqtraded_ftft.txt"
    ).read_text(encoding="utf-8")
    rows = parse_nasdaqtraded_lines(text)
    assert len(rows) == 1
    row = rows[0]
    assert row.symbol == "FTFT"
    assert row.mic_code == "XNAS"
    assert row.is_test is False
    assert row.source == "nasdaqtraded"


def test_ingest_nasdaqtraded_text_empty_inserts_nothing(tmp_path: Path):
    registry = UniverseRegistry(tmp_path / "universe.sqlite")
    result = ingest_nasdaqtraded_text(registry, "", as_of=date(2026, 9, 15))
    assert result.inserted == 0
    assert result.updated == 0
    assert result.delisted == 0
    assert registry.active() == []


def test_ingest_nasdaqtraded_text_minimal_line(tmp_path: Path):
    registry = UniverseRegistry(tmp_path / "universe.sqlite")
    text = f"{_NASDAQ_HEADER}\nY|AAA|Alpha Corp|Q|N|N|100|N||AAA|AAA|N\n"
    result = ingest_nasdaqtraded_text(registry, text, as_of=date(2026, 9, 15))
    assert result.inserted == 1
    active = registry.active()
    assert len(active) == 1
    assert active[0].symbol == "AAA"
    assert active[0].mic_code == "XNAS"
    assert active[0].first_seen == date(2026, 9, 15)
