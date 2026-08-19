"""Persistent broker-neutral state for trade tickets and safety gates."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from core.paths import resolve_project_path


DEFAULT_WORKFLOW_DB = resolve_project_path("runtime/trading_state.sqlite3")
DEFAULT_DEAD_LETTER_DIR = resolve_project_path("journal/dead_letter")
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")


class WorkflowStoreError(RuntimeError):
    """Raised when durable trading state cannot be safely read or changed."""


class WorkflowConflictError(WorkflowStoreError):
    """Raised when a state transition does not match current durable state."""


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve_workflow_db_path() -> Path:
    configured = os.getenv("SUPEREZIO_TRADING_STATE_DB", "").strip()
    return Path(configured).resolve() if configured else DEFAULT_WORKFLOW_DB


class TradeWorkflowStore:
    """SQLite source of truth with cross-process uniqueness guarantees."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path).resolve() if path is not None else resolve_workflow_db_path()
        if os.getenv("PYTEST_CURRENT_TEST") and self.path == DEFAULT_WORKFLOW_DB:
            raise WorkflowStoreError(
                "Tests may not open the operator trading-state database; inject a temporary path"
            )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    def _initialize(self) -> None:
        with self._lock, self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode = WAL;
                CREATE TABLE IF NOT EXISTS trade_tickets (
                    ticket_id TEXT PRIMARY KEY,
                    fingerprint TEXT NOT NULL UNIQUE,
                    broker TEXT NOT NULL,
                    status TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    submitted_to_broker INTEGER NOT NULL CHECK (submitted_to_broker IN (0, 1)),
                    record_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1
                );
                CREATE TABLE IF NOT EXISTS workflow_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_key TEXT NOT NULL UNIQUE,
                    ticket_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    from_status TEXT,
                    to_status TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(ticket_id) REFERENCES trade_tickets(ticket_id)
                );
                CREATE TABLE IF NOT EXISTS approvals (
                    approval_id TEXT PRIMARY KEY,
                    ticket_id TEXT UNIQUE,
                    ticket_fingerprint TEXT,
                    status TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    resolved_at REAL NOT NULL DEFAULT 0,
                    resolved_by TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY(ticket_id) REFERENCES trade_tickets(ticket_id)
                );
                CREATE TABLE IF NOT EXISTS system_state (
                    state_key TEXT PRIMARY KEY,
                    state_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS dead_letters (
                    dead_letter_id TEXT PRIMARY KEY,
                    category TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    error TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(category, idempotency_key)
                );
                """
            )

    @staticmethod
    def _decode_ticket(row: sqlite3.Row) -> dict[str, Any]:
        record = json.loads(row["record_json"])
        record.update(
            {
                "ticket_id": row["ticket_id"],
                "fingerprint": row["fingerprint"],
                "status": row["status"],
                "phase": row["phase"],
                "submitted_to_broker": bool(row["submitted_to_broker"]),
                "workflow_version": row["version"],
                "workflow_updated_at": row["updated_at"],
            }
        )
        return record

    def create_ticket(self, ticket: Mapping[str, Any]) -> tuple[dict[str, Any], bool]:
        """Persist one immutable ticket intent; return the existing row on retry."""

        ticket_id = str(ticket.get("ticket_id") or "").strip()
        fingerprint = str(ticket.get("fingerprint") or "").strip().lower()
        broker = str(ticket.get("broker") or "UNKNOWN").strip().upper()
        status = str(ticket.get("status") or "DRAFT").strip().upper()
        phase = str(ticket.get("phase") or "draft").strip()
        if not ticket_id:
            raise WorkflowStoreError("ticket_id is required")
        if not _HEX_64.fullmatch(fingerprint):
            raise WorkflowStoreError("fingerprint must be a 64-character lowercase SHA-256")
        if ticket.get("submitted_to_broker") is not False:
            raise WorkflowStoreError(
                "new tickets must explicitly declare submitted_to_broker=false"
            )

        now = _utc_now()
        record_json = _canonical_json(ticket)
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM trade_tickets WHERE fingerprint = ?", (fingerprint,)
            ).fetchone()
            if existing is not None:
                connection.commit()
                return self._decode_ticket(existing), False
            id_collision = connection.execute(
                "SELECT fingerprint FROM trade_tickets WHERE ticket_id = ?", (ticket_id,)
            ).fetchone()
            if id_collision is not None:
                connection.rollback()
                raise WorkflowConflictError("ticket_id already belongs to another fingerprint")
            connection.execute(
                """
                INSERT INTO trade_tickets(
                    ticket_id, fingerprint, broker, status, phase,
                    submitted_to_broker, record_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?)
                """,
                (ticket_id, fingerprint, broker, status, phase, record_json, now, now),
            )
            connection.execute(
                """
                INSERT INTO workflow_events(
                    event_key, ticket_id, event_type, from_status, to_status,
                    actor, details_json, created_at
                ) VALUES (?, ?, 'ticket_created', NULL, ?, 'system', '{}', ?)
                """,
                (f"ticket-created:{fingerprint}", ticket_id, status, now),
            )
            connection.commit()
        stored = self.get_ticket(ticket_id)
        if stored is None:  # pragma: no cover - SQLite committed but failed to read
            raise WorkflowStoreError("ticket disappeared after commit")
        return stored, True

    def get_ticket(self, ticket_id: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM trade_tickets WHERE ticket_id = ?", (ticket_id,)
            ).fetchone()
        return self._decode_ticket(row) if row is not None else None

    def list_tickets(self, *, limit: int = 200) -> list[dict[str, Any]]:
        bounded_limit = max(1, min(int(limit), 1000))
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM trade_tickets ORDER BY created_at DESC LIMIT ?", (bounded_limit,)
            ).fetchall()
        return [self._decode_ticket(row) for row in rows]

    def transition_ticket(
        self,
        ticket_id: str,
        *,
        expected_status: str,
        new_status: str,
        new_phase: str,
        actor: str,
        idempotency_key: str,
        details: Mapping[str, Any] | None = None,
        submitted_to_broker: bool = False,
    ) -> dict[str, Any]:
        """Atomically apply one named transition, idempotent across processes."""

        if not idempotency_key.strip() or not actor.strip():
            raise WorkflowStoreError("actor and idempotency_key are required")
        event_key = f"transition:{ticket_id}:{idempotency_key.strip()}"
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            prior_event = connection.execute(
                "SELECT 1 FROM workflow_events WHERE event_key = ?", (event_key,)
            ).fetchone()
            row = connection.execute(
                "SELECT * FROM trade_tickets WHERE ticket_id = ?", (ticket_id,)
            ).fetchone()
            if row is None:
                connection.rollback()
                raise WorkflowStoreError(f"unknown ticket: {ticket_id}")
            if prior_event is not None:
                connection.commit()
                return self._decode_ticket(row)
            if str(row["status"]).upper() != expected_status.strip().upper():
                connection.rollback()
                raise WorkflowConflictError(
                    f"ticket status is {row['status']}, expected {expected_status}"
                )
            record = json.loads(row["record_json"])
            record["status"] = new_status.strip().upper()
            record["phase"] = new_phase.strip()
            record["submitted_to_broker"] = bool(submitted_to_broker)
            now = _utc_now()
            connection.execute(
                """
                UPDATE trade_tickets
                SET status = ?, phase = ?, submitted_to_broker = ?, record_json = ?,
                    updated_at = ?, version = version + 1
                WHERE ticket_id = ?
                """,
                (
                    record["status"],
                    record["phase"],
                    int(bool(submitted_to_broker)),
                    _canonical_json(record),
                    now,
                    ticket_id,
                ),
            )
            connection.execute(
                """
                INSERT INTO workflow_events(
                    event_key, ticket_id, event_type, from_status, to_status,
                    actor, details_json, created_at
                ) VALUES (?, ?, 'status_transition', ?, ?, ?, ?, ?)
                """,
                (
                    event_key,
                    ticket_id,
                    row["status"],
                    record["status"],
                    actor.strip(),
                    _canonical_json(details or {}),
                    now,
                ),
            )
            connection.commit()
        updated = self.get_ticket(ticket_id)
        if updated is None:  # pragma: no cover
            raise WorkflowStoreError("ticket disappeared after transition")
        return updated

    def save_system_state(self, state_key: str, state: Mapping[str, Any]) -> None:
        if not state_key.strip():
            raise WorkflowStoreError("state_key is required")
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO system_state(state_key, state_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(state_key) DO UPDATE SET
                    state_json = excluded.state_json,
                    updated_at = excluded.updated_at
                """,
                (state_key.strip(), _canonical_json(state), _utc_now()),
            )
            connection.commit()

    def load_system_state(self, state_key: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT state_json FROM system_state WHERE state_key = ?", (state_key.strip(),)
            ).fetchone()
        return json.loads(row["state_json"]) if row is not None else None

    def record_dead_letter(
        self,
        *,
        category: str,
        idempotency_key: str,
        payload: Mapping[str, Any],
        error: str,
        output_dir: str | Path | None = None,
    ) -> Path:
        """Persist a deduplicated failed write in SQLite and as replayable JSON."""

        canonical_payload = _canonical_json(payload)
        identity = f"{category}|{idempotency_key}|{canonical_payload}"
        dead_letter_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        created_at = _utc_now()
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO dead_letters(
                    dead_letter_id, category, idempotency_key, payload_json,
                    error, status, created_at
                ) VALUES (?, ?, ?, ?, ?, 'pending_manual_replay', ?)
                """,
                (
                    dead_letter_id,
                    category.strip(),
                    idempotency_key.strip(),
                    canonical_payload,
                    str(error)[:1000],
                    created_at,
                ),
            )
            connection.commit()
        target_dir = (
            Path(output_dir)
            if output_dir is not None
            else Path(os.getenv("SUPEREZIO_DEAD_LETTER_DIR", "") or DEFAULT_DEAD_LETTER_DIR)
        )
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{dead_letter_id}.json"
        body = {
            "dead_letter_id": dead_letter_id,
            "category": category,
            "idempotency_key": idempotency_key,
            "payload": dict(payload),
            "error": str(error)[:1000],
            "status": "pending_manual_replay",
            "created_at": created_at,
        }
        if not target.exists():
            flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0)
            descriptor = os.open(target, flags, 0o600)
            try:
                encoded = (json.dumps(body, ensure_ascii=False, sort_keys=True) + "\n").encode(
                    "utf-8"
                )
                os.write(descriptor, encoded)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        return target


def get_trade_workflow_store() -> TradeWorkflowStore:
    """Open the configured durable workflow database."""

    return TradeWorkflowStore()
