"""Stable item identities: GUID when present, else SHA-256 of the body."""

from __future__ import annotations

import hashlib


def item_identity(body: bytes, guid: str | None) -> str:
    if guid:
        return guid
    return "sha256:" + hashlib.sha256(body).hexdigest()
