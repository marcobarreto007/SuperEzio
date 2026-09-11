"""C2 Frozen Snapshot — provenance, seal, shadow write, rollback flag."""

from __future__ import annotations

from pathlib import Path

from core.evidence.arch_flags import is_arch_c2_enabled
from core.evidence.pack import pack_digest
from core.evidence.pack_builder import build_evidence_pack_from_state
from core.evidence.snapshot import (
    SNAPSHOT_FILENAME,
    format_snapshot_binding,
    freeze_snapshot,
    save_snapshot,
    verify_snapshot_seal,
)

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
        "math_report": {
            "summary": {"latest_price": 190.5, "sharpe": 1.2},
            "numbers": {
                "latest_price": 190.5,
                "rsi": 55.0,
                "sharpe": 1.2,
                "bollinger": {"upper": 200.0, "lower": 180.0},
            },
        },
    }


def _freeze(state: dict | None = None, created_at: str = FROZEN_AT):
    payload = state or _ticker_state()
    pack = build_evidence_pack_from_state(payload, run_id="abc123def456", created_at=created_at)
    math_report = payload.get("math_report")
    snapshot = freeze_snapshot(
        pack=pack,
        math_report=math_report if isinstance(math_report, dict) else {},
        run_id="abc123def456",
    )
    return pack, snapshot


def test_snapshot_is_frozen_with_provenance() -> None:
    pack, snapshot = _freeze()
    assert snapshot["frozen"] is True
    assert verify_snapshot_seal(snapshot)
    assert snapshot["pack_sha256"] == pack_digest(pack)
    assert snapshot["numbers"]["price"]["value"] == 190.5
    assert snapshot["numbers"]["price"]["provenance"] == ["price"]
    assert snapshot["numbers"]["rsi"]["value"] == 55.0
    assert snapshot["numbers"]["rsi"]["provenance"] == ["ohlcv"]
    assert snapshot["numbers"]["rsi"]["formula_id"] == "math_hub.rsi14"
    assert snapshot["price"]["provider"] == "yfinance"
    assert snapshot["series_ref"]["rows"] == 2
    assert "bollinger" not in snapshot["numbers"]
    assert snapshot["currency"] is None


def test_snapshot_seal_ignores_as_of() -> None:
    _, first = _freeze(created_at=FROZEN_AT)
    _, second = _freeze(created_at="2026-09-12T00:00:00+00:00")
    assert first["as_of"] != second["as_of"]
    assert (
        first["integrity"]["canonical_json_sha256"] == second["integrity"]["canonical_json_sha256"]
    )


def test_snapshot_seal_changes_when_a_number_changes() -> None:
    _, baseline = _freeze()
    mutated = _ticker_state()
    mutated["math_report"]["numbers"]["rsi"] = 70.0
    _, other = _freeze(mutated)
    assert (
        baseline["integrity"]["canonical_json_sha256"]
        != other["integrity"]["canonical_json_sha256"]
    )


def test_atomic_snapshot_write(tmp_path: Path) -> None:
    _, snapshot = _freeze()
    path = save_snapshot(snapshot, tmp_path)
    assert path.name == SNAPSHOT_FILENAME
    text = path.read_text(encoding="utf-8")
    assert "canonical_json_sha256" in text
    assert '"frozen":true' in text


def test_c2_flag_rolls_back(monkeypatch) -> None:
    monkeypatch.delenv("SUPEREZIO_ARCH_C2", raising=False)
    assert is_arch_c2_enabled() is True
    monkeypatch.setenv("SUPEREZIO_ARCH_C2", "0")
    assert is_arch_c2_enabled() is False


def test_c2_flag_default_matches_settings() -> None:
    from core.config.settings import Settings

    assert Settings.model_fields["superezio_arch_c2"].default is True


def test_c2_skips_disk_when_flag_off(tmp_path: Path, monkeypatch) -> None:
    from core.pipeline import graph as graph_mod

    monkeypatch.setenv("SUPEREZIO_ARCH_C1", "0")
    monkeypatch.setenv("SUPEREZIO_ARCH_C2", "0")
    graph_mod._save_shadow_evidence_pack(_ticker_state(), "abc123def456", tmp_path)
    assert not (tmp_path / "evidence_pack.json").exists()
    assert not (tmp_path / SNAPSHOT_FILENAME).exists()


def test_c2_writes_snapshot_json(tmp_path: Path, monkeypatch) -> None:
    from core.pipeline import graph as graph_mod

    monkeypatch.setenv("SUPEREZIO_ARCH_C1", "1")
    monkeypatch.setenv("SUPEREZIO_ARCH_C2", "1")
    graph_mod._save_shadow_evidence_pack(_ticker_state(), "abc123def456", tmp_path)
    assert (tmp_path / "evidence_pack.json").exists()
    assert (tmp_path / SNAPSHOT_FILENAME).exists()


def test_binding_helper_is_ready_and_wired_behind_c3() -> None:
    from pathlib import Path

    from core.pipeline.nodes import observation_builder

    _, snapshot = _freeze()
    block = format_snapshot_binding(snapshot)
    assert "SNAPSHOT FROZEN" in block
    assert "rsi=55.0" in block
    observation_src = Path(observation_builder.__file__).read_text(encoding="utf-8")
    assert "format_snapshot_binding" in observation_src
    assert "is_arch_c3_enabled" in observation_src


def test_freeze_c2_puts_snapshot_on_state(monkeypatch) -> None:
    from core.pipeline.graph import _freeze_c2_snapshot

    monkeypatch.setenv("SUPEREZIO_ARCH_C2", "1")
    working = _ticker_state()
    output: dict = {}
    _freeze_c2_snapshot(working, output, "abc123def456")
    assert working["snapshot"]["frozen"] is True
    assert output["snapshot"]["frozen"] is True
    monkeypatch.setenv("SUPEREZIO_ARCH_C2", "0")
    skipped: dict = {}
    empty_out: dict = {}
    _freeze_c2_snapshot(skipped, empty_out, "abc123def456")
    assert "snapshot" not in skipped
