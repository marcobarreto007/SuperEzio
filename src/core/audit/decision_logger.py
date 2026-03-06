"""Audit trail de decisões — implementação em JSONL.

Persiste registros imutáveis explicando *por que* cada decisão foi tomada
no pipeline, gateway e agent selector.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..ports.audit_log import AuditLogPort


class DecisionLogger(AuditLogPort):
    """Logger de decisões em JSONL.

    Args:
        output_dir: diretório onde os arquivos .jsonl serão escritos.
        buffer_size: quantidade de registros a bufferizar antes de flush.
    """

    def __init__(self, output_dir: Path | str | None = None, buffer_size: int = 10):
        self.output_dir = Path(output_dir) if output_dir else Path("data/runs")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._buffer: list[dict[str, Any]] = []
        self._buffer_size = max(1, buffer_size)

    def record_decision(
        self,
        run_id: str,
        step: str,
        decision: str,
        rationale: dict[str, Any],
    ) -> None:
        entry = {
            "run_id": run_id,
            "step": step,
            "decision": decision,
            "rationale": rationale,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._buffer.append(entry)
        if len(self._buffer) >= self._buffer_size:
            self.flush()

    def flush(self) -> None:
        if not self._buffer:
            return
        # arquivo por dia para facilitar auditoria
        fname = self.output_dir / f"audit_{datetime.now(timezone.utc):%Y%m%d}.jsonl"
        with open(fname, "a", encoding="utf-8") as fh:
            for entry in self._buffer:
                fh.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
        self._buffer.clear()
