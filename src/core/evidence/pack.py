"""C1 EvidencePack — shadow contract. Does not steer pipeline decisions.

Canonical JSON + SHA-256 so the same facts always seal to the same digest.
C2 will freeze Snapshot.numbers from this pack; C3 will bind Bob to it.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from core.storage.atomic import atomic_write_text

SCHEMA_VERSION = "c1.1"
PACK_FILENAME = "evidence_pack.json"

FactStatus = Literal["OK", "STALE", "MISSING", "ERROR"]
PackStatus = Literal["COMPLETE", "PARTIAL", "INSUFFICIENT"]

_HASH_EXCLUDE = frozenset({"integrity"})


def canonical_json(payload: Any) -> str:
    """Stable JSON: sorted keys, no extra whitespace, UTF-8 text."""
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def payload_for_hash(pack: dict[str, Any]) -> dict[str, Any]:
    """Drop the integrity block so sealing is a pure function of facts."""
    return {key: value for key, value in pack.items() if key not in _HASH_EXCLUDE}


def seal_pack(pack: dict[str, Any], *, writer: str = "evidence.pack") -> dict[str, Any]:
    """Return a copy with integrity.canonical_json_sha256 filled."""
    sealed = dict(pack)
    digest = sha256_hex(canonical_json(payload_for_hash(sealed)))
    sealed["integrity"] = {
        "canonical_json_sha256": digest,
        "writer": writer,
        "schema_version": SCHEMA_VERSION,
    }
    return sealed


def pack_digest(pack: dict[str, Any]) -> str:
    integrity = pack.get("integrity") or {}
    digest = integrity.get("canonical_json_sha256")
    if not isinstance(digest, str) or len(digest) != 64:
        raise ValueError("EvidencePack is not sealed")
    return digest


def verify_pack_seal(pack: dict[str, Any]) -> bool:
    expected = sha256_hex(canonical_json(payload_for_hash(pack)))
    return pack_digest(pack) == expected


def save_evidence_pack(pack: dict[str, Any], dest_dir: Any) -> Any:
    """Atomic write of the sealed pack next to the existing evidence run."""
    from pathlib import Path

    directory = Path(dest_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / PACK_FILENAME
    atomic_write_text(path, canonical_json(pack) + "\n", encoding="utf-8")
    return path
