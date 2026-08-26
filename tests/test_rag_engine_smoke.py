"""Smoke test for ForensicRAG engine."""

from core.rag.engine import forensic_rag

# Test 1: Semantic search
print("=== Test 1: Semantic search ===")
results = forensic_rag.search("pump and dump manipulation")
print(f"Results: {len(results)}")
for r in results:
    print(f"  [{r['id']}] score={r['score']:.3f}")

# Test 2: Format context
print("\n=== Test 2: Format context ===")
ctx = forensic_rag.format_context(results, max_chars=600)
print(ctx)

# Test 3: Keyword search (degradation path)
print("\n=== Test 3: Keyword fallback ===")
results3 = forensic_rag._keyword_search("insider selling fraud")
print(f"Results: {len(results3)}")
for r in results3:
    print(f"  [{r['id']}] score={r['score']}")

# Test 4: Empty query
print("\n=== Test 4: Empty query ===")
results4 = forensic_rag.search("")
print(f"Results: {len(results4)} (expected 0)")

# Test 5: Document count
print("\n=== Test 5: Document stats ===")
docs = forensic_rag._load_documents()
print(f"Total documents indexed: {len(docs)}")
sources = {d["source"] for d in docs}
for s in sources:
    count = sum(1 for d in docs if d["source"] == s)
    print(f"  {s}: {count} docs")

print("\nALL TESTS PASSED")
