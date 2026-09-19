"""24/7 Heart ingest while the FastAPI process is alive.

Polls irrecoverable RSS, folds dumps into EventBook, then NYSE LULD.
One failed feed or halt download does not stop the loop. No invented rows.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from core.heart.event_book import EventBook
from core.heart.feeds import NON_RECOVERABLE_FEEDS
from core.heart.http import HeartHttpError
from core.heart.nyse_fetch import fetch_halts_csv, ingest_halts_csv
from core.heart.poller import poll_all_feeds
from core.heart.raw_recorder import DEFAULT_HEART_ROOT, RawRecorder
from core.heart.rss_events import ingest_raw_jsonl

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_SECONDS = 60

_task: asyncio.Task[None] | None = None
_running = False


def _interval_seconds() -> int:
    raw = os.getenv("SUPEREZIO_HEART_INGEST_SECONDS", str(DEFAULT_INTERVAL_SECONDS))
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_INTERVAL_SECONDS
    return value if value >= 1 else DEFAULT_INTERVAL_SECONDS


def _fold_raw_into_book(root: Path, book: EventBook, recorder: RawRecorder) -> int:
    raw_root = root / "raw"
    if not raw_root.is_dir():
        return 0
    written = 0
    for jsonl in sorted(raw_root.rglob("*.jsonl")):
        if jsonl.name.endswith(".lock"):
            continue
        source = jsonl.stem
        start_offset = recorder.fold_offset(jsonl)
        try:
            written_inc, next_offset = ingest_raw_jsonl(
                jsonl,
                book,
                source=source,
                start_offset=start_offset,
            )
        except OSError as exc:
            logger.warning("heart fold skipped %s: %s", jsonl.name, exc)
            continue
        written += written_inc
        if next_offset > start_offset:
            recorder.save_fold_offset(jsonl, next_offset)
    return written


def run_heart_cycle(
    *,
    root: Path | None = None,
    client: httpx.Client,
) -> dict[str, Any]:
    """Blocking one-shot cycle. Tests inject a mocked client and tmp root."""
    heart_root = Path(root) if root is not None else DEFAULT_HEART_ROOT
    recorder = RawRecorder(root=heart_root)
    feeds_ok = poll_all_feeds(client, recorder)
    book = EventBook(heart_root / "events.jsonl")
    rss_events = 0
    try:
        rss_events = _fold_raw_into_book(heart_root, book, recorder)
    except OSError as exc:
        logger.error("heart fold failed: %s", exc)
    nyse_events = 0
    try:
        nyse_events = ingest_halts_csv(fetch_halts_csv(client), book)
    except (HeartHttpError, httpx.TransportError) as exc:
        logger.warning("heart nyse halt fetch failed: %s", exc)
    logger.info(
        "heart cycle done feeds_ok=%s/%s rss_events=%s nyse_events=%s at=%s",
        feeds_ok,
        len(NON_RECOVERABLE_FEEDS),
        rss_events,
        nyse_events,
        datetime.now(UTC).isoformat(),
    )
    return {
        "feeds_ok": feeds_ok,
        "feeds_total": len(NON_RECOVERABLE_FEEDS),
        "rss_events": rss_events,
        "nyse_events": nyse_events,
    }


def _cycle_with_own_client(root: Path) -> dict[str, Any]:
    with httpx.Client(timeout=60.0) as client:
        return run_heart_cycle(root=root, client=client)


async def background_heart_loop(root: Path | None = None) -> None:
    global _running
    _running = True
    heart_root = Path(root) if root is not None else DEFAULT_HEART_ROOT
    logger.info(
        "Heart ingest loop started root=%s interval=%ss",
        heart_root,
        _interval_seconds(),
    )
    while _running:
        if not os.getenv("SUPEREZIO_HEART_USER_AGENT"):
            logger.error("heart ingest skipped: SUPEREZIO_HEART_USER_AGENT is required")
        else:
            try:
                await asyncio.to_thread(_cycle_with_own_client, heart_root)
            except Exception as exc:  # noqa: BLE001
                logger.warning("heart ingest cycle failed: %s", exc)
        await asyncio.sleep(_interval_seconds())


def start_heart_ingest() -> None:
    global _task
    if os.getenv("SUPEREZIO_HEART_INGEST", "1") != "1":
        logger.info("Heart ingest loop disabled (SUPEREZIO_HEART_INGEST!=1)")
        return
    if _task is not None and not _task.done():
        logger.info("Heart ingest loop already running")
        return
    _task = asyncio.create_task(background_heart_loop())


def stop_heart_ingest() -> None:
    global _running, _task
    _running = False
    if _task is not None and not _task.done():
        _task.cancel()
    _task = None
