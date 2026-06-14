"""Tests for Bob's conversation memory."""

import tempfile
from pathlib import Path

import pytest

from core.memory import ConversationMemory, ConversationTurn, reset_memory_for_test


def test_memory_init():
    """Test memory initialization."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "test_memory.jsonl"
        mem = reset_memory_for_test(path)

        assert mem.path == path
        assert not mem.path.exists()  # Não cria até primeiro write


def test_add_turn():
    """Test adding a conversation turn."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "test_memory.jsonl"
        mem = reset_memory_for_test(path)

        turn = mem.add_turn(
            session_id="test_session",
            user_message="What about AAPL?",
            bob_response="Apple is trading at $150.",
            ticker_discussed="AAPL",
            thesis_formed="Strong earnings expected",
            verdict="BUY_CANDIDATE",
            confidence=75.0,
            category="ticker_analysis",
        )

        assert turn.session_id == "test_session"
        assert turn.ticker_discussed == "AAPL"
        assert turn.verdict == "BUY_CANDIDATE"
        assert turn.embedding_vector is not None
        assert len(turn.embedding_vector) == 128


def test_session_history():
    """Test retrieving session history."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "test_memory.jsonl"
        mem = reset_memory_for_test(path)

        mem.add_turn("s1", "msg1", "resp1")
        mem.add_turn("s1", "msg2", "resp2")
        mem.add_turn("s2", "msg3", "resp3")

        s1_history = mem.get_session_history("s1")
        assert len(s1_history) == 2

        s2_history = mem.get_session_history("s2")
        assert len(s2_history) == 1


def test_ticker_history():
    """Test retrieving ticker-specific history."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "test_memory.jsonl"
        mem = reset_memory_for_test(path)

        mem.add_turn("s1", "msg1", "resp1", ticker_discussed="AAPL")
        mem.add_turn("s1", "msg2", "resp2", ticker_discussed="TSLA")
        mem.add_turn("s2", "msg3", "resp3", ticker_discussed="AAPL")

        aapl_history = mem.get_ticker_history("AAPL")
        assert len(aapl_history) == 2


def test_search_similar():
    """Test semantic search."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "test_memory.jsonl"
        mem = reset_memory_for_test(path)

        mem.add_turn(
            "s1",
            "Should I buy Tesla stock?",
            "TSLA is volatile but has strong momentum.",
            ticker_discussed="TSLA",
            thesis_formed="Momentum play",
        )

        mem.add_turn(
            "s2",
            "What about Apple?",
            "AAPL is a solid long-term hold.",
            ticker_discussed="AAPL",
            thesis_formed="Value investment",
        )

        # Busca por "EV car stock" deve retornar TSLA
        results = mem.search_similar("EV car stock Tesla", top_k=2)
        assert len(results) > 0
        # Primeiro resultado deve ser sobre TSLA
        assert results[0][0].ticker_discussed == "TSLA"


def test_get_theses():
    """Test retrieving recent theses."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "test_memory.jsonl"
        mem = reset_memory_for_test(path)

        mem.add_turn(
            "s1",
            "msg1",
            "resp1",
            thesis_formed="Thesis 1",
        )
        mem.add_turn(
            "s1",
            "msg2",
            "resp2",
            thesis_formed="",
        )

        theses = mem.get_theses(days=30)
        assert len(theses) == 1
        assert theses[0].thesis_formed == "Thesis 1"


def test_summarize_session():
    """Test session summary."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "test_memory.jsonl"
        mem = reset_memory_for_test(path)

        mem.add_turn("s1", "msg1", "resp1", ticker_discussed="AAPL", category="ticker_analysis")
        mem.add_turn("s1", "msg2", "resp2", ticker_discussed="TSLA", category="ticker_analysis")
        mem.add_turn("s1", "msg3", "resp3", category="general")

        summary = mem.summarize_session("s1")
        assert summary["total_turns"] == 3
        assert "AAPL" in summary["tickers_discussed"]
        assert "TSLA" in summary["tickers_discussed"]
        assert summary["categories"]["ticker_analysis"] == 2
        assert summary["categories"]["general"] == 1


def test_get_stats():
    """Test global stats."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "test_memory.jsonl"
        mem = reset_memory_for_test(path)

        mem.add_turn("s1", "msg1", "resp1", ticker_discussed="AAPL", category="ticker_analysis")
        mem.add_turn("s1", "msg2", "resp2", ticker_discussed="AAPL", category="ticker_analysis")
        mem.add_turn("s2", "msg3", "resp3", ticker_discussed="TSLA", category="ticker_analysis")

        stats = mem.get_stats()
        assert stats["total_turns"] == 3
        assert stats["total_sessions"] == 2
        assert stats["categories"]["ticker_analysis"] == 3
        assert stats["top_tickers"][0]["ticker"] == "AAPL"
        assert stats["top_tickers"][0]["count"] == 2
