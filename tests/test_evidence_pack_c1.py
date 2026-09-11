"""C1 EvidencePack — canonical seal, coverage, shadow write, rollback flag."""

from __future__ import annotations

from pathlib import Path

from core.evidence.pack import (
    PACK_FILENAME,
    save_evidence_pack,
    seal_pack,
    verify_pack_seal,
)
from core.evidence.pack_builder import build_evidence_pack_from_state, is_arch_c1_enabled

FROZEN_AT = "2026-09-11T15:00:00+00:00"


def _ticker_state() -> dict:
    return {
        "run_id": "abc123def456",
        "route": "ticker_analysis",
        "ticker": "AAPL",
        "data": {
            "ticker": "AAPL",
            "price": {"price": 190.5, "source": "yfinance"},
            "ohlcv": [
                {"close": 188.0, "volume": 1_000},
                {"close": 190.5, "volume": 1_100},
            ],
            "news": [{"title": "item"}],
        },
        "math_report": {"summary": {"latest_price": 190.5}},
    }


def test_canonical_seal_is_stable_for_identical_facts() -> None:
    first = build_evidence_pack_from_state(
        _ticker_state(), run_id="abc123def456", created_at=FROZEN_AT
    )
    second = build_evidence_pack_from_state(
        _ticker_state(), run_id="abc123def456", created_at=FROZEN_AT
    )
    assert verify_pack_seal(first)
    assert (
        first["integrity"]["canonical_json_sha256"] == second["integrity"]["canonical_json_sha256"]
    )
    assert len(first["integrity"]["canonical_json_sha256"]) == 64


def test_seal_is_stable_across_created_at() -> None:
    first = build_evidence_pack_from_state(
        _ticker_state(), run_id="abc123def456", created_at=FROZEN_AT
    )
    second = build_evidence_pack_from_state(
        _ticker_state(), run_id="abc123def456", created_at="2026-09-12T00:00:00+00:00"
    )
    assert first["created_at"] != second["created_at"]
    assert (
        first["integrity"]["canonical_json_sha256"] == second["integrity"]["canonical_json_sha256"]
    )


def test_seal_changes_when_a_number_changes() -> None:
    baseline = build_evidence_pack_from_state(
        _ticker_state(), run_id="abc123def456", created_at=FROZEN_AT
    )
    mutated = _ticker_state()
    mutated["data"]["price"]["price"] = 191.0
    other = build_evidence_pack_from_state(mutated, run_id="abc123def456", created_at=FROZEN_AT)
    assert (
        baseline["integrity"]["canonical_json_sha256"]
        != other["integrity"]["canonical_json_sha256"]
    )


def test_verify_fails_if_integrity_is_tampered() -> None:
    pack = build_evidence_pack_from_state(
        _ticker_state(), run_id="abc123def456", created_at=FROZEN_AT
    )
    pack["facts"]["price"]["value"] = 0
    assert verify_pack_seal(pack) is False


def test_ticker_analysis_marks_macro_missing_without_blocking_required_set() -> None:
    pack = build_evidence_pack_from_state(
        _ticker_state(), run_id="abc123def456", created_at=FROZEN_AT
    )
    assert pack["facts"]["price"]["status"] == "OK"
    assert pack["facts"]["ohlcv"]["status"] == "OK"
    assert pack["facts"]["ohlcv"]["value"]["rows"] == 2
    assert pack["facts"]["macro_observations"]["status"] == "MISSING"
    assert pack["coverage"]["missing"] == []
    assert pack["status"] == "PARTIAL"
    assert pack["facts"]["price"]["value"] == 190.5


def test_ticker_without_price_is_insufficient() -> None:
    state = {"route": "ticker_analysis", "ticker": "MSFT", "data": {"ticker": "MSFT"}}
    pack = build_evidence_pack_from_state(state, run_id="run1", created_at=FROZEN_AT)
    assert pack["status"] == "INSUFFICIENT"
    assert "price" in pack["coverage"]["missing"]
    assert "ohlcv" in pack["coverage"]["missing"]


def test_casual_route_has_no_required_facts() -> None:
    pack = build_evidence_pack_from_state(
        {"route": "general", "message": "oi"},
        run_id="run1",
        created_at=FROZEN_AT,
    )
    assert pack["coverage"]["required"] == 0
    assert pack["coverage"]["missing"] == []
    assert pack["status"] == "COMPLETE"


def test_market_scan_requires_candidates() -> None:
    empty = build_evidence_pack_from_state(
        {"route": "market_scan"}, run_id="run1", created_at=FROZEN_AT
    )
    assert empty["status"] == "INSUFFICIENT"
    filled = build_evidence_pack_from_state(
        {"route": "market_scan", "scan": {"candidates": [{"ticker": "AAPL"}]}},
        run_id="run1",
        created_at=FROZEN_AT,
    )
    assert filled["facts"]["scan_candidates"]["status"] == "OK"
    assert filled["coverage"]["missing"] == []


def test_atomic_write_roundtrip(tmp_path: Path) -> None:
    pack = build_evidence_pack_from_state(
        _ticker_state(), run_id="abc123def456", created_at=FROZEN_AT
    )
    path = save_evidence_pack(pack, tmp_path)
    assert path.name == PACK_FILENAME
    text = path.read_text(encoding="utf-8")
    assert "canonical_json_sha256" in text
    assert verify_pack_seal(pack)


def test_c1_flag_rolls_back(monkeypatch) -> None:
    monkeypatch.delenv("SUPEREZIO_ARCH_C1", raising=False)
    assert is_arch_c1_enabled() is True
    monkeypatch.setenv("SUPEREZIO_ARCH_C1", "0")
    assert is_arch_c1_enabled() is False
    monkeypatch.setenv("SUPEREZIO_ARCH_C1", "false")
    assert is_arch_c1_enabled() is False
    monkeypatch.setenv("SUPEREZIO_ARCH_C1", "1")
    assert is_arch_c1_enabled() is True


def test_c1_flag_default_matches_settings() -> None:
    from core.config.settings import Settings

    assert Settings.model_fields["superezio_arch_c1"].default is True


def test_shadow_pack_write_failure_does_not_raise(tmp_path: Path, monkeypatch) -> None:
    from core.pipeline import graph as graph_mod

    monkeypatch.setenv("SUPEREZIO_ARCH_C1", "1")
    monkeypatch.setenv("SUPEREZIO_ARCH_C2", "0")

    def boom(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("core.evidence.pack.atomic_write_text", boom)
    graph_mod._save_shadow_evidence_pack(_ticker_state(), "abc123def456", tmp_path)


def test_pipeline_snapshot_appends_errors() -> None:
    from core.pipeline.graph import _absorb_pipeline_update

    snapshot = {"errors": ["first"]}
    _absorb_pipeline_update(snapshot, {"errors": ["second"], "ticker": "AAPL"})
    assert snapshot["errors"] == ["first", "second"]
    assert snapshot["ticker"] == "AAPL"


def test_ohlcv_provider_is_unknown_without_source() -> None:
    state = _ticker_state()
    state["data"]["price"] = {"price": 190.5}
    pack = build_evidence_pack_from_state(state, run_id="abc123def456", created_at=FROZEN_AT)
    assert pack["facts"]["ohlcv"]["provider"] == "unknown"


def test_seal_helper_is_pure() -> None:
    body = {"facts": {"price": {"value": 1}}, "status": "COMPLETE"}
    first = seal_pack(body, writer="test")
    second = seal_pack(body, writer="test")
    assert (
        first["integrity"]["canonical_json_sha256"] == second["integrity"]["canonical_json_sha256"]
    )
    assert verify_pack_seal(first)
