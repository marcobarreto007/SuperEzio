"""Regression tests for F51 Trade Gate — all critical bugs from the 14-day audit.

These tests enforce the "fail closed" principle.
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.pipeline.f51_trade_gate import (
    build_order_gate_metadata,
    is_execution_frozen,
    is_ticker_blacklisted,
    is_valid_ticker_format,
    is_explicit_trade_intent,
    evaluate_trade_gate,
    TradeGateDecision,
    is_journal_healthy,
)


_NEURAL_GATE = {
    "allowed": True,
    "model_id": "neural-test-v1",
    "as_of": "2026-07-19T12:00:00+00:00",
    "horizon": 1,
}


def test_order_gate_metadata_requires_real_allow_decision_and_consensus():
    allowed = TradeGateDecision(
        status="ALLOW",
        evidence={"validated_ticker": "AAPL", "run_id": "run-123"},
    )
    metadata = build_order_gate_metadata(
        allowed,
        order_symbol="AAPL",
        approval_id="apr-123",
        consensus_decision="SUPPORT",
        neural_gate=_NEURAL_GATE,
    )
    assert metadata["pipeline_prepared"] is True
    assert metadata["adaptive_policy_applied"] is True
    assert metadata["gate_trace_id"] == "run-123"
    assert metadata["neural_gate_status"] == "ALLOW"
    assert metadata["neural_model_id"] == "neural-test-v1"

    with pytest.raises(ValueError):
        build_order_gate_metadata(
            TradeGateDecision(status="BLOCK"),
            order_symbol="AAPL",
            approval_id="apr-123",
            consensus_decision="SUPPORT",
            neural_gate=_NEURAL_GATE,
        )
    with pytest.raises(ValueError):
        build_order_gate_metadata(
            allowed,
            order_symbol="AAPL",
            approval_id="apr-123",
            consensus_decision="BLOCK",
            neural_gate=_NEURAL_GATE,
        )

    with pytest.raises(ValueError):
        build_order_gate_metadata(
            allowed,
            order_symbol="AAPL",
            approval_id="apr-123",
            consensus_decision="SUPPORT",
            neural_gate={"allowed": False},
        )


@pytest.fixture(autouse=True)
def _isolate_from_real_env_file(monkeypatch):
    """Most tests in this file exercise gates *after* GATE 1 (execution
    freeze) and assume freeze is off by default. is_execution_frozen() also
    checks SUPEREZIO_LIVE_TRADING_DISABLED / SUPEREZIO_RESEARCH_PAPER_ONLY /
    SUPEREZIO_DAYTRADE_PAPER_ONLY (added to keep the rest of the system
    paper-only by default — see docs/audit/phase6). If a real .env on disk
    sets any of those (e.g. for scripts/questrade_order_assist.py), every
    test below GATE 1 would wrongly see EXECUTION_FREEZE instead of the gate
    it actually means to exercise. Clear them here so this file's tests stay
    isolated from whatever .env happens to exist on disk; individual tests
    that specifically test freeze behavior (TestExecutionFreeze) still set
    F51_TRADING_EXECUTION_FREEZE explicitly as needed.
    """
    monkeypatch.delenv("SUPEREZIO_LIVE_TRADING_DISABLED", raising=False)
    monkeypatch.delenv("SUPEREZIO_RESEARCH_PAPER_ONLY", raising=False)
    monkeypatch.delenv("SUPEREZIO_DAYTRADE_PAPER_ONLY", raising=False)


class TestExecutionFreeze:
    def test_freeze_default_is_on(self):
        # When env var is explicitly set to true, freeze must be ON
        os.environ["F51_TRADING_EXECUTION_FREEZE"] = "true"
        assert is_execution_frozen() is True

    def test_freeze_blocks_valid_order(self):
        os.environ["F51_TRADING_EXECUTION_FREEZE"] = "true"
        result = evaluate_trade_gate(
            message="comprar 10 AAPL", ticker="AAPL", qty=10, limit_price=150.0
        )
        assert result.status == "BLOCK"
        assert result.reason_code == "EXECUTION_FREEZE"

    def test_freeze_off_proceeds(self, monkeypatch):
        monkeypatch.setenv("F51_TRADING_EXECUTION_FREEZE", "false")
        # SUPEREZIO_* isolation handled by the _isolate_from_real_env_file
        # autouse fixture above.
        result = evaluate_trade_gate(
            message="comprar 10 AAPL", ticker="AAPL", qty=10, limit_price=150.0
        )
        assert result.reason_code != "EXECUTION_FREEZE"


class TestManAtWorkGate:
    """GATE 1.5: MAN_AT_WORK hard-block no caminho de trade."""

    def _patch_guard(self, monkeypatch, result, raises=False):
        import core.bob_consciousness as consciousness

        class _FakeBody:
            def check_man_at_work_guard(self, operation="trading"):
                if raises:
                    raise RuntimeError("ans registry offline")
                return result

        monkeypatch.setattr(consciousness, "get_bobs_body", lambda: _FakeBody())

    def test_normal_mode_does_not_block(self, monkeypatch):
        monkeypatch.setenv("F51_TRADING_EXECUTION_FREEZE", "false")
        self._patch_guard(monkeypatch, (True, ""))
        result = evaluate_trade_gate(
            message="comprar 10 AAPL", ticker="AAPL", qty=10, limit_price=150.0
        )
        assert result.reason_code != "MAN_AT_WORK"

    def test_man_at_work_blocks_with_reason_code(self, monkeypatch):
        monkeypatch.setenv("F51_TRADING_EXECUTION_FREEZE", "false")
        self._patch_guard(monkeypatch, (False, "MAN_AT_WORK mode: trading blocked"))
        result = evaluate_trade_gate(
            message="comprar 10 AAPL", ticker="AAPL", qty=10, limit_price=150.0
        )
        assert result.status == "BLOCK"
        assert result.reason_code == "MAN_AT_WORK"

    def test_unverifiable_guard_fails_closed(self, monkeypatch):
        monkeypatch.setenv("F51_TRADING_EXECUTION_FREEZE", "false")
        self._patch_guard(monkeypatch, (True, ""), raises=True)
        result = evaluate_trade_gate(
            message="comprar 10 AAPL", ticker="AAPL", qty=10, limit_price=150.0
        )
        assert result.status == "BLOCK"
        assert result.reason_code == "MAN_AT_WORK_UNAVAILABLE"


class TestNonTradeIntent:
    def test_explain_sentiment_not_trade(self):
        assert is_explicit_trade_intent("me explica o que e sentimento vivo") is False

    def test_analyze_not_trade(self):
        assert is_explicit_trade_intent("analisa sentimento de mercado") is False

    def test_what_about_apple_not_trade(self):
        assert is_explicit_trade_intent("o que voce acha da Apple?") is False

    def test_explain_rsi_not_trade(self):
        assert is_explicit_trade_intent("me explique RSI") is False

    def test_what_stocks_strong_not_trade(self):
        assert is_explicit_trade_intent("quais acoes estao fortes hoje?") is False

    def test_comprar_is_trade(self):
        assert is_explicit_trade_intent("comprar 10 acoes da AAPL") is True

    def test_paper_ticket_is_trade(self):
        assert is_explicit_trade_intent("PAPER_TICKET: buy 5 TSLA at 250") is True

    def test_submit_order_is_trade(self):
        assert is_explicit_trade_intent("submit order for 100 shares NVDA") is True

    def test_non_trade_blocks_order(self, monkeypatch):
        monkeypatch.setenv("F51_TRADING_EXECUTION_FREEZE", "false")
        result = evaluate_trade_gate(
            message="me explica o que e sentimento vivo", ticker="S", qty=10, limit_price=20.0
        )
        assert result.status == "BLOCK"
        assert result.reason_code == "NON_TRADE_INTENT"


class TestTickerBlacklist:
    def test_todas_blacklisted(self):
        assert is_ticker_blacklisted("TODAS") is True

    def test_sentimento_blacklisted(self):
        assert is_ticker_blacklisted("SENTIMENTO") is True

    def test_vivo_blacklisted(self):
        assert is_ticker_blacklisted("VIVO") is True

    def test_tudo_blacklisted(self):
        assert is_ticker_blacklisted("TUDO") is True

    def test_all_blacklisted(self):
        assert is_ticker_blacklisted("ALL") is True

    def test_buy_blacklisted(self):
        assert is_ticker_blacklisted("BUY") is True

    def test_valid_tickers_not_blacklisted(self):
        assert is_ticker_blacklisted("AAPL") is False
        assert is_ticker_blacklisted("TSLA") is False
        assert is_ticker_blacklisted("NVDA") is False

    def test_blacklisted_blocks_order(self, monkeypatch):
        monkeypatch.setenv("F51_TRADING_EXECUTION_FREEZE", "false")
        result = evaluate_trade_gate(
            message="comprar 10 TODAS", ticker="TODAS", qty=10, limit_price=50.0
        )
        assert result.status == "BLOCK"
        assert result.reason_code == "BLACKLISTED_TICKER"


class TestTickerFormat:
    def test_valid(self):
        assert is_valid_ticker_format("AAPL") is True
        assert is_valid_ticker_format("TSLA") is True
        assert is_valid_ticker_format("RY.TO") is True
        assert is_valid_ticker_format("BRK.B") is True
        assert is_valid_ticker_format("IMRX") is True

    def test_invalid(self):
        assert is_valid_ticker_format("") is False
        assert is_valid_ticker_format("A") is False
        assert is_valid_ticker_format("TOOLONG") is False
        assert is_valid_ticker_format("123") is False


class TestTickerMismatch:
    def test_mismatch_blocks(self, monkeypatch):
        monkeypatch.setenv("F51_TRADING_EXECUTION_FREEZE", "false")
        monkeypatch.setenv("IBKR_HOST", "127.0.0.1")
        monkeypatch.setenv("IBKR_PORT", "7497")
        result = evaluate_trade_gate(
            message="comprar 10 USIO",
            ticker="AOSL",
            thesis_ticker="USIO",
            qty=10,
            limit_price=48.04,
        )
        assert result.status == "BLOCK"
        assert result.reason_code == "TICKER_MISMATCH"

    def test_match_allows(self, monkeypatch):
        monkeypatch.setenv("F51_TRADING_EXECUTION_FREEZE", "false")
        monkeypatch.setenv("IBKR_HOST", "127.0.0.1")
        monkeypatch.setenv("IBKR_PORT", "7497")
        result = evaluate_trade_gate(
            message="comprar 10 AAPL",
            ticker="AAPL",
            thesis_ticker="AAPL",
            qty=10,
            limit_price=150.0,
        )
        if result.reason_code == "TICKER_MISMATCH":
            pytest.fail("Matched ticker should not be blocked for mismatch")


class TestPlaceholderQuantity:
    def test_qty_5_price_99_blocks(self, monkeypatch):
        monkeypatch.setenv("F51_TRADING_EXECUTION_FREEZE", "false")
        monkeypatch.setenv("IBKR_HOST", "127.0.0.1")
        monkeypatch.setenv("IBKR_PORT", "7497")
        result = evaluate_trade_gate(message="comprar AAPL", ticker="AAPL", qty=5, limit_price=99.0)
        assert result.status == "BLOCK"
        assert result.reason_code == "PLACEHOLDER_QUANTITY"

    def test_qty_10_price_99_blocks(self, monkeypatch):
        monkeypatch.setenv("F51_TRADING_EXECUTION_FREEZE", "false")
        monkeypatch.setenv("IBKR_HOST", "127.0.0.1")
        monkeypatch.setenv("IBKR_PORT", "7497")
        result = evaluate_trade_gate(
            message="comprar AAPL", ticker="AAPL", qty=10, limit_price=99.0
        )
        assert result.status == "BLOCK"
        assert result.reason_code == "PLACEHOLDER_QUANTITY"

    def test_qty_100_price_99_blocks(self, monkeypatch):
        monkeypatch.setenv("F51_TRADING_EXECUTION_FREEZE", "false")
        monkeypatch.setenv("IBKR_HOST", "127.0.0.1")
        monkeypatch.setenv("IBKR_PORT", "7497")
        result = evaluate_trade_gate(
            message="comprar AAPL", ticker="AAPL", qty=100, limit_price=99.0
        )
        assert result.status == "BLOCK"
        assert result.reason_code == "PLACEHOLDER_QUANTITY"

    def test_zero_qty_blocks(self, monkeypatch):
        monkeypatch.setenv("F51_TRADING_EXECUTION_FREEZE", "false")
        result = evaluate_trade_gate(
            message="comprar AAPL", ticker="AAPL", qty=0, limit_price=150.0
        )
        assert result.status == "BLOCK"
        assert result.reason_code == "INVALID_QUANTITY"


class TestPlaceholderPrice:
    def test_placeholder_price_99_blocks(self, monkeypatch):
        monkeypatch.setenv("F51_TRADING_EXECUTION_FREEZE", "false")
        monkeypatch.setenv("IBKR_HOST", "127.0.0.1")
        monkeypatch.setenv("IBKR_PORT", "7497")
        result = evaluate_trade_gate(
            message="comprar 50 AAPL", ticker="AAPL", qty=50, limit_price=99.0
        )
        assert result.status == "BLOCK"
        assert result.reason_code == "PLACEHOLDER_PRICE"


class TestJournalHealth:
    def test_journal_health_probe_does_not_append_fake_trade(self, tmp_path):
        journal = tmp_path / "paper_trades.jsonl"
        journal.write_text('{"trade_id":"real-trade"}\n', encoding="utf-8")
        before = journal.read_bytes()

        assert is_journal_healthy(str(journal)) is True
        assert journal.read_bytes() == before
        assert list(tmp_path.glob(".journal-health-*")) == []


class TestTradeGateDecision:
    def test_default_is_block(self):
        d = TradeGateDecision()
        assert d.status == "BLOCK"

    def test_evidence_and_gates_populated(self):
        d = TradeGateDecision(
            status="BLOCK",
            reason_code="TEST",
            reason="Test block",
            evidence={"ticker": "AAPL"},
            gates_failed=["test_gate"],
            gates_passed=["other_gate"],
        )
        assert d.status == "BLOCK"
        assert d.reason_code == "TEST"
        assert d.evidence["ticker"] == "AAPL"
        assert "test_gate" in d.gates_failed
        assert "other_gate" in d.gates_passed
