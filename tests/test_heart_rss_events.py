"""Peça 2: RSS cru (JSONL P0) → EventBook."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from core.heart.event_book import EventBook
from core.heart.rss_events import (
    DEFAULT_EVENT_BOOK_PATH,
    ingest_raw_jsonl,
    parse_rss_items,
)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "heart" / "spine" / "rss.xml"


@pytest.fixture
def book(tmp_path: Path) -> EventBook:
    return EventBook(tmp_path / "events.jsonl")


def _spine_with_pubdate(pub_date: str) -> str:
    xml = FIXTURE.read_text(encoding="utf-8")
    return xml.replace(
        "</item>",
        f"<pubDate>{pub_date}</pubDate></item>",
    )


def test_parse_spine_fixture_yields_one_event_with_guid_identity():
    xml = _spine_with_pubdate("Mon, 15 Sep 2026 16:10:00 GMT")
    events = parse_rss_items(xml, source="prnewswire")
    assert len(events) == 1
    assert events[0].identity == "spine-guid-1"
    assert events[0].event_type == "rss.item"
    assert events[0].source == "prnewswire"
    assert events[0].symbol is None
    assert events[0].occurred_at == datetime(2026, 9, 15, 16, 10, tzinfo=UTC)
    assert events[0].timestamp_precision == "second"


def test_skips_item_when_pubdate_missing():
    xml = FIXTURE.read_text(encoding="utf-8")
    assert parse_rss_items(xml, source="prnewswire") == []


def test_skips_item_when_pubdate_unparseable():
    xml = _spine_with_pubdate("not-a-real-date")
    assert parse_rss_items(xml, source="prnewswire") == []


def test_pubdate_eastern_is_tz_aware():
    xml = _spine_with_pubdate("Mon, 15 Sep 2026 12:10:00 -0400")
    events = parse_rss_items(xml, source="prnewswire")
    assert len(events) == 1
    ny = ZoneInfo("America/New_York")
    assert events[0].occurred_at == datetime(2026, 9, 15, 12, 10, tzinfo=ny)
    assert events[0].timestamp_precision == "second"


def test_identity_falls_back_to_sha256_without_guid():
    xml = """<?xml version="1.0"?>
<rss version="2.0"><channel><title>x</title>
<item><title>t</title><pubDate>Mon, 15 Sep 2026 16:10:00 GMT</pubDate></item>
</channel></rss>"""
    events = parse_rss_items(xml, source="test")
    assert len(events) == 1
    assert events[0].identity.startswith("sha256:")


def test_symbol_from_exchange_ticker_in_description():
    xml = """<?xml version="1.0"?>
<rss version="2.0"><channel><title>x</title>
<item><title>Deal</title><guid>bw-1</guid>
<description>Acme (NYSE:CTRE) announces deal</description>
<pubDate>Mon, 15 Sep 2026 16:10:00 GMT</pubDate></item>
</channel></rss>"""
    events = parse_rss_items(xml, source="businesswire")
    assert len(events) == 1
    assert events[0].symbol == "CTRE"


def test_default_event_book_path():
    assert DEFAULT_EVENT_BOOK_PATH.name == "events.jsonl"
    assert DEFAULT_EVENT_BOOK_PATH.parent.name == "heart"


def test_ingest_raw_jsonl_writes_events(book: EventBook, tmp_path: Path):
    body = _spine_with_pubdate("Mon, 15 Sep 2026 16:10:00 GMT")
    raw_path = tmp_path / "prnewswire.jsonl"
    raw_path.write_text(
        json.dumps({"body": body, "feed_id": "prnewswire"}) + "\n",
        encoding="utf-8",
    )
    written, next_offset = ingest_raw_jsonl(raw_path, book, source="prnewswire")
    assert written == 1
    assert next_offset == raw_path.stat().st_size
    stored = book.read_all()
    assert len(stored) == 1
    assert stored[0].identity == "spine-guid-1"


def test_ingest_raw_jsonl_skips_corrupt_json(book: EventBook, tmp_path: Path):
    body = _spine_with_pubdate("Mon, 15 Sep 2026 16:10:00 GMT")
    raw_path = tmp_path / "mixed.jsonl"
    raw_path.write_text(
        "{broken\n"
        + json.dumps({"body": body}) + "\n",
        encoding="utf-8",
    )
    written, _ = ingest_raw_jsonl(raw_path, book, source="prnewswire")
    assert written == 1


def test_ingest_raw_jsonl_resumes_from_byte_offset(book: EventBook, tmp_path: Path):
    body = _spine_with_pubdate("Mon, 15 Sep 2026 16:10:00 GMT")
    raw_path = tmp_path / "resume.jsonl"
    first = (json.dumps({"body": body}) + "\n").encode("utf-8")
    second = json.dumps({"body": "<rss/>"}) + "\n"
    raw_path.write_bytes(first + second.encode("utf-8"))
    written, offset = ingest_raw_jsonl(raw_path, book, source="prnewswire", start_offset=0)
    assert written == 1
    written_tail, end_offset = ingest_raw_jsonl(
        raw_path, book, source="prnewswire", start_offset=offset
    )
    assert written_tail == 0
    assert end_offset == raw_path.stat().st_size


def test_ingest_raw_jsonl_skips_duplicate_identities(book: EventBook, tmp_path: Path):
    body = _spine_with_pubdate("Mon, 15 Sep 2026 16:10:00 GMT")
    raw_path = tmp_path / "dup.jsonl"
    line = json.dumps({"body": body}) + "\n"
    raw_path.write_text(line + line, encoding="utf-8")
    written, _ = ingest_raw_jsonl(raw_path, book, source="prnewswire")
    assert written == 1
    assert len(book.read_all()) == 1
