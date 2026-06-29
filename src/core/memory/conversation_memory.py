"""Conversation Memory — Memória persistente do Bob.

Armazena conversas por session_id em JSONL append-only.
Permite que o Bob lembre de contextos anteriores, teses formuladas,
e decisões tomadas em sessões passadas.

Design:
- Append-only JSONL (seguindo padrão PaperJournal)
- Embeddings locais via hashed tokens (sem dependência de modelo)
- Recuperação por similaridade para contexto relevante
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from hashlib import blake2b
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_MEMORY_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent / "data" / "conversation_memory.jsonl"
)
_EMBEDDING_DIMS = 128

# Singleton cache para memoria global
_memory_instance: ConversationMemory | None = None


@dataclass
class ConversationTurn:
    """Um turno de conversação Bob-Usuário."""

    session_id: str
    timestamp: str  # ISO 8601
    user_message: str
    bob_response: str
    context_summary: str = ""  # Resumo do contexto nesta conversa
    embedding_vector: list[float] | None = None  # Vetor de similaridade

    # Metadados de decisão (quando aplicável)
    ticker_discussed: str = ""
    thesis_formed: str = ""
    verdict: str = ""  # "BUY_CANDIDATE" | "WAIT" | "REJECT_ALL" | "STUDY_MORE"
    confidence: float = 0.0

    # Tags para recuperação
    tags: list[str] = field(default_factory=list)
    category: str = "general"  # "market_scan" | "ticker_analysis" | "portfolio" | "general"

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items()}

    def to_embedding_text(self) -> str:
        """Texto para gerar embedding e busca."""
        parts = [self.user_message, self.bob_response]
        if self.thesis_formed:
            parts.append(f"thesis: {self.thesis_formed}")
        if self.ticker_discussed:
            parts.append(f"ticker: {self.ticker_discussed}")
        return " ".join(parts)


def _tokenize(text: str) -> set[str]:
    """Tokenização simples para embeddings locais."""
    import re

    text = text.lower()
    tokens = {text} if text and len(text) <= 80 else set()
    tokens.update(t for t in re.split(r"[^a-z0-9_]+", text) if len(t) >= 2)
    return tokens


def _hashed_embedding(text: str, dims: int = _EMBEDDING_DIMS) -> list[float]:
    """Embedding local via hash — sem dependência de modelo."""
    vector = [0.0] * dims
    for token in _tokenize(text):
        digest = blake2b(token.encode("utf-8"), digest_size=8).digest()
        bucket = int.from_bytes(digest[:4], "big") % dims
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[bucket] += sign

    norm = math.sqrt(sum(v * v for v in vector))
    if norm == 0:
        return vector
    return [v / norm for v in vector]


def _cosine_sim(a: list[float], b: list[float]) -> float:
    """Similaridade cosseno entre dois vetores."""
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(ai * bi for ai, bi in zip(a, b))


class ConversationMemory:
    """Memória conversacional persistente do Bob."""

    def __init__(self, path: Path | None = None):
        self._path = path or DEFAULT_MEMORY_PATH
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, list[ConversationTurn]] = {}  # session_id -> turns
        self._all_turns: list[ConversationTurn] = []

    @property
    def path(self) -> Path:
        return self._path

    def _load_all(self) -> list[ConversationTurn]:
        """Carrega todos os turnos do disco."""
        if not self._path.exists():
            return []

        turns = []
        with open(self._path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        data = json.loads(line)
                        turn = ConversationTurn(**data)
                        # Regenera embedding se não existir
                        if turn.embedding_vector is None:
                            turn.embedding_vector = _hashed_embedding(turn.to_embedding_text())
                        turns.append(turn)
                    except (json.JSONDecodeError, TypeError) as e:
                        logger.warning("Skipping corrupt memory line: %s", e)
        return turns

    def _ensure_loaded(self) -> None:
        """Carrega memória do disco se não estiver em cache."""
        if not self._all_turns:
            self._all_turns = self._load_all()
            # Indexa por session_id
            for turn in self._all_turns:
                self._cache.setdefault(turn.session_id, []).append(turn)

    def _append(self, turn: ConversationTurn) -> None:
        """Adiciona turno ao disco."""
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(turn.to_dict(), ensure_ascii=False) + "\n")

    def add_turn(
        self,
        session_id: str,
        user_message: str,
        bob_response: str,
        context_summary: str = "",
        ticker_discussed: str = "",
        thesis_formed: str = "",
        verdict: str = "",
        confidence: float = 0.0,
        tags: list[str] | None = None,
        category: str = "general",
    ) -> ConversationTurn:
        """Registra um novo turno de conversação."""
        self._ensure_loaded()

        turn = ConversationTurn(
            session_id=session_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            user_message=user_message,
            bob_response=bob_response,
            context_summary=context_summary,
            embedding_vector=None,  # Gerado abaixo
            ticker_discussed=ticker_discussed,
            thesis_formed=thesis_formed,
            verdict=verdict,
            confidence=confidence,
            tags=tags or [],
            category=category,
        )

        # Gera embedding
        turn.embedding_vector = _hashed_embedding(turn.to_embedding_text())

        # Salva no disco e cache
        self._append(turn)
        self._all_turns.append(turn)
        self._cache.setdefault(session_id, []).append(turn)

        logger.debug(
            "Memory: added turn to session %s (total turns: %d)",
            session_id,
            len(self._cache.get(session_id, [])),
        )
        return turn

    def get_session_history(self, session_id: str, limit: int = 50) -> list[ConversationTurn]:
        """Recupera histórico de uma sessão específica."""
        self._ensure_loaded()
        return self._cache.get(session_id, [])[-limit:]

    def get_recent_context(
        self, session_id: str, hours: int = 24, limit: int = 20
    ) -> list[ConversationTurn]:
        """Recupera contexto recente da sessão (últimas N horas)."""
        self._ensure_loaded()

        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        recent = []

        for turn in self._cache.get(session_id, []):
            try:
                turn_dt = datetime.fromisoformat(turn.timestamp.replace("Z", "+00:00"))
                if turn_dt >= cutoff:
                    recent.append(turn)
            except ValueError:
                continue

        return recent[-limit:]

    def search_similar(
        self, query: str, session_id: str | None = None, top_k: int = 5
    ) -> list[tuple[ConversationTurn, float]]:
        """Busca turnos similares por embedding."""
        self._ensure_loaded()

        query_emb = _hashed_embedding(query)

        # Filtra por session_id se especificado
        candidates = self._cache.get(session_id, []) if session_id else self._all_turns

        scored = []
        for turn in candidates:
            if turn.embedding_vector:
                sim = _cosine_sim(query_emb, turn.embedding_vector)
                scored.append((turn, sim))

        # Ordena por similaridade
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    def get_ticker_history(
        self, ticker: str, session_id: str | None = None, limit: int = 10
    ) -> list[ConversationTurn]:
        """Recupera conversas sobre um ticker específico."""
        self._ensure_loaded()

        ticker = ticker.upper()
        candidates = self._cache.get(session_id, []) if session_id else self._all_turns

        filtered = [t for t in candidates if t.ticker_discussed.upper() == ticker]
        # Ordena por timestamp (mais recente primeiro)
        filtered.sort(
            key=lambda t: datetime.fromisoformat(t.timestamp.replace("Z", "+00:00")),
            reverse=True,
        )
        return filtered[:limit]

    def get_theses(self, session_id: str | None = None, days: int = 30) -> list[ConversationTurn]:
        """Recupera teses formuladas recentemente."""
        self._ensure_loaded()

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        candidates = self._cache.get(session_id, []) if session_id else self._all_turns

        theses = []
        for turn in candidates:
            if turn.thesis_formed:
                try:
                    turn_dt = datetime.fromisoformat(turn.timestamp.replace("Z", "+00:00"))
                    if turn_dt >= cutoff:
                        theses.append(turn)
                except ValueError:
                    continue

        theses.sort(
            key=lambda t: datetime.fromisoformat(t.timestamp.replace("Z", "+00:00")),
            reverse=True,
        )
        return theses

    def summarize_session(self, session_id: str) -> dict[str, Any]:
        """Sumariza estatísticas de uma sessão."""
        self._ensure_loaded()

        turns = self._cache.get(session_id, [])
        if not turns:
            return {
                "session_id": session_id,
                "total_turns": 0,
                "tickers_discussed": [],
                "categories": {},
            }

        tickers = {t.ticker_discussed for t in turns if t.ticker_discussed}
        categories = {}
        for t in turns:
            categories[t.category] = categories.get(t.category, 0) + 1

        return {
            "session_id": session_id,
            "total_turns": len(turns),
            "first_turn": turns[0].timestamp,
            "last_turn": turns[-1].timestamp,
            "tickers_discussed": sorted(tickers),
            "categories": categories,
        }

    def get_stats(self) -> dict[str, Any]:
        """Estatísticas globais da memória."""
        self._ensure_loaded()

        total_turns = len(self._all_turns)
        total_sessions = len(self._cache)

        # Conta categorias
        categories: dict[str, int] = {}
        for turn in self._all_turns:
            categories[turn.category] = categories.get(turn.category, 0) + 1

        # Tickers mais discutidos
        ticker_counts: dict[str, int] = {}
        for turn in self._all_turns:
            if turn.ticker_discussed:
                ticker_counts[turn.ticker_discussed] = (
                    ticker_counts.get(turn.ticker_discussed, 0) + 1
                )

        top_tickers = sorted(ticker_counts.items(), key=lambda x: x[1], reverse=True)[:10]

        return {
            "total_turns": total_turns,
            "total_sessions": total_sessions,
            "categories": categories,
            "top_tickers": [{"ticker": t, "count": c} for t, c in top_tickers],
            "path": str(self._path),
        }


def get_conversation_memory() -> ConversationMemory:
    """Retorna singleton de ConversationMemory."""
    global _memory_instance
    if _memory_instance is None:
        _memory_instance = ConversationMemory()
        _memory_instance._ensure_loaded()
        logger.info("ConversationMemory loaded from %s", _memory_instance.path)
    return _memory_instance


def reset_memory_for_test(test_path: Path) -> ConversationMemory:
    """Cria nova instância para testes."""
    return ConversationMemory(path=test_path)
