"""MRI Registry — append-only event log for a single scan.

Phase 1: instrumentation only. No behavior change to the scan itself.
Every stage emits started/heartbeat/completed/failed events that
prove the pipeline is alive, even when providers are slow.

Contract: docs/architecture/SCANNER_MRI_CONTRACT.md
"""

from __future__ import annotations

import time
from typing import Any


class ScanEventRegistry:
    """Append-only event log for one scan.

    Created at scan INIT. Every stage pushes events via emit().
    Serialized into scan_trace in the final result.

    This is the source of truth for "onde o sangue parou."
    """

    def __init__(self, scan_id: str, *, writer: Any = None) -> None:
        self.scan_id = scan_id
        self.events: list[dict[str, Any]] = []
        self._started_at = time.monotonic()
        self._finished_at: float | None = None
        self._writer = writer  # LangGraph stream writer, if available

    # ── public API ────────────────────────────────────────────────────────

    def emit(
        self,
        stage: str,
        status: str,
        *,
        provider: str | None = None,
        counts: dict[str, int | None] | None = None,
        error: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Push a SCAN_EVENT to the log and optionally to the UI stream."""
        event: dict[str, Any] = {
            "type": "SCAN_EVENT",
            "scan_id": self.scan_id,
            "stage": stage,
            "provider": provider,
            "status": status,
            "elapsed_ms": self.elapsed_ms(),
            "counts": counts or {"total": None, "done": None, "errors": None},
            "error": error,
            "data": data,
        }
        self.events.append(event)

        if self._writer is not None:
            self._writer(event)

        return event

    def stage_started(self, stage: str, *, provider: str | None = None) -> dict[str, Any]:
        return self.emit(stage, "started", provider=provider)

    def stage_heartbeat(
        self,
        stage: str,
        *,
        provider: str | None = None,
        done: int = 0,
        total: int = 0,
        errors: int = 0,
    ) -> dict[str, Any]:
        return self.emit(
            stage,
            "heartbeat",
            provider=provider,
            counts={"total": total, "done": done, "errors": errors},
        )

    def stage_completed(
        self,
        stage: str,
        *,
        provider: str | None = None,
        done: int = 0,
        total: int = 0,
        errors: int = 0,
    ) -> dict[str, Any]:
        return self.emit(
            stage,
            "completed",
            provider=provider,
            counts={"total": total, "done": done, "errors": errors},
        )

    def stage_failed(
        self,
        stage: str,
        error: str,
        *,
        provider: str | None = None,
        done: int = 0,
        total: int = 0,
        errors: int = 0,
    ) -> dict[str, Any]:
        return self.emit(
            stage,
            "failed",
            provider=provider,
            counts={"total": total, "done": done, "errors": errors},
            error=error,
        )

    # ── queries ───────────────────────────────────────────────────────────

    def elapsed_ms(self) -> int:
        return int((time.monotonic() - self._started_at) * 1000)

    def snapshot(self) -> dict[str, Any]:
        return {
            "scan_id": self.scan_id,
            "started_at": self._started_at,
            "finished_at": self._finished_at,
            "elapsed_ms": self.elapsed_ms(),
            "event_count": len(self.events),
            "stages_seen": sorted({e["stage"] for e in self.events}),
            "failed_stages": sorted({e["stage"] for e in self.events if e["status"] == "failed"}),
        }

    def failing_stage(self) -> str | None:
        for event in reversed(self.events):
            if event["status"] == "failed":
                return str(event["stage"])
        return None

    def as_trace(self) -> dict[str, Any]:
        return {
            "scan_id": self.scan_id,
            "elapsed_ms": self.elapsed_ms(),
            "event_count": len(self.events),
            "stages": [
                {
                    "stage": e["stage"],
                    "status": e["status"],
                    "provider": e["provider"],
                    "elapsed_ms": e["elapsed_ms"],
                    "counts": e["counts"],
                    "error": e.get("error"),
                }
                for e in self.events
            ],
        }
