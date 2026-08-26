"""Coletor de dados via subprocesso Python isolado.

Estratégia de isolamento: evita nested event loops lançando um processo filho
com DataCollector().collect_all().
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.ports.data_collector import DataCollectorPort


class SubprocessDataCollector(DataCollectorPort):
    """Implementa DataCollectorPort via subprocess.run."""

    def __init__(self, project_root: Path, executable: str | None = None):
        self.project_root = Path(project_root)
        self.executable = executable or sys.executable

    # ------------------------------------------------------------------
    # DataCollectorPort
    # ------------------------------------------------------------------

    async def collect_all(self, ticker: str, timeout: float) -> dict[str, Any]:
        child_timeout = max(5.0, float(timeout))
        code = r"""
import asyncio
import json
import sys

from core.data_collector import DataCollector, detect_market

async def main():
    ticker = sys.argv[1]
    timeout = float(sys.argv[2])
    data = await DataCollector().collect_all(ticker, timeout=timeout)
    print("__SUPEREZIO_JSON__" + json.dumps(data, ensure_ascii=False, default=str))

if __name__ == "__main__":
    asyncio.run(main())
"""
        env = os.environ.copy()
        src_path = str(self.project_root / "src")
        env["PYTHONPATH"] = src_path + os.pathsep + env.get("PYTHONPATH", "")
        env.setdefault("DISABLE_OTEL", "1")

        try:
            completed = subprocess.run(  # noqa: ASYNC221 — coletor síncrono deliberado; migrar para asyncio é trabalho separado
                [
                    self.executable,
                    "-c",
                    code,
                    ticker,
                    str(max(3.0, child_timeout - 2.0)),
                ],
                cwd=str(self.project_root),
                env=env,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=child_timeout + 5.0,
                check=False,  # falha é diagnosticada via stdout/stderr/returncode abaixo, não via exceção
            )
        except subprocess.TimeoutExpired:
            return _timeout_data(ticker, child_timeout)

        for line in reversed((completed.stdout or "").splitlines()):
            if line.startswith("__SUPEREZIO_JSON__"):
                try:
                    return json.loads(line.removeprefix("__SUPEREZIO_JSON__"))
                except json.JSONDecodeError as exc:
                    return _error_data(ticker, f"collector_json_parse: {exc}")

        stderr = (completed.stderr or "").strip()
        stdout = (completed.stdout or "").strip()
        detail = stderr or stdout or f"collector exited with code {completed.returncode}"
        return _error_data(ticker, detail[:800])

    async def run_scan(self, message: str, filters: dict[str, Any]) -> dict[str, Any]:
        # placeholder: scan ainda é orquestrado diretamente pelo pipeline
        # quando extrairmos o scanner, movemos para cá.
        raise NotImplementedError("run_scan ainda não migrado para adapter")


# ------------------------------------------------------------------
# Helpers estáticos
# ------------------------------------------------------------------


def _timeout_data(ticker: str, timeout_s: float) -> dict[str, Any]:
    now = datetime.now(UTC).isoformat()
    return {
        "analysis_id": f"{ticker}-{uuid.uuid4().hex[:12]}",
        "ticker": ticker,
        "market": "UNKNOWN",
        "collected_at": now,
        "data_quality": "timeout",
        "source_errors": ["collector_timeout"],
        "technicals": {"error": f"collector hard timeout after {timeout_s}s"},
        "realtime_price": {"error": f"collector hard timeout after {timeout_s}s"},
    }


def _error_data(ticker: str, detail: str) -> dict[str, Any]:
    now = datetime.now(UTC).isoformat()
    return {
        "analysis_id": f"{ticker}-{uuid.uuid4().hex[:12]}",
        "ticker": ticker,
        "market": "UNKNOWN",
        "collected_at": now,
        "data_quality": "error",
        "source_errors": ["collector_error"],
        "technicals": {"error": detail},
        "realtime_price": {"error": detail},
    }
