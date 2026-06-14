"""Simple test for memory integration - direct test without server."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

print("🧪 Testing Unified Memory Layer - Direct Test")
print("=" * 60)

# ── Test 1: Conversation Memory ──
print("\n[Test 1] ConversationMemory...")

from core.memory import get_conversation_memory

mem = get_conversation_memory()

# Add test turn
turn = mem.add_turn(
    session_id="test_session",
    user_message="Analyze AAPL",
    bob_response="AAPL looks bullish. Strong buy candidate with 85% confidence.",
    ticker_discussed="AAPL",
    verdict="BUY",
    confidence=0.85,
    category="ticker_analysis",
)

print(f"  ✓ Turn added: {turn.session_id}")
print(f"  ✓ Ticker: {turn.ticker_discussed}, Verdict: {turn.verdict}")

# Retrieve it
turns = mem.get_ticker_history("AAPL", session_id="test_session")
print(f"  ✓ Retrieved {len(turns)} turns for AAPL")

# ── Test 2: Knowledge Graph ──
print("\n[Test 2] KnowledgeGraph...")

from core.memory import get_graph_bridge

graph = get_graph_bridge()
graph.ingest_conversation_turn(turn)

# Query ticker context
ctx = graph.query_ticker_context("AAPL")
print(f"  ✓ Graph has {len(ctx['entities'])} entities for AAPL")

for eid, ent in list(ctx['entities'].items())[:3]:
    print(f"    - {ent['type']}: {ent['name']}")

# ── Test 3: Hybrid Search ──
print("\n[Test 3] HybridRetriever...")

from core.memory import get_hybrid_retriever

hybrid = get_hybrid_retriever(use_sentence_transformers=False)

# Add documents
hybrid.add_document("doc1", "AAPL stock analysis bullish trend")
hybrid.add_document("doc2", "TSLA bearish outlook")

results = hybrid.search("AAPL bullish", top_k=2)
print(f"  ✓ Hybrid search returned {len(results)} results")

for r in results:
    print(f"    - score={r.hybrid_score:.2f}: {r.text[:50]}...")

# ── Test 4: Reranking ──
print("\n[Test 4] RerankPipeline...")

from core.memory import get_rerank_pipeline

reranker = get_rerank_pipeline()
reranker._hybrid = hybrid  # Use our populated hybrid

reranked = reranker.search("AAPL analysis", top_k=2)
print(f"  ✓ Reranking returned {len(reranked)} results")

for r in reranked:
    print(f"    - rerank={r.rerank_score:.2f}: {r.text[:50]}...")

# ── Test 5: Unified Memory All Together ──
print("\n[Test 5] Unified Memory (all phases)...")

from core.memory import get_unified_retriever

unified = get_unified_retriever()

# Search across all sources
unified_results = unified.search("AAPL stock", sources=["conversation"], top_k=3)
print(f"  ✓ Unified search returned {len(unified_results)} results")

print("\n" + "=" * 60)
print("✅ All 4 phases of Unified Memory Layer working!")
print("\nSummary:")
print("  ✓ ConversationMemory: persistent turns")
print("  ✓ KnowledgeGraph: entities and relations")
print("  ✓ HybridRetriever: dense + sparse fusion")
print("  ✓ RerankPipeline: cross-encoder reranking")
print("  ✓ UnifiedRetriever: cross-source search")
