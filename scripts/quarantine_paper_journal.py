"""Inventory and copy known test-contaminated PaperJournal rows.

The source journal is never modified. Suspect rows are selected only when they
match the historical Mangala contract-test fixtures and lack provenance.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

TEST_FIXTURE_SIGNATURES = {
    ("AAPL", 100.0, 1.0),
    ("AAPL", 100.0, 10.0),
    ("AAPL", 100.1234, 3.0),
    ("AAPL", 150.0, 10.0),
    ("AAPL", 155.0, 10.0),
    ("GOOGL", 50.0, 10.0),
    ("GOOGL", 150.0, 2.0),
    ("MSFT", 200.0, 5.0),
}


def is_known_test_contamination(row: dict[str, Any]) -> bool:
    """Return True only for an unprovenanced historical Mangala test row."""

    trade_id = str(row.get("trade_id") or "")
    if not trade_id.startswith("mangala-") or row.get("provenance"):
        return False
    try:
        signature = (
            str(row.get("ticker") or "").upper(),
            float(row["entry_price"]),
            float(row["shares"]),
        )
    except (KeyError, TypeError, ValueError):
        return False
    return signature in TEST_FIXTURE_SIGNATURES


def quarantine(source: Path, output_dir: Path) -> dict[str, Any]:
    """Copy matching rows and a manifest while preserving the source bytes."""

    source_bytes = source.read_bytes()
    source_sha256 = hashlib.sha256(source_bytes).hexdigest()
    rows: list[dict[str, Any]] = []
    for raw_line in source_bytes.decode("utf-8").splitlines():
        try:
            row = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and is_known_test_contamination(row):
            rows.append(row)

    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"paper_journal-test-contamination-{source_sha256[:12]}"
    records_path = output_dir / f"{stem}.jsonl"
    manifest_path = output_dir / f"{stem}.manifest.json"
    records_payload = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
    records_path.write_text(records_payload, encoding="utf-8")
    records_sha256 = hashlib.sha256(records_payload.encode("utf-8")).hexdigest()
    manifest = {
        "classification": "known_mangala_contract_test_contamination",
        "source": str(source.resolve()),
        "source_sha256_before": source_sha256,
        "source_sha256_after": hashlib.sha256(source.read_bytes()).hexdigest(),
        "source_modified": False,
        "selection": {
            "requires_missing_provenance": True,
            "requires_trade_id_prefix": "mangala-",
            "fixture_signatures": sorted(TEST_FIXTURE_SIGNATURES),
        },
        "record_count": len(rows),
        "records_file": str(records_path.resolve()),
        "records_sha256": records_sha256,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return {**manifest, "manifest_file": str(manifest_path.resolve())}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    print(json.dumps(quarantine(args.source, args.output_dir), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
