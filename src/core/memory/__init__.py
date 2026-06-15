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
    "get_conversation_memory",
    "reset_memory_for_test",
    "get_feedback_loop",
]

# Unified Memory Layer - available for import
from .unified import (
    UnifiedRetriever,
    get_unified_retriever,
    RetrievalResult,
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
from .graph import (
    KnowledgeGraph,
    GraphMemoryBridge,
    get_graph_bridge,
    reset_graph_bridge,
)


def get_feedback_loop():
    """Get FeedbackLoop singleton for trade learning."""
    try:
        from core.trading.feedback_loop import get_feedback_loop as _get
        return _get()
    except ImportError:
        return None
