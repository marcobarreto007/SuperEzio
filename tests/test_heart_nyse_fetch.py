"""Peça 2: fetch NYSE trade-halts CSV → EventBook (sem rede)."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from core.heart.event_book import EventBook
from core.heart.http import HeartHttpError
from core.heart.nyse_fetch import (
    NYSE_HALTS_URL,
    fetch_halts_csv,
    ingest_halts_csv,
)

CSV = (
    Path(__file__).resolve().parent / "fixtures" / "heart" / "spine" / "nyse_halts.csv"
).read_text(encoding="utf-8")


@pytest.fixture
def book(tmp_path: Path) -> EventBook:
    return EventBook(tmp_path / "events.jsonl")


@pytest.fixture(autouse=True)
def heart_user_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPEREZIO_HEART_USER_AGENT", "SuperEzioHeart/1.0 (marco@example.com)")


def test_nyse_halts_url_matches_roadmap():
    assert NYSE_HALTS_URL == "https://www.nyse.com/api/trade-halts/historical/download"


def test_fetch_halts_csv_returns_text_from_mock():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == NYSE_HALTS_URL
        assert "marco@example.com" in request.headers["User-Agent"]
        return httpx.Response(200, text=CSV)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert fetch_halts_csv(client) == CSV


def test_ingest_halts_csv_writes_luld_pause_events(book: EventBook):
    written = ingest_halts_csv(CSV, book)
    assert written == 1
    events = book.read_all()
    assert len(events) == 1
    assert events[0].event_type == "nyse.luld_pause"
    assert events[0].source == "nyse_halts"
    assert events[0].symbol == "FTFT"


def test_fetch_and_ingest_end_to_end(book: EventBook):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=CSV)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    text = fetch_halts_csv(client)
    written = ingest_halts_csv(text, book)
    assert written == 1
    assert book.read_all()[0].event_type == "nyse.luld_pause"


def test_fetch_halts_csv_4xx_raises_heart_http_error(book: EventBook):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, content=b"forbidden")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(HeartHttpError) as exc_info:
        fetch_halts_csv(client)
    assert exc_info.value.status == 403
    assert book.read_all() == []
