"""Append-only market event ledger. Hot path never rewrites the file."""

from __future__ import annotations

import json
import logging
import os
import threading
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.heart.raw_recorder import _file_lock

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class MarketEvent:
    identity: str
    source: str
    event_type: str
    occurred_at: datetime
    timestamp_precision: str
    symbol: str | None = None
    mic_code: str | None = None

    def to_row(self) -> dict[str, Any]:
        row = asdict(self)
        row["occurred_at"] = self.occurred_at.astimezone(UTC).isoformat()
        return row

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> MarketEvent:
        occurred = datetime.fromisoformat(str(row["occurred_at"]))
        if occurred.tzinfo is None:
            occurred = occurred.replace(tzinfo=UTC)
        return cls(
            identity=str(row["identity"]),
            source=str(row["source"]),
            event_type=str(row["event_type"]),
            occurred_at=occurred,
            timestamp_precision=str(row["timestamp_precision"]),
            symbol=row.get("symbol"),
            mic_code=row.get("mic_code"),
        )


@dataclass(frozen=True, slots=True)
class AppendResult:
    written: bool


class EventBook:
    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._lock = threading.RLock()
        self._identities: set[str] | None = None

    def append(self, event: MarketEvent) -> AppendResult:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if event.identity in self._known_identities():
            return AppendResult(written=False)
        self._quarantine_corrupt_lines()
        payload = json.dumps(event.to_row(), ensure_ascii=False) + "\n"
        with self._lock, _file_lock(self._path), open(self._path, "a", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        self._known_identities().add(event.identity)
        return AppendResult(written=True)

    def ingest_many(self, events: Sequence[MarketEvent]) -> int:
        written = 0
        for event in events:
            if self.append(event).written:
                written += 1
        return written

    def read_all(self) -> list[MarketEvent]:
        events: list[MarketEvent] = []
        for row in self._iter_rows():
            events.append(MarketEvent.from_row(row))
        return events

    def _known_identities(self) -> set[str]:
        if self._identities is None:
            self._identities = {row["identity"] for row in self._iter_rows() if "identity" in row}
        return self._identities

    def _iter_rows(self) -> list[dict[str, Any]]:
        if not self._path.exists():
            return []
        rows: list[dict[str, Any]] = []
        with open(self._path, encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict):
                    rows.append(payload)
        return rows

    def _quarantine_corrupt_lines(self) -> None:
        if not self._path.exists():
            return
        quarantine = self._path.with_name(self._path.name + ".quarantine")
        with self._lock, _file_lock(self._path), open(self._path, encoding="utf-8") as handle:
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
                        logger.exception("Could not quarantine corrupt event line")
