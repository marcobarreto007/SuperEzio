"""Decision trace logging and blame reports for pipeline guardrails."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.paths import resolve_project_path


# Thread lock for SQLite writes
_WRITE_LOCK = threading.Lock()

# Database path
DB_PATH = resolve_project_path("runtime/investor.db")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if hasattr(value, "model_dump"):
        return _json_safe(value.model_dump(mode="json"))
    if hasattr(value, "__dict__"):
        return _json_safe(vars(value))
    return str(value)


def _ensure_db_table(db_path: Path) -> None:
    """Create decision_traces table if not exists."""
    with _WRITE_LOCK:
        conn = sqlite3.connect(db_path)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS decision_traces (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trace_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    session_id TEXT,
                    node TEXT NOT NULL,
                    agent TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    latency_ms REAL,
                    decision TEXT,
                    confidence REAL,
                    evidence_refs TEXT,
                    errors TEXT,
                    overrides TEXT,
                    input_summary TEXT,
                    output_summary TEXT
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_traces_run ON decision_traces(run_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_traces_node ON decision_traces(node)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_traces_agent ON decision_traces(agent)")
            conn.commit()
        finally:
            conn.close()


def _write_trace_to_db(
    db_path: Path,
    trace_id: str,
    run_id: str,
    node: str,
    agent: str,
    latency_ms: float,
    decision: str | None,
    confidence: float | None,
    evidence_refs: list[str],
    errors: list[str],
    overrides: dict | None,
    input_summary: str,
    output_summary: str,
) -> None:
    """Write trace entry to SQLite database (thread-safe)."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    _ensure_db_table(db_path)

    with _WRITE_LOCK:
        conn = sqlite3.connect(db_path)
        try:
            conn.execute(
                """
                INSERT INTO decision_traces (
                    trace_id, run_id, session_id, node, agent,
                    timestamp, latency_ms, decision, confidence,
                    evidence_refs, errors, overrides,
                    input_summary, output_summary
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    trace_id,
                    run_id,
                    "",
                    node,
                    agent,
                    _utc_now(),
                    latency_ms,
                    decision,
                    confidence,
                    json.dumps(evidence_refs),
                    json.dumps(errors),
                    json.dumps(overrides) if overrides else None,
                    input_summary[:200],
                    output_summary[:500],
                ),
            )
            conn.commit()
        finally:
            conn.close()


def get_agent_stats(agent: str, days: int = 7, db_path: Path = DB_PATH) -> dict[str, Any]:
    """Get agent performance stats from database."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    _ensure_db_table(db_path)

    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.execute(
            """
            SELECT
                COUNT(*) as calls,
                AVG(latency_ms) as avg_latency,
                SUM(CASE WHEN errors IS NOT NULL AND errors != '[]' THEN 1 ELSE 0 END) as errors,
                AVG(confidence) as avg_confidence
            FROM decision_traces
            WHERE agent = ?
            AND datetime(timestamp) >= datetime('now', '-' || ? || ' days')
        """,
            (agent, days),
        )
        row = cursor.fetchone()

        if not row or row[0] == 0:
            return {
                "agent": agent,
                "calls": 0,
                "avg_latency_ms": 0,
                "error_rate": 0,
                "avg_confidence": 0,
            }

        return {
            "agent": agent,
            "calls": row[0],
            "avg_latency_ms": row[1] or 0,
            "error_rate": row[2] / row[0] if row[0] > 0 else 0,
            "avg_confidence": row[3] or 0,
        }
    finally:
        conn.close()


@dataclass
class TraceToken:
    run_id: str
    node: str
    layer: str = ""
    agent: str = ""
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    started_at: str = field(default_factory=_utc_now)
    perf_start: float = field(default_factory=time.perf_counter)


class DecisionTraceLogger:
    """Append-only JSONL trace with per-node start/end/error entries."""

    def __init__(self, output_dir: str | Path = "runtime/traces") -> None:
        self.output_dir = resolve_project_path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.entries: list[dict[str, Any]] = []

    @property
    def current_file(self) -> Path:
        return self.output_dir / f"decision_trace_{datetime.now(timezone.utc):%Y%m%d}.jsonl"

    def start_node(
        self,
        run_id: str,
        node: str,
        *,
        layer: str = "",
        agent: str = "",
        payload: dict[str, Any] | None = None,
    ) -> TraceToken:
        token = TraceToken(run_id=str(run_id or "unknown"), node=node, layer=layer, agent=agent)
        self._record(
            {
                "trace_id": token.trace_id,
                "run_id": token.run_id,
                "node": node,
                "layer": layer,
                "agent": agent,
                "phase": "start",
                "status": "started",
                "timestamp": token.started_at,
                "payload": payload or {},
            }
        )
        return token

    def end_node(
        self,
        token: TraceToken,
        *,
        status: str = "completed",
        decision: str = "",
        reason: str = "",
        payload: dict[str, Any] | None = None,
        agent: str = "",
        confidence: float | None = None,
        evidence_refs: list[str] | None = None,
        overrides: dict | None = None,
        errors: list[str] | None = None,
    ) -> dict[str, Any]:
        elapsed_ms = int((time.perf_counter() - token.perf_start) * 1000)
        entry = {
            "trace_id": token.trace_id,
            "run_id": token.run_id,
            "node": token.node,
            "layer": token.layer,
            "phase": "end",
            "status": status,
            "decision": decision,
            "reason": reason,
            "elapsed_ms": elapsed_ms,
            "timestamp": _utc_now(),
            "payload": payload or {},
            "confidence": confidence,
            "evidence_refs": evidence_refs or [],
            "overrides": overrides,
            "errors": errors or [],
        }
        self._record(entry)

        # Also write to SQLite for blame attribution
        try:
            _write_trace_to_db(
                db_path=DB_PATH,
                trace_id=token.trace_id,
                run_id=token.run_id,
                node=token.node,
                agent=agent or token.agent,
                latency_ms=elapsed_ms,
                decision=decision or None,
                confidence=confidence,
                evidence_refs=evidence_refs or [],
                errors=errors or [],
                overrides=overrides,
                input_summary=json.dumps(payload)[:200] if payload else "",
                output_summary=reason[:500],
            )
        except Exception:
            pass  # SQLite is optional backup

        return entry

    def skip_node(
        self,
        run_id: str,
        node: str,
        *,
        layer: str = "",
        reason: str = "",
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        token = self.start_node(run_id, node, layer=layer)
        return self.end_node(
            token,
            status="skipped",
            decision="SKIP",
            reason=reason,
            payload=payload,
        )

    def error_node(
        self,
        token: TraceToken,
        exc: Exception,
        *,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.end_node(
            token,
            status="error",
            decision="ERROR",
            reason=str(exc)[:300],
            payload=payload,
        )

    def blame_report(self, run_id: str) -> dict[str, Any]:
        entries = self.load_entries(run_id)
        end_entries = [entry for entry in entries if entry.get("phase") == "end"]
        blockers = [
            entry
            for entry in end_entries
            if str(entry.get("decision", "")).upper() in {"BLOCK", "REVIEW", "ERROR"}
            or entry.get("status") == "error"
        ]
        slowest = sorted(
            end_entries,
            key=lambda entry: int(entry.get("elapsed_ms") or 0),
            reverse=True,
        )[:5]

        # Collect overrides
        overrides = [entry for entry in end_entries if entry.get("overrides")]

        # Agent performance (from this run)
        agent_times: dict[str, list[int]] = {}
        for entry in end_entries:
            agent = entry.get("agent", "unknown")
            agent_times.setdefault(agent, []).append(entry.get("elapsed_ms", 0))

        agent_stats = [
            {
                "agent": agent,
                "avg_latency_ms": sum(times) / len(times) if times else 0,
                "calls": len(times),
            }
            for agent, times in sorted(agent_times.items())
        ]

        return {
            "run_id": run_id,
            "entries": entries,
            "summary": {
                "total_events": len(entries),
                "completed_nodes": sum(1 for e in end_entries if e.get("status") == "completed"),
                "skipped_nodes": sum(1 for e in end_entries if e.get("status") == "skipped"),
                "error_nodes": sum(1 for e in end_entries if e.get("status") == "error"),
                "blockers": len(blockers),
            },
            "blockers": blockers,
            "slowest_nodes": slowest,
            "overrides": overrides,
            "agent_stats": agent_stats,
        }

    def load_entries(self, run_id: str) -> list[dict[str, Any]]:
        run_id = str(run_id or "").strip()
        if not run_id:
            return list(self.entries)

        collected = [entry for entry in self.entries if entry.get("run_id") == run_id]
        for path in sorted(self.output_dir.glob("decision_trace_*.jsonl")):
            try:
                with path.open("r", encoding="utf-8") as fh:
                    for line in fh:
                        if not line.strip():
                            continue
                        entry = json.loads(line)
                        if entry.get("run_id") == run_id:
                            collected.append(entry)
            except (OSError, json.JSONDecodeError):
                continue

        seen: set[tuple[str, str, str]] = set()
        unique: list[dict[str, Any]] = []
        for entry in collected:
            key = (
                str(entry.get("trace_id", "")),
                str(entry.get("phase", "")),
                str(entry.get("timestamp", "")),
            )
            if key in seen:
                continue
            seen.add(key)
            unique.append(entry)
        return unique

    def _record(self, entry: dict[str, Any]) -> None:
        safe = _json_safe(entry)
        self.entries.append(safe)
        with self.current_file.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(safe, ensure_ascii=False, default=str) + "\n")
