from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from scripts.quarantine_test_traces import quarantine_test_interval


def test_quarantine_removes_only_bounded_test_rows(tmp_path: Path) -> None:
    source = tmp_path / "trace.jsonl"
    rows = [
        {"run_id": "operator", "timestamp": "2026-08-19T04:00:01+00:00"},
        {"run_id": "old-test", "timestamp": "2026-08-19T03:00:00+00:00"},
        {"run_id": "new-test", "timestamp": "2026-08-19T04:00:00+00:00"},
    ]
    source.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    manifest = quarantine_test_interval(
        source,
        tmp_path / "quarantine",
        datetime(2026, 8, 19, 3, 57, tzinfo=timezone.utc),
    )

    remaining = [json.loads(line) for line in source.read_text().splitlines()]
    assert [row["run_id"] for row in remaining] == ["operator", "old-test"]
    assert manifest["removed_count"] == 1
