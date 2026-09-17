"""Parse SEC EDGAR getcurrent Atom feeds into MarketEvent rows."""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from xml.etree import ElementTree as ET

from core.heart.event_book import MarketEvent

logger = logging.getLogger(__name__)

_CIK_RE = re.compile(r"\((\d{10})\)|\bCIK=(\d+)\b", re.IGNORECASE)
_FORM_RE = re.compile(r"^([0-9A-Z/-]+)\s+-", re.IGNORECASE)
_ACC_RE = re.compile(r"accession-number=([0-9-]+)|([0-9]{10}-[0-9]{2}-[0-9]{6})", re.IGNORECASE)


def parse_edgar_atom(body: bytes, form: str | None = "8-K") -> list[MarketEvent]:
    """Parse a SEC EDGAR Atom XML feed and return MarketEvent entries.

    Parameters
    ----------
    body : bytes
        Raw bytes from the SEC getcurrent Atom XML feed.
    form : str | None, optional
        Filter by form type (e.g. "8-K"). If None, all forms are accepted.

    Returns
    -------
    list[MarketEvent]
        Extracted market events sorted chronologically.
    """
    events: list[MarketEvent] = []
    if not body or not body.strip():
        return events

    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        logger.warning("SEC EDGAR Atom XML parse error: %s", exc)
        return events

    # Support feeds with default xmlns="http://www.w3.org/2005/Atom" or without namespace
    entries = root.findall("{http://www.w3.org/2005/Atom}entry")
    if not entries:
        entries = root.findall("entry")

    for entry in entries:
        event = _entry_to_event(entry, target_form=form)
        if event is not None:
            events.append(event)

    return events


def _entry_to_event(entry: ET.Element, target_form: str | None = None) -> MarketEvent | None:
    # 1. Form detection via <category term="..."> or title
    category = entry.find("{http://www.w3.org/2005/Atom}category")
    if category is None:
        category = entry.find("category")

    entry_form: str | None = None
    if category is not None:
        entry_form = category.get("term")

    title_elem = entry.find("{http://www.w3.org/2005/Atom}title")
    if title_elem is None:
        title_elem = entry.find("title")
    title_text = (title_elem.text or "").strip() if title_elem is not None else ""

    if not entry_form and title_text:
        match = _FORM_RE.match(title_text)
        if match:
            entry_form = match.group(1).strip()

    entry_form = entry_form or "UNKNOWN"

    if target_form is not None and entry_form.upper() != target_form.upper():
        return None

    # 2. Timestamp via <updated>
    updated_elem = entry.find("{http://www.w3.org/2005/Atom}updated")
    if updated_elem is None:
        updated_elem = entry.find("updated")

    if updated_elem is None or not (updated_elem.text or "").strip():
        return None

    try:
        occurred_at = datetime.fromisoformat(updated_elem.text.strip())
        if occurred_at.tzinfo is None:
            occurred_at = occurred_at.replace(tzinfo=UTC)
        else:
            occurred_at = occurred_at.astimezone(UTC)
    except (ValueError, TypeError):
        return None

    # 3. ID / Accession Number
    id_elem = entry.find("{http://www.w3.org/2005/Atom}id")
    if id_elem is None:
        id_elem = entry.find("id")
    raw_id = (id_elem.text or "").strip() if id_elem is not None else ""

    acc_match = _ACC_RE.search(raw_id)
    accession = acc_match.group(1) or acc_match.group(2) if acc_match else raw_id

    # 4. CIK extraction from title
    cik: str | None = None
    cik_match = _CIK_RE.search(title_text)
    if cik_match:
        cik = cik_match.group(1) or cik_match.group(2)

    identity = f"sec:{entry_form.lower()}:{accession or occurred_at.isoformat()}"
    if cik:
        identity = f"sec:{entry_form.lower()}:{cik}:{accession}"

    return MarketEvent(
        identity=identity,
        source="sec_getcurrent",
        event_type=entry_form,
        occurred_at=occurred_at,
        timestamp_precision="second",
        symbol=cik,
        mic_code=None,
    )
