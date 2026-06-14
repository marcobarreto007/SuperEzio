"""Unified Memory Layer — Fase 1: Adapter Pattern.

Integra ConversationMemory e PaperJournal com ForensicRAG via
adapter pattern, permitindo retrieval unificado de todas as fontes.

Arquitetura:
    ConversationMemory ──add_document──> ForensicRAG
    PaperJournal ─────────add_document──> ForensicRAG
    UnifiedRetriever ──────────────┬────> search across all
                                      │
                                      └──> context fusion
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class RetrievalResult:
    """Resultado unificado de qualquer fonte de memória."""

    id: str
    text: str
    source: str  # "conversation" | "paper_trade" | "fraud_pattern"
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)

    # Campos específicos por fonte
    timestamp: str = ""
    ticker: str = ""
    verdict: str = ""
    category: str = ""

    def to_rag_format(self) -> dict[str, Any]:
        """Converte para formato esperado pelo ForensicRAG."""
        return {
            "id": self.id,
            "text": self.text,
            "source": self.source,
            "score": self.score,
        }


class ConversationMemoryAdapter:
    """Adapter para integrar ConversationMemory com ForensicRAG."""

    def __init__(self, memory_path: Path | None = None):
        from core.memory import ConversationMemory

        self._memory = ConversationMemory(memory_path)

    def ingest_to_rag(self, rag_instance, session_id: str | None = None) -> int:
        """Ingerir conversas no ForensicRAG.

        Args:
            rag_instance: Instância de ForensicRAG
            session_id: Se especificado, ingere apenas desta sessão

        Returns:
            Número de documentos ingeridos
        """
        self._memory._ensure_loaded()

        turns = (
            self._memory._cache.get(session_id, [])
            if session_id
            else self._memory._all_turns
        )

        ingested = 0
        for turn in turns:
            # Formata como documento RAG
            doc_text = self._format_turn_as_doc(turn)
            doc_id = f"conv_{turn.session_id}_{turn.timestamp}"

            try:
                rag_instance.add_document(
                    doc_id=doc_id,
                    text=doc_text,
                    source="conversation_memory",
                )
                ingested += 1
            except Exception as e:
                logger.warning("Failed to ingest turn %s: %s", doc_id, e)

        logger.info(
            "ConversationMemory: ingested %d turns to RAG (session=%s)",
            ingested,
            session_id or "all",
        )
        return ingested

    def _format_turn_as_doc(self, turn) -> str:
        """Formata um ConversationTurn como documento RAG."""
        parts = [
            f"[CONVERSATION] Session: {turn.session_id}",
            f"User: {turn.user_message[:200]}",
            f"Bob: {turn.bob_response[:300]}",
        ]
        if turn.ticker_discussed:
            parts.append(f"Ticker: {turn.ticker_discussed}")
        if turn.thesis_formed:
            parts.append(f"Thesis: {turn.thesis_formed}")
        if turn.verdict:
            parts.append(f"Verdict: {turn.verdict} (confidence: {turn.confidence:.0f})")
        parts.append(f"Category: {turn.category}")
        return " | ".join(parts)

    def search(self, query: str, top_k: int = 5) -> list[RetrievalResult]:
        """Busca direta na memória conversacional."""
        results = self._memory.search_similar(query, top_k=top_k)

        retrieval_results = []
        for turn, score in results:
            retrieval_results.append(
                RetrievalResult(
                    id=f"conv_{turn.session_id}_{turn.timestamp}",
                    text=turn.to_embedding_text()[:500],
                    source="conversation",
                    score=float(score),
                    metadata={
                        "session_id": turn.session_id,
                        "timestamp": turn.timestamp,
                    },
                    timestamp=turn.timestamp,
                    ticker=turn.ticker_discussed,
                    verdict=turn.verdict,
                    category=turn.category,
                )
            )
        return retrieval_results


class PaperJournalAdapter:
    """Adapter para integrar PaperJournal com ForensicRAG."""

    def __init__(self, journal_path: Path | None = None):
        from core.trading.paper_journal import PaperJournal

        self._journal = PaperJournal(journal_path)

    def ingest_to_rag(self, rag_instance) -> int:
        """Ingerir trades paper no ForensicRAG.

        Returns:
            Número de documentos ingeridos
        """
        trades = self._journal.list_all()
        ingested = 0

        for trade in trades:
            doc_text = self._format_trade_as_doc(trade)
            doc_id = f"trade_{trade.get('trade_id', 'unknown')}"

            try:
                rag_instance.add_document(
                    doc_id=doc_id,
                    text=doc_text,
                    source="paper_journal",
                )
                ingested += 1
            except Exception as e:
                logger.warning("Failed to ingest trade %s: %s", doc_id, e)

        logger.info("PaperJournal: ingested %d trades to RAG", ingested)
        return ingested

    def _format_trade_as_doc(self, trade: dict) -> str:
        """Formata um PaperTrade como documento RAG."""
        parts = [
            f"[PAPER_TRADE] {trade.get('ticker', 'UNKNOWN')}",
            f"Direction: {trade.get('direction', 'unknown')}",
            f"Entry: ${trade.get('entry_price', 0):.2f}",
            f"Thesis: {trade.get('thesis', 'No thesis')[:200]}",
        ]

        # Adiciona resultado se fechado
        if trade.get("exit_date"):
            parts.append(
                f"Outcome: {trade.get('outcome', 'unknown')} "
                f"(PnL: ${trade.get('pnl_amount', 0):.2f})"
            )
            if trade.get("lesson_learned"):
                parts.append(f"Lesson: {trade.get('lesson_learned')[:200]}")

        return " | ".join(parts)

    def search(self, query: str, top_k: int = 5) -> list[RetrievalResult]:
        """Busca trades por similaridade de texto (simples por enquanto)."""
        from core.memory.conversation_memory import _tokenize, _cosine_sim, _hashed_embedding

        trades = self._journal.list_all()
        query_emb = _hashed_embedding(query)

        scored = []
        for trade in trades:
            # Texto para embedding
            trade_text = self._format_trade_as_doc(trade)
            trade_emb = _hashed_embedding(trade_text)
            score = _cosine_sim(query_emb, trade_emb)

            if score > 0.1:
                scored.append((trade, score))

        scored.sort(key=lambda x: x[1], reverse=True)

        retrieval_results = []
        for trade, score in scored[:top_k]:
            retrieval_results.append(
                RetrievalResult(
                    id=f"trade_{trade.get('trade_id', 'unknown')}",
                    text=self._format_trade_as_doc(trade)[:500],
                    source="paper_trade",
                    score=float(score),
                    metadata={
                        "trade_id": trade.get("trade_id"),
                        "entry_date": trade.get("entry_date"),
                        "exit_date": trade.get("exit_date"),
                    },
                    ticker=trade.get("ticker", ""),
                    verdict=trade.get("outcome", ""),
                )
            )
        return retrieval_results


class UnifiedRetriever:
    """Retriever unificado que consulta todas as fontes de memória."""

    def __init__(self):
        self._conv_adapter = ConversationMemoryAdapter()
        self._journal_adapter = PaperJournalAdapter()
        self._forensic_rag = None
        self._rag_loaded = False

    def _ensure_rag(self) -> None:
        """Carrega ForensicRAG lazy."""
        if self._rag_loaded:
            return
        try:
            from core.rag.engine import forensic_rag

            self._forensic_rag = forensic_rag
            self._rag_loaded = True
        except ImportError:
            logger.warning("ForensicRAG not available")
            self._rag_loaded = True

    def ingest_all_to_rag(self, session_id: str | None = None) -> dict[str, int]:
        """Ingerir todas as fontes no ForensicRAG.

        Args:
            session_id: Se especificado, ingere apenas esta sessão da memória conversacional

        Returns:
            Dict com contagem por fonte
        """
        self._ensure_rag()
        if not self._forensic_rag:
            return {"error": "ForensicRAG not available"}

        counts = {
            "conversation": 0,
            "paper_trades": 0,
            "total": 0,
        }

        # Ingerir conversas
        try:
            counts["conversation"] = self._conv_adapter.ingest_to_rag(
                self._forensic_rag, session_id=session_id
            )
        except Exception as e:
            logger.warning("Failed to ingest conversations: %s", e)

        # Ingerir trades
        try:
            counts["paper_trades"] = self._journal_adapter.ingest_to_rag(
                self._forensic_rag
            )
        except Exception as e:
            logger.warning("Failed to ingest paper trades: %s", e)

        counts["total"] = counts["conversation"] + counts["paper_trades"]
        return counts

    def search(
        self,
        query: str,
        top_k: int = 5,
        sources: list[str] | None = None,
    ) -> list[RetrievalResult]:
        """Busca unificada em todas as fontes.

        Args:
            query: Query de busca
            top_k: Número de resultados por fonte
            sources: Lista de fontes ("conversation", "paper_trade", "fraud_pattern").
                     None busca em todas.

        Returns:
            Lista de RetrievalResult, ordenada por score
        """
        if sources is None:
            sources = ["conversation", "paper_trade", "fraud_pattern"]

        all_results = []

        # Conversa
        if "conversation" in sources:
            try:
                all_results.extend(self._conv_adapter.search(query, top_k=top_k))
            except Exception as e:
                logger.warning("Conversation search failed: %s", e)

        # Paper trades
        if "paper_trade" in sources:
            try:
                all_results.extend(self._journal_adapter.search(query, top_k=top_k))
            except Exception as e:
                logger.warning("Paper trade search failed: %s", e)

        # Fraud patterns (via ForensicRAG)
        if "fraud_pattern" in sources:
            self._ensure_rag()
            if self._forensic_rag:
                try:
                    rag_results = self._forensic_rag.search(query, top_k=top_k)
                    for r in rag_results:
                        all_results.append(
                            RetrievalResult(
                                id=r["id"],
                                text=r["text"][:500],
                                source="fraud_pattern",
                                score=float(r["score"]),
                            )
                        )
                except Exception as e:
                    logger.warning("ForensicRAG search failed: %s", e)

        # Ordenar por score global
        all_results.sort(key=lambda r: r.score, reverse=True)
        return all_results[:top_k]

    def format_context(
        self, results: list[RetrievalResult], max_chars: int = 2000
    ) -> str:
        """Formata resultados como contexto para o Bob."""
        if not results:
            return "[UNIFIED_MEMORY] No relevant memories found."

        lines = [
            "[UNIFIED_MEMORY] — Relevant context from conversations, "
            "paper trades, and fraud patterns:"
        ]

        used = len(lines[0])
        for i, r in enumerate(results, 1):
            source_label = {
                "conversation": "💬 Conversation",
                "paper_trade": "📈 Paper Trade",
                "fraud_pattern": "⚠️ Fraud Pattern",
            }.get(r.source, r.source)

            metadata = []
            if r.ticker:
                metadata.append(f"ticker={r.ticker}")
            if r.verdict:
                metadata.append(f"verdict={r.verdict}")
            if r.timestamp:
                metadata.append(f"when={r.timestamp[:10]}")

            meta_str = f" ({', '.join(metadata)})" if metadata else ""

            entry = f"\n{i}. [{source_label}]{meta_str} (score={r.score:.2f})\n   {r.text[:300]}"
            if used + len(entry) > max_chars:
                lines.append(f"\n... ({len(results) - i + 1} more results omitted)")
                break
            lines.append(entry)
            used += len(entry)

        return "".join(lines)


# Singleton para uso no pipeline
_unified_retriever: UnifiedRetriever | None = None


def get_unified_retriever() -> UnifiedRetriever:
    """Retorna singleton de UnifiedRetriever."""
    global _unified_retriever
    if _unified_retriever is None:
        _unified_retriever = UnifiedRetriever()
        logger.info("UnifiedRetriever initialized")
    return _unified_retriever
