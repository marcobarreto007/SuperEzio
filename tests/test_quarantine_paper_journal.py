from __future__ import annotations

import json
from pathlib import Path

from scripts.quarantine_paper_journal import is_known_test_contamination, quarantine


def _row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "trade_id": "mangala-AAPL-1",
        "ticker": "AAPL",
        "entry_price": 100.0,
        "shares": 10.0,
    }
    row.update(overrides)
    return row


def test_selector_is_fail_closed() -> None:
    assert is_known_test_contamination(_row()) is True
    assert is_known_test_contamination(_row(provenance="operator")) is False
    assert is_known_test_contamination(_row(ticker="TD")) is False
    assert is_known_test_contamination(_row(trade_id="manual-AAPL-1")) is False


def test_quarantine_copies_without_modifying_source(tmp_path: Path) -> None:
    source = tmp_path / "paper_journal.jsonl"
    rows = [_row(), _row(provenance="operator"), _row(ticker="TD")]
    source.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    before = source.read_bytes()

    manifest = quarantine(source, tmp_path / "quarantine")

    assert source.read_bytes() == before
    assert manifest["source_modified"] is False
    assert manifest["record_count"] == 1
    assert manifest["source_sha256_before"] == manifest["source_sha256_after"]
