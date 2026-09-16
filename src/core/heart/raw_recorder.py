"""Append-only dump of non-recoverable event feeds.

No business parsing. Duplicate bodies are skipped by SHA-256. HTTP 304 writes
nothing. Tests must not touch the production root.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import threading
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.heart.feeds import FeedSpec
from core.paths import project_path

logger = logging.getLogger(__name__)

DEFAULT_HEART_ROOT = project_path("data", "heart")

try:
    import msvcrt as _msvcrt
except ImportError:  # pragma: no cover
    _msvcrt = None


@contextlib.contextmanager
def _file_lock(path: Path):
    if _msvcrt is None:
        yield
        return
    lock_path = path.with_name(path.name + ".lock")
    if not lock_path.exists():
        lock_path.write_bytes(b"\0")
    with open(lock_path, "r+b") as handle:
        try:
            handle.seek(0)
            _msvcrt.locking(handle.fileno(), _msvcrt.LK_LOCK, 1)
            yield
        finally:
            try:
                _msvcrt.locking(handle.fileno(), _msvcrt.LK_UNLCK, 1)
            except OSError:
                pass


@dataclass(frozen=True, slots=True)
class RawCapture:
    status: int
    body: bytes = b""
    headers: Mapping[str, str] = field(default_factory=dict)
    captured_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class RecordResult:
    written: int
    skipped: int
    not_modified: bool
    captured_at: datetime
    body_sha256: str | None = None


class RawRecorder:
    def __init__(self, root: Path | None = None) -> None:
        self._root = Path(root) if root is not None else DEFAULT_HEART_ROOT
        self._lock = threading.RLock()
        self._seen: dict[str, set[str]] = {}

    def capture_path(self, feed_id: str, captured_at: datetime) -> Path:
        moment = _as_utc(captured_at)
        return (
            self._root
            / "raw"
            / f"{moment.year:04d}"
            / f"{moment.month:02d}"
            / f"{moment.day:02d}"
            / f"{feed_id}.jsonl"
        )

    def conditional_headers(self, feed: FeedSpec) -> dict[str, str]:
        state = self._load_state().get(feed.feed_id, {})
        headers: dict[str, str] = {}
        etag = state.get("etag")
        last_modified = state.get("last_modified")
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified
        return headers

    def record(self, feed: FeedSpec, *, capture: RawCapture) -> RecordResult:
        self._assert_write_allowed()
        captured_at = _as_utc(capture.captured_at or datetime.now(UTC))
        if capture.status == 304:
            return RecordResult(
                written=0,
                skipped=0,
                not_modified=True,
                captured_at=captured_at,
            )

        digest = hashlib.sha256(capture.body).hexdigest()
        if digest in self._seen_hashes(feed.feed_id):
            return RecordResult(
                written=0,
                skipped=1,
                not_modified=False,
                captured_at=captured_at,
                body_sha256=digest,
            )

        path = self.capture_path(feed.feed_id, captured_at)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._quarantine_corrupt_lines(path)
        row = {
            "feed_id": feed.feed_id,
            "url": feed.url,
            "http_status": capture.status,
            "captured_at": captured_at.isoformat(),
            "etag": _header(capture.headers, "ETag"),
            "last_modified": _header(capture.headers, "Last-Modified"),
            "body_sha256": digest,
            "body": _decode_body(capture.body),
        }
        payload = json.dumps(row, ensure_ascii=False) + "\n"
        with self._lock, _file_lock(path), open(path, "a", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        self._remember(feed.feed_id, digest)
        self._store_validators(feed.feed_id, capture.headers)
        return RecordResult(
            written=1,
            skipped=0,
            not_modified=False,
            captured_at=captured_at,
            body_sha256=digest,
        )

    def _assert_write_allowed(self) -> None:
        if self._root.resolve() == DEFAULT_HEART_ROOT.resolve() and os.getenv(
            "PYTEST_CURRENT_TEST"
        ):
            raise RuntimeError(
                f"pytest cannot write the production heart root at {DEFAULT_HEART_ROOT}"
            )

    def _index_path(self, feed_id: str) -> Path:
        return self._root / "index" / f"{feed_id}.sha256"

    def _state_path(self) -> Path:
        return self._root / "state.json"

    def _seen_hashes(self, feed_id: str) -> set[str]:
        cached = self._seen.get(feed_id)
        if cached is not None:
            return cached
        hashes: set[str] = set()
        index = self._index_path(feed_id)
        if index.exists():
            for line in index.read_text(encoding="utf-8").splitlines():
                value = line.strip()
                if value:
                    hashes.add(value)
        self._seen[feed_id] = hashes
        return hashes

    def _remember(self, feed_id: str, digest: str) -> None:
        self._seen_hashes(feed_id).add(digest)
        index = self._index_path(feed_id)
        index.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, _file_lock(index), open(index, "a", encoding="utf-8") as handle:
            handle.write(digest + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def _load_state(self) -> dict[str, Any]:
        path = self._state_path()
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            logger.warning("Heart state unreadable; starting empty")
            return {}
        feeds = payload.get("feeds")
        return feeds if isinstance(feeds, dict) else {}

    def _store_validators(self, feed_id: str, headers: Mapping[str, str]) -> None:
        etag = _header(headers, "ETag")
        last_modified = _header(headers, "Last-Modified")
        if not etag and not last_modified:
            return
        state = self._load_state()
        current = dict(state.get(feed_id) or {})
        if etag:
            current["etag"] = etag
        if last_modified:
            current["last_modified"] = last_modified
        state[feed_id] = current
        path = self._state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        with self._lock, _file_lock(path):
            tmp.write_text(
                json.dumps({"feeds": state}, indent=2) + "\n",
                encoding="utf-8",
            )
            os.replace(tmp, path)

    def _quarantine_corrupt_lines(self, path: Path) -> None:
        if not path.exists():
            return
        quarantine = path.with_name(path.name + ".quarantine")
        with self._lock, _file_lock(path), open(path, encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    json.loads(line)
                except json.JSONDecodeError:
                    try:
                        with open(quarantine, "a", encoding="utf-8") as dump:
                            dump.write(raw_line.rstrip("\n") + "\n")
                    except OSError:
                        logger.exception("Could not quarantine corrupt heart capture")


def _as_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def _header(headers: Mapping[str, str], name: str) -> str | None:
    wanted = name.lower()
    for key, value in headers.items():
        if key.lower() == wanted and str(value).strip():
            return str(value)
    return None


def _decode_body(body: bytes) -> str:
    return body.decode("utf-8", errors="replace")
