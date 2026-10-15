"""Dashboard facts come from the Heart archive, not from a paper order board."""

import os
from datetime import UTC, datetime
from pathlib import Path

from agent_server.heart_endpoints import build_heart_status


def test_heart_status_reports_archive_and_refuses_learned_weights(tmp_path: Path):
    heart = tmp_path / "heart"
    ohlcv = heart / "ohlcv"
    raw = heart / "raw" / "2026" / "09" / "21"
    ohlcv.mkdir(parents=True)
    raw.mkdir(parents=True)
    (heart / "events.jsonl").write_text('{"identity":"a"}\n{"identity":"b"}\n', encoding="utf-8")
    (ohlcv / "ATXG.csv").write_text("Date,Open,High,Low,Close,Volume\n", encoding="utf-8")
    wire = raw / "newsfile.jsonl"
    wire.write_text("{}\n", encoding="utf-8")
    old = datetime(2026, 9, 21, 20, 0, tzinfo=UTC).timestamp()
    os.utime(wire, (old, old))

    status = build_heart_status(
        heart,
        ohlcv,
        now=datetime(2026, 9, 25, 21, 0, tzinfo=UTC),
    )

    assert status["paper_is_product"] is False
    assert status["events"] == 2
    assert status["priced_symbols"] == 1
    assert status["weights"] == "unweighted"
    assert status["freshness"] == "stale"
    assert "opiniao" in status["bob"]
    assert "TD" in status["execution"]


def test_dashboard_html_shows_current_reality():
    from pathlib import Path

    main = Path("src/agent_server/main.py").read_text(encoding="utf-8")
    index = Path("frontend/index.html").read_text(encoding="utf-8")
    assert "Paper não é o produto" in main or "Paper não é o produto" in index
    assert "Quality Dashboard" not in main
    assert "/api/heart/status" in main
    assert "Bob consulta o Coração" in index
