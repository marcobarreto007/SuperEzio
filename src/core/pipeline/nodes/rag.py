"""RAG forensics node — enriches agent context with historical fraud intelligence."""

from langgraph.config import get_stream_writer


async def node_rag_forensics(state: dict) -> dict:
    """Semantic forensic RAG: search historical fraud patterns for this ticker/intent."""
    writer = get_stream_writer()
    run_id = state.get("run_id", "")

    if state.get("rag_context") is not None:
        writer(
            {
                "type": "PIPELINE_STEP",
                "run_id": run_id,
                "step": "rag_forensics",
                "status": "skipped_duplicate",
            }
        )
        return {}

    writer(
        {
            "type": "PIPELINE_STEP",
            "run_id": run_id,
            "step": "rag_forensics",
            "status": "started",
        }
    )

    ticker = state.get("ticker", "")
    message = state.get("message", "")
    intent = state.get("intent", "")

    query_parts = []
    if ticker:
        query_parts.append(f"Ticker: {ticker}")
    if intent:
        query_parts.append(f"Intent: {intent}")
    if message and not ticker:
        query_parts.append(message[:200])
    query = " ".join(query_parts)

    try:
        from ...rag.engine import forensic_rag

        results = forensic_rag.search(query, top_k=5)
        rag_context = forensic_rag.format_context(results)
        writer(
            {
                "type": "PIPELINE_STEP",
                "run_id": run_id,
                "step": "rag_forensics",
                "status": "completed",
                "matches": len(results),
                "context_chars": len(rag_context),
            }
        )
        return {"rag_context": rag_context}
    except Exception as exc:
        writer(
            {
                "type": "PIPELINE_STEP",
                "run_id": run_id,
                "step": "rag_forensics",
                "status": "degraded",
                "error": str(exc)[:200],
            }
        )
        return {"rag_context": ""}
