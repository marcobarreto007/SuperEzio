"""RSS XML (from P0 raw JSONL) → MarketEvent rows for EventBook."""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from xml.etree import ElementTree as ET

from core.heart.event_book import EventBook, MarketEvent
from core.heart.identities import item_identity
from core.paths import project_path

logger = logging.getLogger(__name__)

DEFAULT_EVENT_BOOK_PATH = project_path("data", "heart", "events.jsonl")

_TICKER_RE = re.compile(r"\([A-Z]+:([A-Z0-9.-]+)\)")


def parse_rss_items(xml_text: str, *, source: str) -> list[MarketEvent]:
    events: list[MarketEvent] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        logger.warning("RSS XML parse failed for source=%s", source)
        return []

    channel = root.find("channel")
    if channel is None:
        return []

    for item in channel.findall("item"):
        event = _item_to_event(item, source=source)
        if event is not None:
            events.append(event)
    return events


def ingest_raw_jsonl(
    path: Path,
    book: EventBook,
    *,
    source: str,
    start_offset: int = 0,
) -> tuple[int, int]:
    """Fold raw JSONL into EventBook from ``start_offset``. Returns (written, next_offset)."""
    written = 0
    raw_path = Path(path)
    if not raw_path.exists():
        return 0, 0
    file_size = raw_path.stat().st_size
    if start_offset >= file_size:
        return 0, start_offset
    with open(raw_path, "rb") as handle:
        handle.seek(start_offset)
        while True:
            raw_line = handle.readline()
            if not raw_line:
                break
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue
            body = row.get("body")
            if not isinstance(body, str) or not body.strip():
                continue
            written += book.ingest_many(parse_rss_items(body, source=source))
        next_offset = handle.tell()
    return written, next_offset


def _item_to_event(item: ET.Element, *, source: str) -> MarketEvent | None:
    guid = _element_text(item.find("guid"))
    item_bytes = ET.tostring(item, encoding="utf-8")
    identity = item_identity(item_bytes, guid or None)

    pub_date_raw = _element_text(item.find("pubDate"))
    if not pub_date_raw:
        return None
    occurred_at, precision = _parse_pubdate(pub_date_raw)
    if occurred_at is None:
        return None

    symbol = _extract_symbol(item)
    return MarketEvent(
        identity=identity,
        source=source,
        event_type="rss.item",
        occurred_at=occurred_at,
        timestamp_precision=precision,
        symbol=symbol,
    )


def _element_text(node: ET.Element | None) -> str:
    if node is None or node.text is None:
        return ""
    return node.text.strip()


def _parse_pubdate(raw: str) -> tuple[datetime | None, str]:
    try:
        occurred_at = parsedate_to_datetime(raw.strip())
    except (TypeError, ValueError, OverflowError):
        return None, "unknown"
    if occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=UTC)
    precision = "second" if re.search(r"\d{1,2}:\d{2}", raw) else "unknown"
    return occurred_at, precision


def _extract_symbol(item: ET.Element) -> str | None:
    for tag in ("description", "title"):
        text = _element_text(item.find(tag))
        match = _TICKER_RE.search(text)
        if match:
            return match.group(1)
    return None
