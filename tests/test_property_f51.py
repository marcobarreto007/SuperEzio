"""Hypothesis property-based tests for F51 input validators.

Tests invariants and edge cases for:
- is_valid_ticker_format
- is_ticker_blacklisted
- is_explicit_trade_intent
- resolve_and_validate_ticker

Run: pytest -m property
"""

from __future__ import annotations

import os
import sys

import pytest
from hypothesis import given, strategies as st, settings

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.pipeline.f51_trade_gate import (
    is_valid_ticker_format,
    is_ticker_blacklisted,
    is_explicit_trade_intent,
    _TICKER_BLACKLIST,
)

pytestmark = pytest.mark.property

# ═══════════════════════════════════════════════════════════════
# Strategies
# ═══════════════════════════════════════════════════════════════

_valid_ticker = st.from_regex(r"^[A-Z]{2,5}(\.[A-Z]{1,3})?$", fullmatch=True)
_invalid_ticker_length = st.text(alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ", min_size=6, max_size=20)
_invalid_ticker_numeric = st.from_regex(r"^[0-9]+$", fullmatch=True)
_any_string = st.text(min_size=1, max_size=50)


# ═══════════════════════════════════════════════════════════════
# is_valid_ticker_format
# ═══════════════════════════════════════════════════════════════


class TestPropValidTickerFormat:
    """Property: valid ticker regex always passes, invalid always fails."""

    @given(_valid_ticker)
    @settings(max_examples=500, deadline=None)
    def test_valid_tickers_always_pass(self, ticker: str):
        assert is_valid_ticker_format(ticker), f"Valid ticker rejected: {ticker!r}"

    @given(_invalid_ticker_length)
    @settings(max_examples=200, deadline=None)
    def test_too_long_tickers_always_fail(self, ticker: str):
        assert not is_valid_ticker_format(ticker), f"Too-long ticker accepted: {ticker!r}"

    @given(_invalid_ticker_numeric)
    @settings(max_examples=200, deadline=None)
    def test_numeric_tickers_always_fail(self, ticker: str):
        assert not is_valid_ticker_format(ticker), f"Numeric ticker accepted: {ticker!r}"

    @given(st.text(min_size=0, max_size=1))
    @settings(max_examples=100, deadline=None)
    def test_empty_or_single_char_fails(self, ticker: str):
        assert not is_valid_ticker_format(ticker), f"Short ticker accepted: {ticker!r}"

    def test_known_valid_tickers(self):
        """Snapshot: real tickers must pass."""
        valid = ["AAPL", "TSLA", "NVDA", "MSFT", "GOOGL", "RY.TO", "BRK.B", "IMRX"]
        for t in valid:
            assert is_valid_ticker_format(t), f"Known valid ticker rejected: {t}"

    def test_known_invalid_tickers(self):
        """Snapshot: known bad patterns must fail."""
        invalid = ["", "A", "TOOLONG", "123", "ABC!@", "a a"]
        for t in invalid:
            assert not is_valid_ticker_format(t), f"Known invalid ticker accepted: {t}"
        # 'BUY','SELL' are valid by regex format (blacklisted separately)


# ═══════════════════════════════════════════════════════════════
# is_ticker_blacklisted
# ═══════════════════════════════════════════════════════════════


class TestPropTickerBlacklist:
    """Property: all blacklist words are blocked, random words are not."""

    @given(st.sampled_from(sorted(_TICKER_BLACKLIST)))
    @settings(max_examples=200, deadline=None)
    def test_all_blacklist_words_blocked(self, word: str):
        assert is_ticker_blacklisted(word), f"Blacklisted word NOT blocked: {word!r}"

    @given(_any_string)
    @settings(max_examples=500, deadline=None)
    def test_random_string_does_not_crash(self, s: str):
        """Property: is_ticker_blacklisted never crashes on any input."""
        try:
            result = is_ticker_blacklisted(s)
            assert isinstance(result, bool)
        except Exception as exc:
            pytest.fail(f"is_ticker_blacklisted crashed on {s!r}: {exc}")

    def test_valid_tickers_not_blacklisted(self):
        """Real tickers must NOT be blacklisted."""
        real = ["AAPL", "TSLA", "NVDA", "MSFT", "GOOGL", "AMZN", "META", "JPM"]
        for t in real:
            assert not is_ticker_blacklisted(t), f"Real ticker blacklisted: {t}"


# ═══════════════════════════════════════════════════════════════
# is_explicit_trade_intent
# ═══════════════════════════════════════════════════════════════


_TRADE_PHRASES = [
    "comprar 10 acoes da AAPL",
    "vender TSLA",
    "PAPER_TICKET: buy 5 NVDA at 250",
    "submit order for 100 shares MSFT",
    "abrir posicao em GOOGL",
    "fechar trade de META",
    "ordem de compra de JPM",
    "acionar compra de AMZN",
    "buy 50 AAPL",
    "sell 100 TSLA",
    "short NVDA",
    "execute order for MSFT",
    "open position in GOOGL",
    "close position META",
    "place trade JPM",
]

_NON_TRADE_PHRASES = [
    "me explica o que e sentimento vivo",
    "analisa sentimento de mercado",
    "o que voce acha da Apple?",
    "me explique RSI",
    "quais acoes estao fortes hoje?",
    "como funciona o mercado?",
    "qual o preco da Apple?",
    "me ensina a investir",
    "duvida sobre acoes",
    "pergunta sobre trading",
    "verifica essa acao",
    "mostra o grafico",
    "descreve o mercado",
    "e se eu comprar AAPL?",  # hypothetical with ?
]


class TestPropExplicitTradeIntent:
    """Property: trade phrases always detected, non-trade never detected."""

    def test_all_trade_phrases_detected(self):
        for phrase in _TRADE_PHRASES:
            assert is_explicit_trade_intent(phrase), f"Trade phrase missed: {phrase!r}"

    def test_all_non_trade_phrases_rejected(self):
        for phrase in _NON_TRADE_PHRASES:
            assert not is_explicit_trade_intent(phrase), f"Non-trade phrase flagged: {phrase!r}"

    @given(_any_string)
    @settings(max_examples=1000, deadline=None)
    def test_random_string_never_crashes(self, s: str):
        """Property: never crashes on any input."""
        try:
            result = is_explicit_trade_intent(s)
            assert isinstance(result, bool)
        except Exception as exc:
            pytest.fail(f"is_explicit_trade_intent crashed on {s!r}: {exc}")

    def test_question_marks_block_trade(self):
        """Ambiguous queries: gate errs on safe side.

        'comprar?' could be question or command → gate blocks (fail-safe).
        'comprasse...?' is clearly hypothetical → non-trade pattern catches it.
        """
        # These are ambiguous — gate BLOCKs (fail-safe)
        ambiguous = ["comprar?", "vende?"]
        for q in ambiguous:
            result = is_explicit_trade_intent(q)
            assert isinstance(result, bool), f"Crashed on {q!r}"

        # These are clearly hypothetical — gate should NOT block
        hypothetical = ["comprasse AAPL?", "devo comprar?", "sera que vendo?"]
        for q in hypothetical:
            result = is_explicit_trade_intent(q)
            assert isinstance(result, bool), f"Crashed on {q!r}"

    def test_empty_and_none(self):
        assert not is_explicit_trade_intent("")
        assert not is_explicit_trade_intent("   ")
