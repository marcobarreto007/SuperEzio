"""Append-only local feedback storage for Bob responses."""

from __future__ import annotations

import glob
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_FEEDBACK_DIR = Path(os.getenv("SUPEREZIO_FEEDBACK_DIR", "runtime/feedback"))


def _resolve_feedback_dir() -> Path:
    feedback_dir = _FEEDBACK_DIR
    if not feedback_dir.is_absolute():
        feedback_dir = Path.cwd() / feedback_dir
    feedback_dir.mkdir(parents=True, exist_ok=True)
    return feedback_dir


def save_feedback(
    msg_id: str,
    rating: int,
    *,
    comment: str = "",
    trace: dict[str, Any] | None = None,
) -> Path:
    """Append a feedback entry to today's JSONL file."""
    entry = {
        "msg_id": msg_id,
        "rating": rating,
        "comment": comment,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "trace": trace or {},
    }
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = _resolve_feedback_dir() / f"feedback-{today}.jsonl"
    with path.open("a", encoding="utf-8") as feedback_file:
        feedback_file.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return path


def save(
    msg_id: str,
    rating: int,
    *,
    comment: str = "",
    trace: dict[str, Any] | None = None,
) -> Path:
    """Backward-compatible alias for save_feedback()."""
    return save_feedback(msg_id, rating, comment=comment, trace=trace)


def load_recent_feedback(days: int = 30) -> list[dict[str, Any]]:
    """Load valid feedback records newer than the requested window."""
    records: list[dict[str, Any]] = []
    cutoff = time.time() - days * 86400

    for feedback_path in sorted(glob.glob(str(_resolve_feedback_dir() / "feedback-*.jsonl"))):
        try:
            with open(feedback_path, encoding="utf-8") as feedback_file:
                for line in feedback_file:
                    record = _parse_recent_record(line, cutoff)
                    if record is not None:
                        records.append(record)
        except OSError:
            continue
    return records


def load_recent(days: int = 30) -> list[dict[str, Any]]:
    """Backward-compatible alias for load_recent_feedback()."""
    return load_recent_feedback(days=days)


def _parse_recent_record(line: str, cutoff: float) -> dict[str, Any] | None:
    stripped = line.strip()
    if not stripped:
        return None
    try:
        record = json.loads(stripped)
        timestamp = datetime.fromisoformat(record.get("timestamp", "")).timestamp()
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return record if timestamp > cutoff else None
