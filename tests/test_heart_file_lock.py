"""Windows msvcrt heart locks must serialize in-process threads."""

from __future__ import annotations

import sys
import threading
from pathlib import Path

import pytest

from core.heart.event_book import EventBook, MarketEvent
from core.heart.raw_recorder import _file_lock


@pytest.mark.skipif(sys.platform != "win32", reason="msvcrt locking is Windows-specific")
def test_file_lock_serializes_threads_without_errno_36(tmp_path: Path):
    target = tmp_path / "events.jsonl"
    target.write_text("", encoding="utf-8")
    errors: list[tuple[int, str]] = []

    def worker(index: int) -> None:
        try:
            with _file_lock(target):
                pass
        except OSError as exc:
            errors.append((index, str(exc)))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
        assert not thread.is_alive()

    assert errors == []


@pytest.mark.skipif(sys.platform != "win32", reason="msvcrt locking is Windows-specific")
def test_event_book_append_from_multiple_threads(tmp_path: Path):
    from datetime import UTC, datetime

    book = EventBook(tmp_path / "events.jsonl")
    errors: list[str] = []

    def worker(index: int) -> None:
        try:
            book.append(
                MarketEvent(
                    identity=f"thread-{index}",
                    source="test",
                    event_type="rss.item",
                    occurred_at=datetime.now(UTC),
                    timestamp_precision="second",
                )
            )
        except OSError as exc:
            errors.append(str(exc))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
        assert not thread.is_alive()

    assert errors == []
    assert len(book.read_all()) == 6
