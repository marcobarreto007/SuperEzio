"""Tests for Re-ranking Layer - Fase 3: Cross-encoder reranking."""

import sys
from pathlib import Path

# Add src to path for pytest
src_path = str(Path(__file__).parent.parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

import pytest

from core.memory.reranker import (
    CrossEncoderReranker,
    RerankPipeline,
    RerankResult,
    get_rerank_pipeline,
    reset_rerank_pipeline,
)


class TestCrossEncoderReranker:
    """Test cross-encoder reranking."""

    def test_reranker_init(self):
        """Test CrossEncoderReranker initialization."""
        reranker = CrossEncoderReranker(
            model_name="ms-marco-MiniLM-L-6-v2",
            top_k=10,
        )
        assert reranker.model_name == "ms-marco-MiniLM-L-6-v2"
        assert reranker.top_k == 10
        assert reranker._model is None  # Lazy load

    def test_reranker_empty_candidates(self):
        """Test reranking with empty candidates."""
        reranker = CrossEncoderReranker()
        results = reranker.rerank("test query", [])
        assert results == []

    def test_reranker_fallback_no_model(self):
        """Test fallback when model unavailable."""
        reranker = CrossEncoderReranker()
        # Mock model load failure
        reranker._load_model = lambda: None

        candidates = [
            {"id": "doc1", "text": "test document", "score": 0.8, "source": "test"},
        ]
        results = reranker.rerank("query", candidates)

        assert len(results) == 1
        assert results[0].id == "doc1"
        # Without model, rerank_score equals original
        assert results[0].rerank_score == pytest.approx(0.8)

    def test_reranker_result_fields(self):
        """Test RerankResult has all required fields."""
        reranker = CrossEncoderReranker()
        reranker._load_model = lambda: None

        candidates = [
            {
                "id": "doc1",
                "text": "test document with content",
                "score": 0.75,
                "source": "conversation",
                "metadata": {"ticker": "AAPL"},
            }
        ]
        results = reranker.rerank("test", candidates)

        if results:
            r = results[0]
            assert r.id == "doc1"
            assert r.source == "conversation"
            assert r.metadata == {"ticker": "AAPL"}
            assert hasattr(r, "original_score")
            assert hasattr(r, "rerank_score")

    def test_reranker_truncates_text(self):
        """Test text is truncated to 300 chars."""
        reranker = CrossEncoderReranker()
        reranker._load_model = lambda: None

        long_text = "x" * 500
        candidates = [
            {"id": "doc1", "text": long_text, "score": 0.5, "source": "test"},
        ]
        results = reranker.rerank("q", candidates)

        if results:
            assert len(results[0].text) <= 300

    def test_reranker_respects_top_k(self):
        """Test reranking respects top_k parameter."""
        reranker = CrossEncoderReranker()
        reranker._load_model = lambda: None

        candidates = [
            {"id": f"doc{i}", "text": f"document {i}", "score": 0.5 + i * 0.1, "source": "test"}
            for i in range(20)
        ]
        results = reranker.rerank("query", candidates, top_k=5)

        assert len(results) <= 5


class TestRerankPipeline:
    """Test complete reranking pipeline."""

    def test_pipeline_init(self):
        """Test RerankPipeline initialization."""
        from core.memory.hybrid import HybridRetriever

        hybrid = HybridRetriever(use_sentence_transformers=False)
        pipeline = RerankPipeline(
            hybrid_retriever=hybrid,
            final_top_k=5,
        )
        assert pipeline.final_top_k == 5
        assert pipeline._hybrid is hybrid

    def test_pipeline_search_empty(self):
        """Test pipeline with empty index."""
        pipeline = RerankPipeline()
        results = pipeline.search("test query")
        # Should not crash, may return empty
        assert isinstance(results, list)

    def test_pipeline_search_with_docs(self):
        """Test pipeline with documents."""
        from core.memory.hybrid import HybridRetriever

        # Setup hybrid retriever with docs
        hybrid = HybridRetriever(use_sentence_transformers=False)
        hybrid.add_document("doc1", "apple stock analysis")
        hybrid.add_document("doc2", "banana price forecast")
        hybrid.add_document("doc3", "apple technical indicators")

        pipeline = RerankPipeline(hybrid_retriever=hybrid, final_top_k=3)
        results = pipeline.search("apple stock", top_k=3)

        assert isinstance(results, list)
        assert len(results) <= 3

        if results:
            # Check result type
            assert isinstance(results[0], RerankResult)

    def test_pipeline_format_context(self):
        """Test context formatting."""
        pipeline = RerankPipeline()

        results = [
            RerankResult(
                id="doc1",
                text="test content",
                original_score=0.7,
                rerank_score=0.85,
                source="conversation",
            )
        ]

        context = pipeline.format_context(results, max_chars=1000)

        assert "[RERANKED_MEMORY]" in context
        assert "original=" in context or "rerank=" in context
        assert "test content" in context

    def test_pipeline_format_context_empty(self):
        """Test context formatting with empty results."""
        pipeline = RerankPipeline()
        context = pipeline.format_context([])
        assert "No relevant memories found" in context

    def test_pipeline_format_context_truncates(self):
        """Test context formatting truncates long content."""
        pipeline = RerankPipeline()

        # Create many long results
        results = [
            RerankResult(
                id=f"doc{i}",
                text="x" * 500,  # Long text
                original_score=0.5,
                rerank_score=0.6,
                source="conversation",
            )
            for i in range(20)
        ]

        context = pipeline.format_context(results, max_chars=500)
        # Should truncate
        assert len(context) < 600
        assert "omitted" in context or len(context) < 550


def test_rerank_pipeline_singleton():
    """Test singleton pattern."""
    reset_rerank_pipeline()

    p1 = get_rerank_pipeline()
    p2 = get_rerank_pipeline()

    assert p1 is p2


def test_rerank_pipeline_reset():
    """Test reset function."""
    p1 = get_rerank_pipeline()
    reset_rerank_pipeline()

    p2 = get_rerank_pipeline()

    # After reset, should be different instance
    assert p1 is not p2


def test_reranker_with_hybrid_results():
    """Test reranking HybridResult objects."""
    from core.memory.hybrid import HybridResult

    reranker = CrossEncoderReranker()
    reranker._load_model = lambda: None

    hybrid_results = [
        HybridResult(
            id="doc1",
            text="apple stock analysis",
            source="conversation",
            dense_score=0.8,
            sparse_score=0.6,
            hybrid_score=0.72,
        ),
        HybridResult(
            id="doc2",
            text="banana forecast",
            source="paper_trade",
            dense_score=0.3,
            sparse_score=0.9,
            hybrid_score=0.54,
        ),
    ]

    results = reranker.rerank_hybrid_results("apple", hybrid_results, top_k=2)

    assert len(results) <= 2
    if results:
        assert isinstance(results[0], RerankResult)
        # Source should be preserved
        assert results[0].source in {"conversation", "paper_trade"}
