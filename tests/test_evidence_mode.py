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


def test_evidence_run_propagates_stream_run_id() -> None:
    """The stream run_id must be baked into evidence_run_id (unification)."""
    run = EvidenceRun(prompt="p", ticker="AAPL", run_id="abc123def456")

    assert run.run_id.endswith("_abc123def456_AAPL")
    assert run.run_dir.name == run.run_id

    # Legacy format (timestamp + 6-hex) preserved when no run_id is passed.
    legacy = EvidenceRun(prompt="p", ticker="")
    assert len(legacy.run_id.rsplit("_", 1)[1]) == 6


def test_finalize_treats_streamed_placeholder_as_empty() -> None:
    """The explanation node's "(streamed)" marker must not count as a response."""
    from core.pipeline.graph import _is_real_evidence_response

    assert _is_real_evidence_response("") is False
    assert _is_real_evidence_response("(streamed)") is False
    assert _is_real_evidence_response("real streamed answer") is True


def test_record_response_overwrites_streamed_placeholder() -> None:
    """The finalize fallback depends on record_response overwriting the placeholder."""
    run = EvidenceRun(prompt="p", ticker="AAPL")
    run.record_response("(streamed)", tokens=1)
    run.record_response("real streamed answer", tokens=3)

    assert run.response == "real streamed answer"


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
