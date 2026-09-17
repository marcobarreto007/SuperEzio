"""Disk hydration for HeartView — no invented OHLCV."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from types import ModuleType
from zoneinfo import ZoneInfo

from agent_server.heart_endpoints import HeartView
from core.heart.event_book import EventBook, MarketEvent
from core.heart.hydrate import refresh_heart_view

ET = ZoneInfo("America/New_York")
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "heart" / "spine"
BARS = json.loads((FIXTURES / "bars.json").read_text(encoding="utf-8"))


def _write_ftft_event(events_path: Path) -> None:
    event = MarketEvent(
        identity="nyse-halt:FTFT:2026-09-14T14:44:20-04:00",
        source="nyse_halts",
        event_type="nyse.luld_pause",
        occurred_at=datetime(2026, 9, 14, 14, 44, 20, tzinfo=ET),
        timestamp_precision="second",
        symbol="FTFT",
        mic_code="XNAS",
    )
    book = EventBook(events_path)
    book.append(event)


def _install_ohlcv_csv(monkeypatch, *, bars_by_path: dict[Path, list[dict]] | None = None):
    """Inject a fake core.heart.ohlcv_csv module for hermetic tests."""

    def bars_from_yahoo_csv(path: Path) -> list[dict]:
        if bars_by_path is not None:
            return list(bars_by_path.get(Path(path), []))
        if Path(path).name == "FTFT.csv":
            return list(BARS)
        return []

    fake = ModuleType("core.heart.ohlcv_csv")
    fake.bars_from_yahoo_csv = bars_from_yahoo_csv
    monkeypatch.setitem(sys.modules, "core.heart.ohlcv_csv", fake)


def test_refresh_reads_events_from_jsonl(tmp_path: Path):
    heart_root = tmp_path / "heart"
    heart_root.mkdir()
    _write_ftft_event(heart_root / "events.jsonl")
    view = HeartView()
    refresh_heart_view(view, heart_root=heart_root, ohlcv_dir=None)
    assert len(view.events) == 1
    assert view.events[0].symbol == "FTFT"
    assert view.moves == []


def test_refresh_without_ohlcv_module_leaves_moves_empty(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("core.heart.hydrate._resolve_bars_loader", lambda: None)
    heart_root = tmp_path / "heart"
    heart_root.mkdir()
    _write_ftft_event(heart_root / "events.jsonl")
    ohlcv = tmp_path / "ohlcv"
    ohlcv.mkdir()
    (ohlcv / "FTFT.csv").write_text("Date,Close\n2026-09-14,8.0\n", encoding="utf-8")
    view = HeartView()
    refresh_heart_view(view, heart_root=heart_root, ohlcv_dir=ohlcv)
    assert view.moves == []


def test_refresh_loads_moves_for_event_tickers(tmp_path: Path, monkeypatch):
    _install_ohlcv_csv(monkeypatch)
    heart_root = tmp_path / "heart"
    heart_root.mkdir()
    _write_ftft_event(heart_root / "events.jsonl")
    ohlcv = tmp_path / "ohlcv"
    ohlcv.mkdir()
    (ohlcv / "FTFT.csv").write_text("placeholder\n", encoding="utf-8")
    (ohlcv / "OTHER.csv").write_text("placeholder\n", encoding="utf-8")
    view = HeartView()
    refresh_heart_view(view, heart_root=heart_root, ohlcv_dir=ohlcv)
    assert view.moves
    assert all(m["symbol"] == "FTFT" for m in view.moves)
    assert any(m["session_date"] == "2026-09-14" for m in view.moves)


def test_refresh_bars_from_first_luld_event(tmp_path: Path, monkeypatch):
    _install_ohlcv_csv(monkeypatch)
    heart_root = tmp_path / "heart"
    heart_root.mkdir()
    _write_ftft_event(heart_root / "events.jsonl")
    ohlcv = tmp_path / "ohlcv"
    ohlcv.mkdir()
    (ohlcv / "FTFT.csv").write_text("placeholder\n", encoding="utf-8")
    view = HeartView()
    refresh_heart_view(view, heart_root=heart_root, ohlcv_dir=ohlcv)
    assert view.bars == BARS


def test_refresh_missing_events_jsonl_leaves_events_empty(tmp_path: Path, monkeypatch):
    _install_ohlcv_csv(monkeypatch)
    heart_root = tmp_path / "heart"
    heart_root.mkdir()
    ohlcv = tmp_path / "ohlcv"
    ohlcv.mkdir()
    (ohlcv / "AAA.csv").write_text("placeholder\n", encoding="utf-8")
    view = HeartView()
    refresh_heart_view(view, heart_root=heart_root, ohlcv_dir=ohlcv)
    assert view.events == []
    assert len(view.moves) <= 20


def test_refresh_no_events_caps_at_twenty_csvs(tmp_path: Path, monkeypatch):
    _install_ohlcv_csv(monkeypatch, bars_by_path={})
    heart_root = tmp_path / "heart"
    heart_root.mkdir()
    ohlcv = tmp_path / "ohlcv"
    ohlcv.mkdir()
    for idx in range(25):
        (ohlcv / f"T{idx:02d}.csv").write_text("placeholder\n", encoding="utf-8")
    view = HeartView()
    refresh_heart_view(view, heart_root=heart_root, ohlcv_dir=ohlcv)
    assert view.events == []
    assert view.moves == []


def test_refresh_never_invents_ohlcv(tmp_path: Path, monkeypatch):
    _install_ohlcv_csv(monkeypatch, bars_by_path={})
    heart_root = tmp_path / "heart"
    heart_root.mkdir()
    _write_ftft_event(heart_root / "events.jsonl")
    ohlcv = tmp_path / "ohlcv"
    ohlcv.mkdir()
    view = HeartView()
    refresh_heart_view(view, heart_root=heart_root, ohlcv_dir=ohlcv)
    assert view.moves == []
    assert view.bars == []


def test_refresh_no_ohlcv_dir_leaves_moves_empty(tmp_path: Path, monkeypatch):
    _install_ohlcv_csv(monkeypatch)
    heart_root = tmp_path / "heart"
    heart_root.mkdir()
    _write_ftft_event(heart_root / "events.jsonl")
    view = HeartView()
    refresh_heart_view(view, heart_root=heart_root, ohlcv_dir=None)
    assert view.moves == []
    assert view.bars == []
