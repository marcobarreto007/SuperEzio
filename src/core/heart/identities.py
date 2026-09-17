"""Stable item identities: GUID when present, else SHA-256 of the body."""

from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET


def item_identity(body: bytes, guid: str | None) -> str:
    if guid:
        return guid
    return "sha256:" + hashlib.sha256(body).hexdigest()


def extract_rss_item_guids(body: bytes) -> list[str]:
    """Return stripped ``<guid>`` text for each RSS ``<item>``, in document order."""
    root = ET.fromstring(body)
    guids: list[str] = []
    for item in root.iter("item"):
        guid_el = item.find("guid")
        if guid_el is not None and guid_el.text:
            guids.append(guid_el.text.strip())
    return guids
