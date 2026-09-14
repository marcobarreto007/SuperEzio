"""RAG + pattern matching — semantic search (embeddings) and keyword forensics."""

from .engine import ForensicRAG, forensic_rag
from .fraud_rag import FraudPatternMatcher, fraud_patterns
from .macro_dataset import MacroDataset, macro_engine
from .tfidf_rag import TfidfRetriever

__all__ = [
    "ForensicRAG",
    "FraudPatternMatcher",
    "MacroDataset",
    "TfidfRetriever",
    "forensic_rag",
    "fraud_patterns",
    "macro_engine",
]
