"""Contract tests: core.rag — ForensicRAG import and fallback behavior."""


def test_forensic_rag_import():
    from core.rag.engine import ForensicRAG

    rag = ForensicRAG()
    assert rag is not None
    assert hasattr(rag, "data_dir")


def test_forensic_rag_search_fallback():
    """search() works even without embedding model (keyword fallback)."""
    from core.rag.engine import ForensicRAG

    rag = ForensicRAG(data_dir="data/nonexistent_dir_for_test")
    results = rag.search("pump and dump scheme")
    assert isinstance(results, list)


def test_forensic_rag_format_context_empty():
    from core.rag.engine import ForensicRAG

    rag = ForensicRAG()
    ctx = rag.format_context([])
    assert isinstance(ctx, str)
    assert "No forensic pattern matches found" in ctx


def test_forensic_rag_add_document():
    """add_document appends to the module-level document cache."""
    from core.rag.engine import ForensicRAG, _documents_cache

    rag = ForensicRAG()
    before = len(_documents_cache)
    rag.add_document(
        "test-001",
        "A classic pump and dump involves artificial price inflation.",
        source="runtime",
    )
    assert len(_documents_cache) == before + 1
    assert _documents_cache[-1]["id"] == "test-001"
    assert _documents_cache[-1]["text"] == (
        "A classic pump and dump involves artificial price inflation."
    )


def test_forensic_rag_format_context_with_results():
    from core.rag.engine import ForensicRAG

    rag = ForensicRAG()
    results = [
        {
            "id": "test-001",
            "text": "Pump and Dump Pattern: inflation followed by dump.",
            "source": "test",
            "score": 0.9,
        }
    ]
    ctx = rag.format_context(results)
    assert isinstance(ctx, str)
    assert "Pump and Dump" in ctx
    assert "[RAG_FORENSICS]" in ctx


def test_forensic_rag_singleton():
    from core.rag import forensic_rag

    assert forensic_rag is not None


def test_rag_disabled_env():
    import os

    os.environ["SUPEREZIO_RAG_DISABLED"] = "1"
    from core.rag.engine import ForensicRAG

    rag = ForensicRAG(data_dir="data/nonexistent_dir_for_test")
    results = rag.search("anything")
    assert results == []
    del os.environ["SUPEREZIO_RAG_DISABLED"]


def test_fraud_rag_legacy_import():
    """FraudRAG (legacy keyword search) still importable for backward compat."""
    from core.rag.fraud_rag import FraudRAG

    rag = FraudRAG()
    assert rag is not None
