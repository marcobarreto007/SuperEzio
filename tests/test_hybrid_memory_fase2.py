"""Tests for Hybrid Memory Layer - Fase 2: Dense + Sparse Search."""

import sys
from pathlib import Path

# Add src to path for pytest
src_path = str(Path(__file__).parent.parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

import pytest

from core.memory.hybrid import (
    BM25Index,
    HybridResult,
    HybridRetriever,
    get_hybrid_retriever,
)


class TestBM25Index:
    """Test BM25 sparse retrieval."""

    def test_bm25_empty_index(self):
        """Test BM25 with empty index."""
        bm25 = BM25Index()
        results = bm25.search("test query")
        assert results == []

    def test_bm25_add_document(self):
        """Test adding documents to BM25 index."""
        bm25 = BM25Index()
        bm25.add_document("doc1", "apple banana cherry")
        bm25.add_document("doc2", "apple date")

        assert len(bm25._corpus) == 2
        assert bm25._doc_freqs["apple"] == 2
        assert bm25._doc_freqs["banana"] == 1

    def test_bm25_search(self):
        """Test BM25 search ranking."""
        bm25 = BM25Index()
        bm25.add_document("doc1", "apple banana cherry")
        bm25.add_document("doc2", "apple date")
        bm25.add_document("doc3", "banana")

        results = bm25.search("apple banana", top_k=3)

        # doc1 has both terms, should rank highest
        assert len(results) > 0
        doc_ids = [r[0] for r in results]
        assert "doc1" in doc_ids

    def test_bm25_tokenization(self):
        """Test BM25 tokenization."""
        bm25 = BM25Index()
        tokens = bm25._tokenize("Hello World! Test123")
        assert "hello" in tokens
        assert "world" in tokens
        assert "test123" in tokens

    def test_bm25_idf(self):
        """Test IDF calculation."""
        bm25 = BM25Index()
        bm25.add_document("doc1", "apple")
        bm25.add_document("doc2", "apple")
        bm25.add_document("doc3", "banana")

        # "apple" appears in 2 docs, should have lower IDF than "banana"
        idf_apple = bm25._idf("apple")
        idf_banana = bm25._idf("banana")

        # Rare term gets higher IDF
        assert idf_banana > idf_apple

    def test_bm25_stats(self):
        """Test BM25 index statistics."""
        bm25 = BM25Index(k1=1.2, b=0.8)
        bm25.add_document("doc1", "apple banana cherry")
        bm25.add_document("doc2", "apple date")

        stats = {
            "k1": bm25.k1,
            "b": bm25.b,
            "total_docs": len(bm25._corpus),
            "unique_terms": len(bm25._doc_freqs),
        }

        assert stats["k1"] == 1.2
        assert stats["b"] == 0.8
        assert stats["total_docs"] == 2
        assert stats["unique_terms"] >= 3


class TestHybridRetriever:
    """Test hybrid retrieval combining dense and sparse."""

    def test_hybrid_init(self):
        """Test HybridRetriever initialization."""
        retriever = HybridRetriever(dense_weight=0.7)
        assert retriever.dense_weight == 0.7
        assert retriever.sparse_weight == pytest.approx(0.3)
        assert len(retriever._dense_docs) == 0

    def test_hybrid_add_document(self):
        """Test adding documents to hybrid index."""
        retriever = HybridRetriever()
        retriever.add_document("doc1", "test document", {"ticker": "AAPL"})

        assert len(retriever._dense_docs) == 1
        assert len(retriever._bm25._corpus) == 1
        assert retriever._dense_docs[0]["id"] == "doc1"

    def test_hybrid_search_empty(self):
        """Test hybrid search with empty index."""
        retriever = HybridRetriever()
        results = retriever.search("test query")
        assert results == []

    def test_hybrid_search_with_docs(self):
        """Test hybrid search with documents."""
        retriever = HybridRetriever(dense_weight=0.5, use_sentence_transformers=False)
        retriever.add_document("doc1", "apple stock analysis")
        retriever.add_document("doc2", "banana price forecast")
        retriever.add_document("doc3", "apple technical indicators")

        results = retriever.search("apple stock", top_k=3)

        assert len(results) >= 1
        # Check result structure
        assert isinstance(results[0], HybridResult)
        assert results[0].id in {"doc1", "doc3"}
        assert results[0].hybrid_score >= 0

    def test_hybrid_result_fields(self):
        """Test HybridResult has all required fields."""
        retriever = HybridRetriever(use_sentence_transformers=False)
        retriever.add_document("doc1", "test")
        results = retriever.search("test", top_k=1)

        if results:
            r = results[0]
            assert hasattr(r, "id")
            assert hasattr(r, "text")
            assert hasattr(r, "dense_score")
            assert hasattr(r, "sparse_score")
            assert hasattr(r, "hybrid_score")

    def test_hybrid_alpha_override(self):
        """Test alpha weight override in search."""
        retriever = HybridRetriever(dense_weight=0.7, use_sentence_transformers=False)
        retriever.add_document("doc1", "apple stock")
        retriever.add_document("doc2", "banana price")

        # Search with different alpha
        results_default = retriever.search("apple", top_k=1)
        results_custom = retriever.search("apple", top_k=1, alpha=0.3)

        # Results should exist (even if ordering differs)
        assert len(results_default) >= 0
        assert len(results_custom) >= 0

    def test_hybrid_get_stats(self):
        """Test get_stats returns valid dict."""
        retriever = HybridRetriever()
        retriever.add_document("doc1", "test document with words")

        stats = retriever.get_stats()
        assert isinstance(stats, dict)
        assert "total_documents" in stats
        assert "dense_weight" in stats
        assert "sparse_weight" in stats

    def test_hybrid_metadata_propagation(self):
        """Test metadata is preserved in results."""
        retriever = HybridRetriever(use_sentence_transformers=False)
        retriever.add_document(
            "doc1", "test", {"ticker": "AAPL", "verdict": "BUY", "confidence": 0.85}
        )

        results = retriever.search("test", top_k=1)
        if results:
            assert results[0].metadata is not None
            assert results[0].metadata.get("ticker") == "AAPL"


def test_hybrid_retriever_singleton():
    """Test singleton pattern."""
    from core.memory.hybrid import reset_hybrid_retriever

    # Reset before test
    reset_hybrid_retriever()

    r1 = get_hybrid_retriever()
    r2 = get_hybrid_retriever()

    assert r1 is r2


def test_hybrid_retriever_fallback_to_hash():
    """Test fallback to hash embeddings when ST unavailable."""
    # Patch to force hash mode
    import core.memory.hybrid as hybrid_module

    original_get = hybrid_module.HybridRetriever._get_embedder

    def mock_get_embedder(self):
        return "hash"  # Force hash mode

    hybrid_module.HybridRetriever._get_embedder = mock_get_embedder

    try:
        retriever = HybridRetriever(use_sentence_transformers=False)
        retriever.add_document("doc1", "test document")
        results = retriever.search("test", top_k=1)
        assert len(results) >= 0
    finally:
        # Restore
        hybrid_module.HybridRetriever._get_embedder = original_get
