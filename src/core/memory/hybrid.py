"""Hybrid Search — Fase 2: Dense (SentenceTransformers) + Sparse (BM25).

Implementa busca híbrida combinando:
- Dense: embeddings semânticos (SentenceTransformers ou Blake2b hash fallback)
- Sparse: BM25 keyword matching

Fusão: score = α·dense_score + (1-α)·sparse_score

Técnicas 2026:
- BM25 com parâmetros otimizados (k1=1.5, b=0.75)
- Score fusion com α dinâmico baseado em query length
- Reranking opcional via late interaction
"""

from __future__ import annotations

import logging
import math
from collections import Counter
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class HybridResult:
    """Resultado de busca híbrida."""

    id: str
    text: str
    source: str
    dense_score: float
    sparse_score: float
    hybrid_score: float
    metadata: dict[str, Any] | None = None


class BM25Index:
    """BM25 sparse retrieval index."""

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        """
        Args:
            k1: Term saturation parameter (1.2-2.0 typical)
            b: Length normalization (0.75 standard)
        """
        self.k1 = k1
        self.b = b
        self._corpus: list[dict[str, Any]] = []
        self._doc_freqs: Counter = Counter()  # term -> document frequency
        self._doc_lengths: list[int] = []
        self._avg_doc_length: float = 0.0

    def add_document(self, doc_id: str, text: str, metadata: dict[str, Any] | None = None):
        """Add a document to the index."""
        tokens = self._tokenize(text)
        self._corpus.append(
            {
                "id": doc_id,
                "text": text,
                "tokens": set(tokens),
                "token_counts": Counter(tokens),
                "metadata": metadata or {},
            }
        )
        self._doc_lengths.append(len(tokens))

        # Update document frequencies
        for token in set(tokens):
            self._doc_freqs[token] += 1

        # Recompute average
        if self._doc_lengths:
            self._avg_doc_length = sum(self._doc_lengths) / len(self._doc_lengths)

    def _tokenize(self, text: str) -> list[str]:
        """Simple tokenization for BM25."""
        import re

        text = text.lower()
        tokens = re.findall(r"\b[a-z0-9_]{3,}\b", text)
        return tokens

    def _idf(self, term: str) -> float:
        """Compute IDF for a term."""
        n = len(self._corpus)
        df = self._doc_freqs.get(term, 0)
        if df == 0:
            return 0.0
        return math.log((n - df + 0.5) / (df + 0.5) + 1.0)

    def search(self, query: str, top_k: int = 10) -> list[tuple[str, float]]:
        """
        Search using BM25.

        Returns:
            List of (doc_id, score) tuples
        """
        if not self._corpus:
            return []

        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        scores: dict[str, float] = {}

        for doc in self._corpus:
            doc_id = doc["id"]
            doc_len = self._doc_lengths[self._corpus.index(doc)]
            avg_len = self._avg_doc_length

            score = 0.0
            for term in query_tokens:
                if term not in doc["tokens"]:
                    continue

                # BM25 formula
                idf = self._idf(term)
                tf = doc["token_counts"][term]

                # Length normalization
                norm = 1 - self.b + self.b * (doc_len / (avg_len + 1e-8))
                norm = max(0.01, norm)  # Avoid division by zero

                term_score = idf * (tf * (self.k1 + 1)) / (tf + self.k1 * norm)
                score += term_score

            if score > 0:
                scores[doc_id] = score

        # Sort by score
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return ranked[:top_k]


class HybridRetriever:
    """Hybrid retrieval combining dense and sparse search."""

    def __init__(
        self,
        dense_weight: float = 0.7,  # α
        sparse_weight: float | None = None,  # 1-α
        use_sentence_transformers: bool = True,
    ):
        """
        Args:
            dense_weight: Weight for dense embeddings (0-1)
            sparse_weight: Weight for sparse BM25 (defaults to 1-dense_weight)
            use_sentence_transformers: If True, use ST; else use Blake2b hash
        """
        self.dense_weight = dense_weight
        self.sparse_weight = sparse_weight or (1.0 - dense_weight)
        self.use_st = use_sentence_transformers

        self._bm25 = BM25Index()
        self._dense_docs: list[dict[str, Any]] = []  # For dense search
        self._embedder: Any = None

    def _get_embedder(self):
        """Lazy load sentence transformer or use hash."""
        if self._embedder is not None:
            return self._embedder

        if self.use_st:
            try:
                from sentence_transformers import SentenceTransformer

                self._embedder = SentenceTransformer("all-MiniLM-L6-v2")
                self._embedder.to("cpu")
                logger.info("HybridRetriever: using SentenceTransformers")
                return self._embedder
            except (ImportError, Exception) as e:
                logger.warning("SentenceTransformers unavailable: %s, using hash embeddings", e)
                self.use_st = False

        # Fallback to hash
        self._embedder = "hash"
        return self._embedder

    def _encode(self, texts: list[str]) -> list[list[float]]:
        """Encode texts using available embedder."""
        embedder = self._get_embedder()

        if embedder == "hash":
            from core.memory.conversation_memory import _hashed_embedding

            return [_hashed_embedding(t) for t in texts]

        # SentenceTransformer

        vecs = embedder.encode(
            texts,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return vecs.tolist() if hasattr(vecs, "tolist") else vecs

    def add_document(self, doc_id: str, text: str, metadata: dict[str, Any] | None = None):
        """Add document to both dense and sparse indices."""
        # Add to BM25
        self._bm25.add_document(doc_id, text, metadata)

        # Add to dense corpus
        self._dense_docs.append(
            {
                "id": doc_id,
                "text": text,
                "metadata": metadata or {},
            }
        )

    def _dense_search(self, query: str, top_k: int = 10) -> list[tuple[str, float]]:
        """Dense semantic search."""
        if not self._dense_docs:
            return []

        from core.memory.conversation_memory import _cosine_sim, _hashed_embedding

        # Encode query
        if self._get_embedder() == "hash":
            query_emb = _hashed_embedding(query)
        else:
            query_emb = self._encode([query])[0]

        # Encode all docs
        doc_texts = [d["text"] for d in self._dense_docs]
        doc_embs = self._encode(doc_texts)

        # Compute similarities
        scores = []
        for i, doc_emb in enumerate(doc_embs):
            sim = _cosine_sim(query_emb, doc_emb)
            if sim > 0:
                scores.append((self._dense_docs[i]["id"], sim))

        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]

    def search(
        self,
        query: str,
        top_k: int = 10,
        alpha: float | None = None,
    ) -> list[HybridResult]:
        """
        Hybrid search combining dense and sparse.

        Args:
            query: Search query
            top_k: Number of results
            alpha: Dense weight override (uses self.dense_weight if None)

        Returns:
            List of HybridResult sorted by hybrid_score
        """
        dense_w = alpha if alpha is not None else self.dense_weight
        sparse_w = 1.0 - dense_w

        # Get both result sets
        dense_results = dict(self._dense_search(query, top_k=top_k * 2))
        sparse_results = dict(self._bm25.search(query, top_k=top_k * 2))

        # Combine scores
        combined: dict[str, HybridResult] = {}

        # Process dense results
        for doc_id, dense_score in dense_results.items():
            # Find doc metadata
            doc = next((d for d in self._dense_docs if d["id"] == doc_id), None)
            if doc:
                combined[doc_id] = HybridResult(
                    id=doc_id,
                    text=doc["text"][:300],
                    source="hybrid",
                    dense_score=float(dense_score),
                    sparse_score=0.0,
                    hybrid_score=float(dense_w * dense_score),
                    metadata=doc.get("metadata"),
                )

        # Add/update with sparse results
        for doc_id, sparse_score in sparse_results.items():
            # Find doc metadata
            doc = next((d for d in self._dense_docs if d["id"] == doc_id), None)
            if doc:
                if doc_id in combined:
                    # Update existing
                    combined[doc_id].sparse_score = float(sparse_score)
                    combined[doc_id].hybrid_score = (
                        dense_w * combined[doc_id].dense_score + sparse_w * sparse_score
                    )
                else:
                    # New from sparse
                    combined[doc_id] = HybridResult(
                        id=doc_id,
                        text=doc["text"][:300],
                        source="hybrid",
                        dense_score=0.0,
                        sparse_score=float(sparse_score),
                        hybrid_score=float(sparse_w * sparse_score),
                        metadata=doc.get("metadata"),
                    )

        # Sort by hybrid score
        results = sorted(combined.values(), key=lambda r: r.hybrid_score, reverse=True)
        return results[:top_k]

    def get_stats(self) -> dict[str, Any]:
        """Get index statistics."""
        return {
            "total_documents": len(self._dense_docs),
            "dense_weight": self.dense_weight,
            "sparse_weight": self.sparse_weight,
            "use_sentence_transformers": self.use_st,
            "avg_doc_length": self._bm25._avg_doc_length,
            "unique_terms": len(self._bm25._doc_freqs),
        }


# Singleton
_hybrid_retriever: HybridRetriever | None = None


def reset_hybrid_retriever() -> None:
    """Reset singleton (for testing)."""
    global _hybrid_retriever
    _hybrid_retriever = None


def get_hybrid_retriever(
    dense_weight: float = 0.7,
    use_sentence_transformers: bool = True,
) -> HybridRetriever:
    """Get singleton HybridRetriever."""
    global _hybrid_retriever
    if _hybrid_retriever is None:
        _hybrid_retriever = HybridRetriever(
            dense_weight=dense_weight,
            use_sentence_transformers=use_sentence_transformers,
        )
        logger.info(
            "HybridRetriever initialized (dense=%.2f, sparse=%.2f)",
            _hybrid_retriever.dense_weight,
            _hybrid_retriever.sparse_weight,
        )
    return _hybrid_retriever
