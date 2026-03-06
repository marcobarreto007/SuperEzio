"""RAG (Retrieval-Augmented Generation) package — semantic + keyword forensic search."""
from .engine import ForensicRAG, forensic_rag
from .fraud_rag import FraudRAG, fraud_rag
from .macro_dataset import MacroDataset, macro_engine

__all__ = [
    "ForensicRAG",
    "forensic_rag",
    "FraudRAG",
    "fraud_rag",
    "MacroDataset",
    "macro_engine",
]