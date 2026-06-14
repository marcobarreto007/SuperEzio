"""Decision trace logging and blame reports for pipeline guardrails."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.paths import resolve_project_path


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


@dataclass
class TraceToken:
    run_id: str
    node: str
    layer: str = ""
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
        payload: dict[str, Any] | None = None,
    ) -> TraceToken:
        token = TraceToken(run_id=str(run_id or "unknown"), node=node, layer=layer)
        self._record(
            {
                "trace_id": token.trace_id,
                "run_id": token.run_id,
                "node": node,
                "layer": layer,
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
        }
        self._record(entry)
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
