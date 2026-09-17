"""Static Heart panel files — existence and API wiring in HTML."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_heart_panel_files_exist():
    assert (ROOT / "frontend" / "heart.html").is_file()
    assert (ROOT / "frontend" / "js" / "heart_panel.js").is_file()
    assert (ROOT / "frontend" / "css" / "heart_panel.css").is_file()


def test_heart_html_references_ranking_api():
    html = (ROOT / "frontend" / "heart.html").read_text(encoding="utf-8")
    assert "/api/heart/ranking" in html


def test_heart_ohlcv_store_exists_beside_eventbook():
    assert (ROOT / "data" / "heart" / "ohlcv").is_dir()
    assert (ROOT / "scripts" / "ops" / "start_heart_ingest.ps1").is_file()
    assert (ROOT / "scripts" / "ops" / "stop_heart_ingest.ps1").is_file()
