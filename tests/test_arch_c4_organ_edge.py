"""C4 organ edge — SDCA fail-closed is an edge, not a paragraph."""

from __future__ import annotations

from core.evidence.arch_flags import is_arch_c4_enabled
from core.pipeline.nodes.guardrails import render_blocked_answer
from core.pipeline.organ_board import route_after_organ_board, sdca_block_reason

_TICKER = {"ticker": "AAPL"}


def test_c4_flag_default_off(monkeypatch) -> None:
    monkeypatch.delenv("SUPEREZIO_ARCH_C4", raising=False)
    assert is_arch_c4_enabled() is False
    from core.config.settings import Settings

    assert Settings.model_fields["superezio_arch_c4"].default is False
    monkeypatch.setenv("SUPEREZIO_ARCH_C4", "1")
    assert is_arch_c4_enabled() is True


def test_c4_off_blocked_sdca_still_goes_to_trinity(monkeypatch, caplog) -> None:
    caplog.set_level("INFO", logger="core.pipeline.organ_board")
    monkeypatch.setenv("SUPEREZIO_ARCH_C4", "0")
    state = {**_TICKER, "sdca_blocked": True, "sdca_firewall": {"decision": "BLOCK"}}
    assert sdca_block_reason(state) == "sdca_blocked"
    assert route_after_organ_board(state) == "trinity"
    assert any("C4_WOULD_BLOCK" in rec.message for rec in caplog.records)


def test_c4_on_sdca_block_stops_before_trinity(monkeypatch) -> None:
    monkeypatch.setenv("SUPEREZIO_ARCH_C4", "1")
    state = {**_TICKER, "sdca_blocked": True, "sdca_firewall": {"decision": "BLOCK"}}
    assert route_after_organ_board(state) == "respond_blocked"


def test_c4_on_sdca_error_never_becomes_allow(monkeypatch) -> None:
    monkeypatch.setenv("SUPEREZIO_ARCH_C4", "1")
    state = {**_TICKER, "sdca_firewall": {"error": "boom"}}
    assert sdca_block_reason(state) == "sdca_error"
    assert route_after_organ_board(state) == "respond_blocked"


def test_c4_on_missing_firewall_with_ticker_blocks(monkeypatch) -> None:
    monkeypatch.setenv("SUPEREZIO_ARCH_C4", "1")
    assert route_after_organ_board({**_TICKER}) == "respond_blocked"
    assert sdca_block_reason({**_TICKER}) == "sdca_missing"


def test_c4_on_swallowed_loop_error_blocks(monkeypatch) -> None:
    monkeypatch.setenv("SUPEREZIO_ARCH_C4", "1")
    state = {
        **_TICKER,
        "errors": ["auto_full_analysis.sdca_firewall:timeout"],
    }
    assert sdca_block_reason(state) == "sdca_error"
    assert route_after_organ_board(state) == "respond_blocked"


def test_c4_on_casual_without_ticker_never_blocks(monkeypatch) -> None:
    monkeypatch.setenv("SUPEREZIO_ARCH_C4", "1")
    state = {"message": "oi", "sdca_blocked": True, "sdca_firewall": {"error": "x"}}
    assert sdca_block_reason(state) is None
    assert route_after_organ_board(state) == "trinity"


def test_c4_on_allow_continues_to_trinity(monkeypatch) -> None:
    monkeypatch.setenv("SUPEREZIO_ARCH_C4", "1")
    state = {**_TICKER, "sdca_firewall": {"decision": "ALLOW"}}
    assert sdca_block_reason(state) is None
    assert route_after_organ_board(state) == "trinity"


def test_blocked_render_covers_organ_error() -> None:
    text = render_blocked_answer({"ticker": "AAPL", "sdca_firewall": {"error": "timeout"}})
    assert "BLOCKED" in text
    assert "timeout" in text
    assert "ALLOW" in text


def test_blocked_render_covers_sdca_decision_block() -> None:
    text = render_blocked_answer(
        {"ticker": "AAPL", "sdca_firewall": {"decision": "BLOCK", "human_summary": "FOMO"}}
    )
    assert "BLOCKED" in text
    assert "FOMO" in text
