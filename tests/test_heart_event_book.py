"""Peça 2: livro de eventos append-only, com precisão do carimbo."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from core.heart.event_book import EventBook, MarketEvent


@pytest.fixture
def book(tmp_path: Path) -> EventBook:
    return EventBook(tmp_path / "events.jsonl")


def test_append_keeps_timestamp_precision(book: EventBook):
    event = MarketEvent(
        identity="sec:8-k:0000320193:2026-09-15T16:10:00Z",
        source="sec_getcurrent",
        event_type="8-K",
        occurred_at=datetime(2026, 9, 15, 16, 10, tzinfo=UTC),
        timestamp_precision="second",
        symbol="AAPL",
        mic_code="XNAS",
    )
    result = book.append(event)
    assert result.written is True
    stored = book.read_all()
    assert stored[0].timestamp_precision == "second"
    assert stored[0].occurred_at == event.occurred_at


def test_duplicate_identity_is_a_noop(book: EventBook):
    event = MarketEvent(
        identity="nyse-halt:FTFT:2026-09-14T14:44:20Z",
        source="nyse_halts",
        event_type="LULD",
        occurred_at=datetime(2026, 9, 14, 14, 44, 20, tzinfo=UTC),
        timestamp_precision="second",
        symbol="FTFT",
        mic_code="XNAS",
    )
    assert book.append(event).written is True
    assert book.append(event).written is False
    assert len(book.read_all()) == 1


def test_corrupt_line_is_quarantined(book: EventBook, tmp_path: Path):
    path = tmp_path / "events.jsonl"
    path.write_text("{broken\n", encoding="utf-8")
    book = EventBook(path)
    event = MarketEvent(
        identity="x",
        source="test",
        event_type="news",
        occurred_at=datetime(2026, 9, 15, tzinfo=UTC),
        timestamp_precision="day",
    )
    book.append(event)
    assert (
        path.with_name("events.jsonl.quarantine").read_text(encoding="utf-8").startswith("{broken")
    )
    assert json.loads(path.read_text(encoding="utf-8").splitlines()[-1])["identity"] == "x"


def test_ingest_many_writes_new_events_skips_duplicates(book: EventBook):
    from core.heart.nyse_halts import parse_nyse_halts_csv

    nyse_csv = (
        Path(__file__).resolve().parent / "fixtures" / "heart" / "spine" / "nyse_halts.csv"
    ).read_text(encoding="utf-8")
    batch = parse_nyse_halts_csv(nyse_csv)
    assert book.ingest_many(batch) == 1
    assert len(book.read_all()) == 1
    assert book.ingest_many(batch) == 0
    assert len(book.read_all()) == 1


def test_ingest_many_empty_list_returns_zero(book: EventBook):
    assert book.ingest_many([]) == 0
