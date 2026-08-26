"""Tests for Unified Memory Layer - Fase 1: Adapter Pattern."""

import sys
from pathlib import Path

# Add src to path for pytest
src_path = str(Path(__file__).parent.parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

import tempfile
from datetime import UTC

from core.memory.unified import (
    ConversationMemoryAdapter,
    PaperJournalAdapter,
    RetrievalResult,
    UnifiedRetriever,
)


def test_conversation_adapter_ingest():
    """Test conversation memory adapter ingests to RAG."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Setup: memória com alguns turnos
        from core.memory import ConversationMemory

        mem_path = Path(tmpdir) / "memory.jsonl"
        mem = ConversationMemory(mem_path, enforce_session_filter=False)
        mem.add_turn(
            "session1",
            "Should I buy AAPL?",
            "Apple looks strong with upcoming earnings.",
            ticker_discussed="AAPL",
            thesis_formed="Strong earnings expected",
            verdict="BUY_CANDIDATE",
            confidence=75.0,
            category="ticker_analysis",
        )
        mem.add_turn(
            "session1",
            "What about TSLA?",
            "Tesla is volatile but has momentum.",
            ticker_discussed="TSLA",
            thesis_formed="Momentum play",
            verdict="WAIT",
            confidence=60.0,
            category="ticker_analysis",
        )

        # Test: adapter deve ingerir no ForensicRAG mock
        from core.rag.engine import ForensicRAG

        rag = ForensicRAG(data_dir=Path(tmpdir) / "patterns")
        adapter = ConversationMemoryAdapter(mem_path)

        # Ingest
        count = adapter.ingest_to_rag(rag)

        assert count == 2


def test_conversation_adapter_search():
    """Test direct search via adapter."""
    with tempfile.TemporaryDirectory() as tmpdir:
        from core.memory import ConversationMemory

        mem_path = Path(tmpdir) / "memory.jsonl"
        mem = ConversationMemory(mem_path, enforce_session_filter=False)
        mem.add_turn(
            "s1",
            "Tesla stock analysis",
            "TSLA has strong momentum",
            ticker_discussed="TSLA",
            thesis_formed="Bullish momentum",
        )

        adapter = ConversationMemoryAdapter(mem_path)
        results = adapter.search("Tesla EV stock", top_k=3)

        assert len(results) > 0
        assert results[0].source == "conversation"
        assert results[0].ticker == "TSLA"
        assert results[0].score > 0


def test_paper_journal_adapter_ingest():
    """Test paper journal adapter ingests to RAG."""
    with tempfile.TemporaryDirectory() as tmpdir:
        from datetime import datetime

        from core.trading.paper_journal import PaperJournal, PaperTrade

        journal_path = Path(tmpdir) / "journal.jsonl"
        journal = PaperJournal(journal_path)

        # Add some trades
        journal.open_trade(
            PaperTrade(
                trade_id="trade1",
                ticker="AAPL",
                thesis="Strong earnings",
                direction="long",
                entry_date=datetime.now(UTC).isoformat(),
                entry_price=150.0,
                shares=10,
                entry_reasoning="Technical breakout",
                verdict_at_entry="BUY_CANDIDATE",
                risk_assessment="moderate",
                expected_holding_period="swing",
            )
        )

        # Test adapter
        from core.rag.engine import ForensicRAG

        rag = ForensicRAG(data_dir=Path(tmpdir) / "patterns")
        adapter = PaperJournalAdapter(journal_path)

        count = adapter.ingest_to_rag(rag)
        assert count == 1


def test_paper_journal_adapter_search():
    """Test paper journal search."""
    with tempfile.TemporaryDirectory() as tmpdir:
        from datetime import datetime

        from core.trading.paper_journal import PaperJournal, PaperTrade

        journal_path = Path(tmpdir) / "journal.jsonl"
        journal = PaperJournal(journal_path)

        journal.open_trade(
            PaperTrade(
                trade_id="trade1",
                ticker="NVDA",
                thesis="AI growth story",
                direction="long",
                entry_date=datetime.now(UTC).isoformat(),
                entry_price=450.0,
                shares=5,
                entry_reasoning="AI demand",
                verdict_at_entry="BUY_CANDIDATE",
                risk_assessment="high",
                expected_holding_period="position",
            )
        )

        adapter = PaperJournalAdapter(journal_path)
        results = adapter.search("AI chip stock", top_k=3)

        assert len(results) > 0
        assert results[0].source == "paper_trade"
        assert results[0].ticker == "NVDA"


def test_paper_journal_adapter_rejects_unprovenanced_rows(tmp_path):
    """Legacy or synthetic rows cannot silently enter financial RAG."""
    journal_path = tmp_path / "legacy.jsonl"
    journal_path.write_text(
        '{"trade_id":"legacy","ticker":"AAPL","thesis":"synthetic"}\n',
        encoding="utf-8",
    )
    adapter = PaperJournalAdapter(journal_path)

    assert adapter.search("AAPL synthetic", top_k=3) == []


def test_unified_retriever_search():
    """Test unified retriever searches across sources."""
    retriever = UnifiedRetriever()

    # Mock search com resultados
    results = retriever.search("test query", top_k=3, sources=["conversation"])

    # Deve retornar lista (mesmo que vazia)
    assert isinstance(results, list)


def test_unified_retriever_format_context():
    """Test context formatting."""
    retriever = UnifiedRetriever()

    # Mock results
    results = [
        RetrievalResult(
            id="1",
            text="Test conversation about AAPL",
            source="conversation",
            score=0.85,
            ticker="AAPL",
            verdict="BUY_CANDIDATE",
            timestamp="2026-06-14T10:00:00Z",
        ),
        RetrievalResult(
            id="2",
            text="Paper trade on TSLA",
            source="paper_trade",
            score=0.72,
            ticker="TSLA",
            verdict="win",
        ),
    ]

    context = retriever.format_context(results, max_chars=500)

    assert "[UNIFIED_MEMORY]" in context
    assert "💬 Conversation" in context
    assert "📈 Paper Trade" in context
    assert "AAPL" in context
    assert "TSLA" in context


def test_unified_retriever_ingest_all():
    """Test ingest all sources."""
    with tempfile.TemporaryDirectory() as tmpdir:
        from datetime import datetime

        from core.memory import ConversationMemory
        from core.trading.paper_journal import PaperJournal, PaperTrade

        # Setup memória
        mem_path = Path(tmpdir) / "memory.jsonl"
        mem = ConversationMemory(mem_path, enforce_session_filter=False)
        mem.add_turn("s1", "Buy AAPL?", "Apple strong", ticker_discussed="AAPL")

        # Setup journal
        journal_path = Path(tmpdir) / "journal.jsonl"
        journal = PaperJournal(journal_path)
        journal.open_trade(
            PaperTrade(
                trade_id="t1",
                ticker="TSLA",
                thesis="Momentum",
                direction="long",
                entry_date=datetime.now(UTC).isoformat(),
                entry_price=200.0,
                shares=10,
                entry_reasoning="Breakout",
                verdict_at_entry="BUY",
                risk_assessment="moderate",
                expected_holding_period="swing",
            )
        )

        # Criar unified retriever com paths temporários
        from core.memory.unified import UnifiedRetriever

        retriever = UnifiedRetriever()
        retriever._conv_adapter = ConversationMemoryAdapter(mem_path)
        retriever._journal_adapter = PaperJournalAdapter(journal_path)

        # Ingestar (sem ForensicRAG real)
        counts = retriever.ingest_all_to_rag()

        # Verificar que contou
        assert "conversation" in counts
        assert "paper_trades" in counts
        assert counts.get("conversation", 0) >= 0
        assert counts.get("paper_trades", 0) >= 0


def test_retrieval_result_to_rag_format():
    """Test conversion to RAG format."""
    result = RetrievalResult(
        id="test1",
        text="Test content",
        source="conversation",
        score=0.9,
        ticker="AAPL",
        verdict="BUY",
    )

    rag_format = result.to_rag_format()

    assert rag_format["id"] == "test1"
    assert rag_format["text"] == "Test content"
    assert rag_format["source"] == "conversation"
    assert rag_format["score"] == 0.9


def test_unified_retriever_singleton():
    """Test singleton pattern."""
    from core.memory.unified import get_unified_retriever

    r1 = get_unified_retriever()
    r2 = get_unified_retriever()

    assert r1 is r2
