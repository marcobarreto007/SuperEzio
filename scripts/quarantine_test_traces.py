"""Recoverably remove a bounded pytest trace interval from an operator JSONL file."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any


def _parse_timestamp(row: dict[str, Any]) -> datetime | None:
    try:
        return datetime.fromisoformat(str(row.get("timestamp") or "").replace("Z", "+00:00"))
    except ValueError:
        return None


def quarantine_test_interval(source: Path, output_dir: Path, since: datetime) -> dict[str, Any]:
    """Quarantine test-labelled rows on/after ``since`` and atomically keep all others."""

    source_bytes = source.read_bytes()
    source_sha256 = hashlib.sha256(source_bytes).hexdigest()
    kept: list[str] = []
    removed: list[dict[str, Any]] = []
    for line in source_bytes.decode("utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            kept.append(line)
            continue
        timestamp = _parse_timestamp(row) if isinstance(row, dict) else None
        run_id = str(row.get("run_id") or "").lower() if isinstance(row, dict) else ""
        if timestamp is not None and timestamp >= since and "test" in run_id:
            removed.append(row)
        else:
            kept.append(line)

    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"decision-trace-pytest-{source_sha256[:12]}"
    quarantine_path = output_dir / f"{stem}.jsonl"
    manifest_path = output_dir / f"{stem}.manifest.json"
    quarantine_payload = "".join(json.dumps(row, sort_keys=True) + "\n" for row in removed)
    quarantine_path.write_text(quarantine_payload, encoding="utf-8")
    kept_payload = "".join(f"{line}\n" for line in kept)
    temporary = source.with_suffix(source.suffix + ".cleaning")
    temporary.write_text(kept_payload, encoding="utf-8")
    os.replace(temporary, source)
    manifest = {
        "classification": "pytest_decision_trace_contamination",
        "source": str(source.resolve()),
        "source_sha256_before": source_sha256,
        "source_sha256_after": hashlib.sha256(source.read_bytes()).hexdigest(),
        "since": since.isoformat(),
        "removed_count": len(removed),
        "quarantine_file": str(quarantine_path.resolve()),
        "quarantine_sha256": hashlib.sha256(quarantine_payload.encode("utf-8")).hexdigest(),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return {**manifest, "manifest_file": str(manifest_path.resolve())}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--since", required=True)
    args = parser.parse_args()
    since = datetime.fromisoformat(args.since.replace("Z", "+00:00"))
    if since.tzinfo is None:
        raise SystemExit("--since must include a timezone")
    print(json.dumps(quarantine_test_interval(args.source, args.output_dir, since), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
