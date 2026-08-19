"""Compatibility decision logger backed by the active decision trace system."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.audit.decision_trace import DecisionTraceLogger


class DecisionLogger:
    """Small audit-log facade used by gateway and legacy contracts."""

    def __init__(self, output_dir: str | Path | None = None) -> None:
        self._trace = DecisionTraceLogger(output_dir=output_dir)

    def record_decision(
        self,
        run_id: str,
        step: str,
        decision: str,
        rationale: dict[str, Any],
    ) -> None:
        token = self._trace.start_node(
            run_id=str(run_id or "unknown"),
            node=str(step or "decision"),
            agent="decision_logger",
            payload={"rationale": rationale or {}},
        )
        self._trace.end_node(
            token,
            decision=str(decision or ""),
            reason=str((rationale or {}).get("reason") or ""),
            payload={"rationale": rationale or {}},
            agent="decision_logger",
        )

    def flush(self) -> None:
        return None
