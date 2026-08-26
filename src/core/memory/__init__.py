"""Memory module for Bob's persistent conversation memory.

Includes:
- ConversationMemory: basic conversational memory
- Unified Memory Layer (4 phases):
  1. UnifiedRetriever: adapter pattern for cross-source search
  2. HybridRetriever: dense+sparse fusion search
  3. RerankPipeline: cross-encoder reranking
  4. GraphMemoryBridge: knowledge graph with entities
- FeedbackLoop: learning system from trade outcomes
"""

from .conversation_memory import (
    ConversationMemory,
    ConversationTurn,
    get_conversation_memory,
    reset_memory_for_test,
)

__all__ = [
    "ConversationMemory",
    "ConversationTurn",
    "GraphMemoryBridge",
    "HybridRetriever",
    "KnowledgeGraph",
    "RerankPipeline",
    "RetrievalResult",
    "UnifiedRetriever",
    "get_conversation_memory",
    "get_feedback_loop",
    "get_graph_bridge",
    "get_hybrid_retriever",
    "get_rerank_pipeline",
    "get_unified_retriever",
    "reset_graph_bridge",
    "reset_hybrid_retriever",
    "reset_memory_for_test",
    "reset_rerank_pipeline",
]

# Unified Memory Layer - available for import
from .graph import (
    GraphMemoryBridge,
    KnowledgeGraph,
    get_graph_bridge,
    reset_graph_bridge,
)
from .hybrid import (
    HybridRetriever,
    get_hybrid_retriever,
    reset_hybrid_retriever,
)
from .reranker import (
    RerankPipeline,
    get_rerank_pipeline,
    reset_rerank_pipeline,
)
from .unified import (
    RetrievalResult,
    UnifiedRetriever,
    get_unified_retriever,
)


def get_feedback_loop():
    """Get FeedbackLoop singleton for trade learning."""
    try:
        from core.trading.feedback_loop import get_feedback_loop as _get

        return _get()
    except ImportError:
        return None
