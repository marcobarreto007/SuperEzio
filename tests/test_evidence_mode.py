from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from agent_server import endpoints
from core.evidence.report import generate_html_report
from core.evidence.run import EvidenceRun
from core.pipeline.graph import _scan_evidence_payload
import core.evidence.run as evidence_run_mod


def test_evidence_report_escapes_user_content(tmp_path: Path) -> None:
    run = EvidenceRun(prompt="<script>alert(1)</script>", ticker="AAPL")
    run.start()
    run.record_response("<b>not html</b>", tokens=2)
    run.finish()

    report_path = Path(generate_html_report(run, tmp_path))
    html = report_path.read_text(encoding="utf-8")

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<b>not html</b>" not in html
    assert "&lt;b&gt;not html&lt;/b&gt;" in html


def test_evidence_file_resolution_blocks_traversal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(evidence_run_mod, "EVIDENCE_DIR", tmp_path)
    run_dir = tmp_path / "20260603-122000_abc123"
    run_dir.mkdir()
    (run_dir / "report.html").write_text("<html></html>", encoding="utf-8")

    resolved = endpoints._resolve_evidence_file(run_dir.name, "report.html")
    assert resolved == (run_dir / "report.html").resolve()

    with pytest.raises(HTTPException):
        endpoints._resolve_evidence_file(run_dir.name, "../secret.txt")

    with pytest.raises(HTTPException):
        endpoints._resolve_evidence_file("../bad", "report.html")


def test_scan_evidence_payload_reads_nested_scan_output() -> None:
    payload = _scan_evidence_payload(
        {
            "scan": {
                "candidates": [{"ticker": "MRVL"}],
                "rejected_count": 2,
                "scan_trace": {"provider_sources_used": ["finnhub"]},
            }
        }
    )

    assert payload == ([{"ticker": "MRVL"}], 2, ["finnhub"])
