"""Regression tests for F51 Trade Gate — all critical bugs from the 14-day audit.

These tests enforce the "fail closed" principle.
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.pipeline.f51_trade_gate import (
    is_execution_frozen,
    is_ticker_blacklisted,
    is_valid_ticker_format,
    is_explicit_trade_intent,
    evaluate_trade_gate,
    TradeGateDecision,
    is_journal_healthy,
)


class TestExecutionFreeze:
    def test_freeze_default_is_on(self):
        assert is_execution_frozen() is True

    def test_freeze_blocks_valid_order(self):
        os.environ["F51_TRADING_EXECUTION_FREEZE"] = "true"
        result = evaluate_trade_gate(
            message="comprar 10 AAPL", ticker="AAPL", qty=10, limit_price=150.0)
        assert result.status == "BLOCK"
        assert result.reason_code == "EXECUTION_FREEZE"

    def test_freeze_off_proceeds(self, monkeypatch):
        monkeypatch.setenv("F51_TRADING_EXECUTION_FREEZE", "false")
        result = evaluate_trade_gate(
            message="comprar 10 AAPL", ticker="AAPL", qty=10, limit_price=150.0)
        assert result.reason_code != "EXECUTION_FREEZE"


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
            message="me explica o que e sentimento vivo",
            ticker="S", qty=10, limit_price=20.0)
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
            message="comprar 10 TODAS", ticker="TODAS", qty=10, limit_price=50.0)
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
            message="comprar 10 USIO", ticker="AOSL",
            thesis_ticker="USIO", qty=10, limit_price=48.04)
        assert result.status == "BLOCK"
        assert result.reason_code == "TICKER_MISMATCH"

    def test_match_allows(self, monkeypatch):
        monkeypatch.setenv("F51_TRADING_EXECUTION_FREEZE", "false")
        monkeypatch.setenv("IBKR_HOST", "127.0.0.1")
        monkeypatch.setenv("IBKR_PORT", "7497")
        result = evaluate_trade_gate(
            message="comprar 10 AAPL", ticker="AAPL",
            thesis_ticker="AAPL", qty=10, limit_price=150.0)
        if result.reason_code == "TICKER_MISMATCH":
            pytest.fail("Matched ticker should not be blocked for mismatch")


class TestPlaceholderQuantity:
    def test_qty_5_price_99_blocks(self, monkeypatch):
        monkeypatch.setenv("F51_TRADING_EXECUTION_FREEZE", "false")
        monkeypatch.setenv("IBKR_HOST", "127.0.0.1")
        monkeypatch.setenv("IBKR_PORT", "7497")
        result = evaluate_trade_gate(
            message="comprar AAPL", ticker="AAPL", qty=5, limit_price=99.0)
        assert result.status == "BLOCK"
        assert result.reason_code == "PLACEHOLDER_QUANTITY"

    def test_qty_10_price_99_blocks(self, monkeypatch):
        monkeypatch.setenv("F51_TRADING_EXECUTION_FREEZE", "false")
        monkeypatch.setenv("IBKR_HOST", "127.0.0.1")
        monkeypatch.setenv("IBKR_PORT", "7497")
        result = evaluate_trade_gate(
            message="comprar AAPL", ticker="AAPL", qty=10, limit_price=99.0)
        assert result.status == "BLOCK"
        assert result.reason_code == "PLACEHOLDER_QUANTITY"

    def test_qty_100_price_99_blocks(self, monkeypatch):
        monkeypatch.setenv("F51_TRADING_EXECUTION_FREEZE", "false")
        monkeypatch.setenv("IBKR_HOST", "127.0.0.1")
        monkeypatch.setenv("IBKR_PORT", "7497")
        result = evaluate_trade_gate(
            message="comprar AAPL", ticker="AAPL", qty=100, limit_price=99.0)
        assert result.status == "BLOCK"
        assert result.reason_code == "PLACEHOLDER_QUANTITY"

    def test_zero_qty_blocks(self, monkeypatch):
        monkeypatch.setenv("F51_TRADING_EXECUTION_FREEZE", "false")
        result = evaluate_trade_gate(
            message="comprar AAPL", ticker="AAPL", qty=0, limit_price=150.0)
        assert result.status == "BLOCK"
        assert result.reason_code == "INVALID_QUANTITY"


class TestPlaceholderPrice:
    def test_placeholder_price_99_blocks(self, monkeypatch):
        monkeypatch.setenv("F51_TRADING_EXECUTION_FREEZE", "false")
        monkeypatch.setenv("IBKR_HOST", "127.0.0.1")
        monkeypatch.setenv("IBKR_PORT", "7497")
        result = evaluate_trade_gate(
            message="comprar 50 AAPL", ticker="AAPL", qty=50, limit_price=99.0)
        assert result.status == "BLOCK"
        assert result.reason_code == "PLACEHOLDER_PRICE"


class TestJournalHealth:
    def test_journal_is_healthy_on_disk(self):
        assert is_journal_healthy() is True


class TestTradeGateDecision:
    def test_default_is_block(self):
        d = TradeGateDecision()
        assert d.status == "BLOCK"

    def test_evidence_and_gates_populated(self):
        d = TradeGateDecision(
            status="BLOCK", reason_code="TEST", reason="Test block",
            evidence={"ticker": "AAPL"},
            gates_failed=["test_gate"], gates_passed=["other_gate"])
        assert d.status == "BLOCK"
        assert d.reason_code == "TEST"
        assert d.evidence["ticker"] == "AAPL"
        assert "test_gate" in d.gates_failed
        assert "other_gate" in d.gates_passed
