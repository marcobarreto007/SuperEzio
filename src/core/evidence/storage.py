"""Save evidence artifacts to disk."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .run import EvidenceRun


def save_evidence(run: EvidenceRun) -> Path:
    """Save all evidence artifacts to runs/evidence/{run_id}/."""
    run_dir = run.run_dir
    run_dir.mkdir(parents=True, exist_ok=True)

    _write_json(
        run_dir / "analysis.json",
        {
            "run_id": run.run_id,
            "created_at": run.created_at,
            "prompt": run.prompt,
            "ticker": run.ticker,
            "response": run.response,
            "price_at_analysis": run.price_at_analysis,
        },
    )

    _write_json(
        run_dir / "sources.json",
        {
            "sources": run.sources,
            "candidates": run.candidates,
        },
    )

    _write_json(run_dir / "experts.json", run.experts)
    _write_json(run_dir / "risk.json", run.risk)
    _write_json(
        run_dir / "trace.json",
        {
            "timeline": run.timeline,
            "errors": run.errors,
        },
    )
    _write_json(run_dir / "pipeline.json", run.to_dict())

    return run_dir


def _write_json(path: Path, data: dict[str, Any]) -> None:
    """Write JSON with consistent formatting."""
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
