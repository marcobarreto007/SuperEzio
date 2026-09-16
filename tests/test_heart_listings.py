from pathlib import Path

from core.heart.listings import parse_nasdaqtraded_lines


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
