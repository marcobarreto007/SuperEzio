"""Offline tests for signal ledger scripts (no network)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "scripts" / "signal_ledger"


@pytest.mark.skip(reason="signal_ledger scripts removed in cleanup")
def test_append_sample_produces_official_emit(tmp_path):
    sample = ROOT / "data" / "signals" / "inbox" / "sample-aapl-official.ndjson"
    out = tmp_path / "emitted.jsonl"
    cmd = [
        sys.executable,
        str(LEDGER / "append_from_ndjson.py"),
        str(sample),
        "--out",
        str(out),
        "--traces",
        str(ROOT / "data" / "traces"),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(LEDGER))
    assert proc.returncode == 0, proc.stderr
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["record_type"] == "signal_emit"
    assert record["status"] == "official"
    assert record["action"] == "LONG"
    assert record["ticker"] == "AAPL"
    assert record["evidence"]["reference_price"] == 302.25


@pytest.mark.skip(reason="signal_ledger scripts removed in cleanup")
def test_report_empty_ledger(tmp_path):
    emitted = tmp_path / "emitted.jsonl"
    emitted.write_text("", encoding="utf-8")
    cmd = [
        sys.executable,
        str(LEDGER / "report_signals.py"),
        "--emitted",
        str(emitted),
        "--resolutions",
        str(tmp_path / "resolutions.jsonl"),
        "--json",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(LEDGER))
    assert proc.returncode == 0
    report = json.loads(proc.stdout)
    assert report["emitted_total"] == 0
