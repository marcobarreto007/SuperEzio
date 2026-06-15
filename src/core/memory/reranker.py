"""Re-ranking — Fase 3: Cross-encoder para refinar top-k results.

Implementa re-ranking usando cross-encoder para reranquear resultados
da busca híbrida, melhorando precisão com técnicas 2026.

Técnicas:
- Cross-encoder: ms-marco-MiniLM-L-6-v2 (ou similar)
- Late interaction: query-document pair scoring
- Top-k refino: rerank apenas top N da busca inicial
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class RerankResult:
    """Resultado de re-ranking."""
    id: str
    text: str
    original_score: float
    rerank_score: float
    source: str
    metadata: dict[str, Any] | None = None


class CrossEncoderReranker:
    """Re-ranker usando cross-encoder.

    Cross-encoders são mais precisos que bi-encoders para reranking
    porque processam query-document pair juntos.
    """

    def __init__(
        self,
        model_name: str = "ms-marco-MiniLM-L-6-v2",
        top_k: int = 20,
        batch_size: int = 32,
    ):
        """
        Args:
            model_name: Nome do modelo cross-encoder
            top_k: Número de candidatos a reranquear
            batch_size: Batch size para inferência
        """
        self.model_name = model_name
        self.top_k = top_k
        self.batch_size = batch_size
        self._model: Any = None

    def _load_model(self):
        """Lazy load do cross-encoder."""
        if self._model is not None:
            return self._model

        try:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(
                self.model_name,
                device="cpu",
                max_length=512,
            )
            logger.info("CrossEncoderReranker: loaded %s", self.model_name)
            return self._model
        except (ImportError, Exception) as e:
            logger.warning("CrossEncoder unavailable: %s", e)
            return None

    def rerank(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        top_k: int | None = None,
    ) -> list[RerankResult]:
        """
        Reranquear candidatos usando cross-encoder.

        Args:
            query: Query de busca
            candidates: Lista de dicts com {id, text, score, source, metadata?}
            top_k: Número final de resultados (padrão: self.top_k)

        Returns:
            Lista de RerankResult ordenada por rerank_score
        """
        model = self._load_model()
        if model is None:
            # Fallback: retorna ordenação original
            return [
                RerankResult(
                    id=c["id"],
                    text=c.get("text", "")[:300],
                    original_score=float(c.get("score", 0)),
                    rerank_score=float(c.get("score", 0)),
                    source=c.get("source", "unknown"),
                    metadata=c.get("metadata"),
                )
                for c in candidates[: top_k or self.top_k]
            ]

        k = top_k or self.top_k
        candidates = candidates[: self.top_k]

        if not candidates:
            return []

        # Preparar pares query-document
        pairs = [[query, doc.get("text", "")[:512]] for doc in candidates]

        # Inferir scores
        scores = model.predict(pairs, batch_size=self.batch_size)

        # Criar resultados
        results = [
            RerankResult(
                id=doc["id"],
                text=doc.get("text", "")[:300],
                original_score=float(doc.get("score", 0)),
                rerank_score=float(score),
                source=doc.get("source", "unknown"),
                metadata=doc.get("metadata"),
            )
            for doc, score in zip(candidates, scores)
        ]

        # Ordenar por rerank score
        results.sort(key=lambda r: r.rerank_score, reverse=True)
        return results[:k]

    def rerank_hybrid_results(
        self,
        query: str,
        hybrid_results: list[Any],  # HybridResult
        top_k: int = 10,
    ) -> list[RerankResult]:
        """
        Reranquear resultados do HybridRetriever.

        Args:
            query: Query de busca
            hybrid_results: Lista de HybridResult
            top_k: Número de resultados finais

        Returns:
            Lista de RerankResult
        """
        # Converter para formato esperado
        candidates = [
            {
                "id": r.id,
                "text": r.text,
                "score": r.hybrid_score,
                "source": r.source,
                "metadata": r.metadata,
            }
            for r in hybrid_results[: self.top_k]
        ]

        return self.rerank(query, candidates, top_k=top_k)


class RerankPipeline:
    """Pipeline completo: busca híbrida + re-ranking."""

    def __init__(
        self,
        hybrid_retriever: Any | None = None,
        cross_encoder_model: str = "ms-marco-MiniLM-L-6-v2",
        rerank_top_k: int = 20,
        final_top_k: int = 10,
    ):
        """
        Args:
            hybrid_retriever: Instância de HybridRetriever (ou None para lazy load)
            cross_encoder_model: Nome do modelo cross-encoder
            rerank_top_k: Quantos candidatos reranquear
            final_top_k: Quantos retornar
        """
        from core.memory.hybrid import get_hybrid_retriever

        self._hybrid = hybrid_retriever or get_hybrid_retriever()
        self._reranker = CrossEncoderReranker(
            model_name=cross_encoder_model,
            top_k=rerank_top_k,
        )
        self.final_top_k = final_top_k

    def search(
        self,
        query: str,
        top_k: int | None = None,
        alpha: float | None = None,
    ) -> list[RerankResult]:
        """
        Busca completa com re-ranking.

        Args:
            query: Query de busca
            top_k: Número final de resultados
            alpha: α para busca híbrida

        Returns:
            Lista de RerankResult
        """
        k = top_k or self.final_top_k

        # Fase 1: Busca híbrida (top N maior)
        hybrid_results = self._hybrid.search(
            query,
            top_k=self._reranker.top_k,
            alpha=alpha,
        )

        if not hybrid_results:
            return []

        # Fase 2: Re-ranking
        reranked = self._reranker.rerank_hybrid_results(
            query,
            hybrid_results,
            top_k=k,
        )

        return reranked

    def format_context(
        self,
        results: list[RerankResult],
        max_chars: int = 2000,
    ) -> str:
        """Formata resultados como contexto para o Bob."""
        if not results:
            return "[RERANKED_MEMORY] No relevant memories found."

        lines = [
            "[RERANKED_MEMORY] — Relevant context (hybrid search + cross-encoder rerank):"
        ]

        used = len(lines[0])
        for i, r in enumerate(results, 1):
            source_label = {
                "conversation": "💬 Conversation",
                "paper_trade": "📈 Paper Trade",
                "fraud_pattern": "⚠️ Fraud Pattern",
                "hybrid": "🔍 Hybrid",
            }.get(r.source, r.source)

            # Mostra scores
            score_info = f"original={r.original_score:.2f} → rerank={r.rerank_score:.2f}"

            entry = f"\n{i}. [{source_label}] ({score_info})\n   {r.text[:300]}"
            if used + len(entry) > max_chars:
                lines.append(f"\n... ({len(results) - i + 1} more results omitted)")
                break
            lines.append(entry)
            used += len(entry)

        return "".join(lines)


# Singleton
_rerank_pipeline: RerankPipeline | None = None


def reset_rerank_pipeline() -> None:
    """Reset singleton (for testing)."""
    global _rerank_pipeline
    _rerank_pipeline = None


def get_rerank_pipeline() -> RerankPipeline:
    """Get singleton RerankPipeline."""
    global _rerank_pipeline
    if _rerank_pipeline is None:
        _rerank_pipeline = RerankPipeline()
        logger.info("RerankPipeline initialized")
    return _rerank_pipeline
