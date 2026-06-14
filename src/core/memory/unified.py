"""Unified Memory Layer — Fase 1: Adapter Pattern.

Integra ConversationMemory e PaperJournal com ForensicRAG via
adapter pattern, permitindo retrieval unificado de todas as fontes.

Arquitetura:
    ConversationMemory ──add_document──> ForensicRAG
    PaperJournal ─────────add_document──> ForensicRAG
    UnifiedRetriever ──────────────┬────> search across all
                                      │
                                      └──> context fusion + user profile
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
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
        """Ingerir conversas no ForensicRAG."""
        self._memory._ensure_loaded()

        turns = (
            self._memory._cache.get(session_id, [])
            if session_id
            else self._memory._all_turns
        )

        ingested = 0
        for turn in turns:
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
        """Ingerir trades paper no ForensicRAG."""
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

        if trade.get("exit_date"):
            parts.append(
                f"Outcome: {trade.get('outcome', 'unknown')} "
                f"(PnL: ${trade.get('pnl_amount', 0):.2f})"
            )
            if trade.get("lesson_learned"):
                parts.append(f"Lesson: {trade.get('lesson_learned')[:200]}")

        return " | ".join(parts)

    def search(self, query: str, top_k: int = 5) -> list[RetrievalResult]:
        """Busca trades por similaridade de texto."""
        from core.memory.conversation_memory import _tokenize, _cosine_sim, _hashed_embedding

        trades = self._journal.list_all()
        query_emb = _hashed_embedding(query)

        scored = []
        for trade in trades:
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
    """Retriever unificado com perfil, busca e renderização de contexto.

    Conecta:
    - ConversationMemory
    - PaperJournal
    - ForensicRAG (optional)
    - User profile (8 chaves)
    """

    def __init__(self):
        self._conv_adapter = ConversationMemoryAdapter()
        self._journal_adapter = PaperJournalAdapter()
        self._forensic_rag = None
        self._rag_loaded = False
        # User profile (8 chaves)
        self._profile: dict[str, tuple[str, float]] = {}  # key -> (value, confidence)

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

    # === PROFILE METHODS ===

    def get_profile(self) -> dict[str, tuple[str, float]]:
        """Get current user profile.

        Returns:
            Dict mapping key -> (value, confidence)
        """
        return self._profile.copy()

    def upsert_profile(self, key: str, value: str, confidence: float = 0.5) -> None:
        """Update or insert profile key.

        Args:
            key: Profile key (risk_tolerance, capital_cad, etc.)
            value: Profile value
            confidence: Confidence score 0-1
        """
        existing_conf = self._profile.get(key, (None, 0.0))[1]
        if confidence > existing_conf:
            self._profile[key] = (value, confidence)
            logger.debug("Profile updated: %s = %s (conf=%.2f)", key, value, confidence)

    def extract_profile_from_message(
        self, message: str
    ) -> list[tuple[str, str, float]]:
        """Extract profile updates from user message.

        Returns:
            List of (key, value, confidence) tuples
        """
        updates: list[tuple[str, str, float]] = []
        msg_lower = message.lower()

        # 1. risk_tolerance
        if any(w in msg_lower for w in ["conservador", "conservativa", "seguro", "segura"]):
            updates.append(("risk_tolerance", "conservative", 0.8))
        elif any(w in msg_lower for w in ["adrenalina", "especulativo", "agressivo", "arriscado"]):
            updates.append(("risk_tolerance", "speculative", 0.8))
        elif any(w in msg_lower for w in ["moderado", "equilibrado", "balanceado"]):
            updates.append(("risk_tolerance", "moderate", 0.8))

        # 2. capital_cad - regex
        capital_match = re.search(r"(\d+)\s*(k|mil|cad)\s*(reais|r\$|c\$)?", msg_lower)
        if capital_match:
            amount = capital_match.group(1)
            updates.append(("capital_cad", f"{amount}k", 0.9))

        # 3. income_stability
        if any(w in msg_lower for w in ["freelance", "autônomo", "instável", "variável"]):
            updates.append(("income_stability", "unstable", 0.7))
        elif any(w in msg_lower for w in ["salário", "fixo", "estável", "clt"]):
            updates.append(("income_stability", "stable", 0.7))

        # 4. investment_goal
        if any(w in msg_lower for w in ["independência", "aposentar", "liberdade", "fire"]):
            updates.append(("investment_goal", "financial_independence", 0.8))
        elif any(w in msg_lower for w in ["aprender", "estudar", "conhecimento"]):
            updates.append(("investment_goal", "education", 0.7))

        # 5. time_horizon_years
        horizon_match = re.search(r"(\d+)\s*(anos?|years?)", msg_lower)
        if horizon_match:
            updates.append(("time_horizon_years", horizon_match.group(1), 0.8))

        # 6. has_emergency_fund
        if any(w in msg_lower for w in ["tenho reserva", "emergência já", "reserva já tenho"]):
            updates.append(("has_emergency_fund", "True", 0.9))
        elif any(w in msg_lower for w in ["não tenho", "sem reserva", "preciso fazer"]):
            updates.append(("has_emergency_fund", "False", 0.9))

        # 7. preferred_markets
        if any(w in msg_lower for w in ["tsx", "canada", "toronto"]):
            updates.append(("preferred_markets", "TSX", 0.7))
        elif any(w in msg_lower for w in ["nasdaq"]):
            updates.append(("preferred_markets", "NASDAQ", 0.7))

        # 8. avoid_sectors
        avoid_keywords = ["crypto", "cripto", "bitcoin", "otc", "maconha", "cannabis", "alavancado", "etf alavancado"]
        for keyword in avoid_keywords:
            if keyword in msg_lower:
                updates.append(("avoid_sectors", keyword, 0.6))
                break

        return updates

    # === CONTEXT RENDERING ===

    def render_memory_context(
        self,
        session_id: str,
        message: str = "",
        ticker: str = "",
    ) -> str:
        """Render memory context in EXACT format for Bob prompt.

        Format:
        === BOB'S MEMORY ===

        ## Perfil do Marco
        - Risco: {risk_tolerance}
        - Capital: CAD {capital}
        - Renda: {income_stability}
        - Meta: {investment_goal}
        - Reserva emergência: {has_emergency_fund}

        ## Conversas recentes (últimas 24h)
        - {timestamp}: "{user_message[:100]}" → {verdict}

        ## Teses abertas
        - {ticker}: "{thesis}" @ ${entry_price}, conv: {conviction}/100

        ## Tickers já analisados
        - {ticker} ({count}x) — último veredito: {verdict}

        === END MEMORY ===
        """
        lines = ["=== BOB'S MEMORY ===", ""]

        # ## Perfil do Marco
        lines.append("## Perfil do Marco")
        profile = self.get_profile()
        labels = {
            "risk_tolerance": "Risco",
            "capital_cad": "Capital",
            "income_stability": "Renda",
            "investment_goal": "Meta",
            "has_emergency_fund": "Reserva emergência",
        }
        for key, label in labels.items():
            if key in profile:
                value, _ = profile[key]
                lines.append(f"- {label}: {value}")
        if not any(key in profile for key in labels):
            lines.append("- (Perfil não definido ainda)")
        lines.append("")

        # ## Conversas recentes
        lines.append("## Conversas recentes (últimas 24h)")
        recent_turns = self._conv_adapter._memory.get_recent_context(session_id, hours=24, limit=5)
        if recent_turns:
            for turn in recent_turns[:3]:
                msg_preview = turn.user_message[:80].replace("\n", " ")
                lines.append(f"- {turn.timestamp[:10]}: \"{msg_preview}\" → {turn.verdict or 'Sem veredito'}")
        else:
            lines.append("- (Nenhuma conversa recente)")
        lines.append("")

        # ## Teses abertas
        lines.append("## Teses abertas")
        if recent_turns:
            theses = [t for t in recent_turns if t.thesis_formed and t.verdict in {"BUY", "SELL"}]
            if theses:
                for t in theses[:3]:
                    lines.append(f"- {t.ticker_discussed or 'N/A'}: \"{t.thesis_formed[:60]}...\" conv: {int(t.confidence)}/100")
            else:
                lines.append("- (Nenhuma tese aberta)")
        else:
            lines.append("- (Nenhuma tese aberta)")
        lines.append("")

        # ## Tickers já analisados
        lines.append("## Tickers já analisados")
        if recent_turns:
            ticker_counts = Counter(t.ticker_discussed for t in recent_turns if t.ticker_discussed)
            if ticker_counts:
                for ticker, count in ticker_counts.most_common(5):
                    latest = max((t for t in recent_turns if t.ticker_discussed == ticker), key=lambda x: x.timestamp, default=None)
                    verdict = latest.verdict if latest else "N/A"
                    lines.append(f"- {ticker} ({count}x) — último veredito: {verdict}")
            else:
                lines.append("- (Nenhum ticker analisado)")
        else:
            lines.append("- (Nenhum ticker analisado)")
        lines.append("")

        lines.append("=== END MEMORY ===")
        return "\n".join(lines)

    # === SEARCH METHODS ===

    def ingest_all_to_rag(self, session_id: str | None = None) -> dict[str, int]:
        """Ingerir todas as fontes no ForensicRAG."""
        self._ensure_rag()
        if not self._forensic_rag:
            return {"error": "ForensicRAG not available"}

        counts = {"conversation": 0, "paper_trades": 0, "total": 0}

        try:
            counts["conversation"] = self._conv_adapter.ingest_to_rag(
                self._forensic_rag, session_id=session_id
            )
        except Exception as e:
            logger.warning("Failed to ingest conversations: %s", e)

        try:
            counts["paper_trades"] = self._journal_adapter.ingest_to_rag(self._forensic_rag)
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
        """Busca unificada em todas as fontes."""
        if sources is None:
            sources = ["conversation", "paper_trade", "fraud_pattern"]

        all_results = []

        if "conversation" in sources:
            try:
                all_results.extend(self._conv_adapter.search(query, top_k=top_k))
            except Exception as e:
                logger.warning("Conversation search failed: %s", e)

        if "paper_trade" in sources:
            try:
                all_results.extend(self._journal_adapter.search(query, top_k=top_k))
            except Exception as e:
                logger.warning("Paper trade search failed: %s", e)

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
