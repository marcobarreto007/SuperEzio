from pathlib import Path

from core.heart.paths import PathDecision, PathSpec, SPINE_PATH

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "heart" / "spine"


def test_spine_path_id_is_frozen():
    assert SPINE_PATH == PathSpec(
        event_type="nyse.luld_pause",
        window="same_session",
        axis="gross_return",
    )
    assert SPINE_PATH.path_id == "nyse.luld_pause|same_session|gross_return"


def test_killed_decision_has_zero_weight():
    d = PathDecision(path_id=SPINE_PATH.path_id, status="killed", weight=0.0)
    assert d.status == "killed"
    assert d.weight == 0.0


def test_spine_fixtures_exist_with_required_tokens():
    csv = (FIXTURES / "nyse_halts.csv").read_text(encoding="utf-8")
    assert "FTFT" in csv
    assert "LULD Pause" in csv
    assert "14:44:20" in csv
    bars = (FIXTURES / "bars.json").read_text(encoding="utf-8")
    assert "2026-09-14" in bars
    assert "8.00" in bars or "8.0" in bars
    rss = (FIXTURES / "rss.xml").read_text(encoding="utf-8")
    assert "<rss" in rss.lower() or "<rss" in rss
