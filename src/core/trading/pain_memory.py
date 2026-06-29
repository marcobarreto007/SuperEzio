"""Pain Memory - Sistema de memória com pesos de dor.

Bob "lembra" com mais intensidade perdas grandes (traumas) e usa isso
para evitar setups similares no futuro.

Características:
- Pesos baseados em dor (1x a 5x)
- Traumas (> $500 perda) ficam marcados
- Decay: dores antigas pesam menos
- Recall: busca dores similares ao setup atual
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_PAIN_MEMORY_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent / "data" / "pain_memory.jsonl"
)


class PainSeverity(Enum):
    """Níveis de dor."""

    MILD = (1, "Mild", 100)
    MODERATE = (2, "Moderate", 500)
    SEVERE = (3, "Severe", 1000)
    TRAUMATIC = (5, "Traumatic", 0)  # Sem limite

    @property
    def weight(self) -> int:
        return self.value[0]

    @property
    def label(self) -> str:
        return self.value[1]

    @property
    def threshold_usd(self) -> int:
        return self.value[2]

    @classmethod
    def from_loss(cls, loss_amount: float) -> "PainSeverity":
        """Classifica dor baseado no valor da perda."""
        abs_loss = abs(loss_amount)

        if abs_loss < 100:
            return PainSeverity.MILD
        elif abs_loss < 500:
            return PainSeverity.MODERATE
        elif abs_loss < 1000:
            return PainSeverity.SEVERE
        else:
            return PainSeverity.TRAUMATIC


@dataclass
class PainMemory:
    """Uma memória de dor (perda registrada)."""

    memory_id: str
    timestamp: str
    ticker: str
    loss_amount: float
    severity: PainSeverity
    weight: float  # Peso atual (com decay aplicado)
    original_weight: float  # Peso original (sem decay)
    thesis: str
    what_went_wrong: str | None = None
    trade_id: str | None = None
    tags: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)  # Para matching similar
    recall_count: int = 0  # Quantas vezes foi acessada
    last_recalled: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "memory_id": self.memory_id,
            "timestamp": self.timestamp,
            "ticker": self.ticker,
            "loss_amount": self.loss_amount,
            "severity": self.severity.name,
            "weight": round(self.weight, 3),
            "original_weight": round(self.original_weight, 3),
            "thesis": self.thesis,
            "what_went_wrong": self.what_went_wrong,
            "trade_id": self.trade_id,
            "tags": self.tags,
            "keywords": self.keywords,
            "recall_count": self.recall_count,
            "last_recalled": self.last_recalled,
        }

    def calculate_decay(self, days_old: int, decay_rate: float = 0.05) -> float:
        """Calcula peso com decay aplicado.

        Args:
            days_old: Dias desde a memória
            decay_rate: Taxa de decaimento por mês (padrão 5% ao mês)

        Returns:
            Peso após decay
        """
        # Decay é aplicado mensalmente
        months_old = days_old / 30.0
        decay_factor = (1 - decay_rate) ** months_old
        return self.original_weight * decay_factor

    def boost(self, factor: float = 1.5) -> None:
        """Aumenta peso temporariamente (recall recente)."""
        self.weight = min(5.0, self.weight * factor)
        self.recall_count += 1
        self.last_recalled = datetime.now(timezone.utc).isoformat()


class PainMemorySystem:
    """Sistema de memória de dor do Bob."""

    def __init__(
        self,
        path: Path | None = None,
        decay_rate: float = 0.05,  # 5% ao mês
        similar_threshold: float = 0.3,  # Similaridade para recall
    ):
        self._path = path or DEFAULT_PAIN_MEMORY_PATH
        self._path.parent.mkdir(parents=True, exist_ok=True)

        self._decay_rate = decay_rate
        self._similar_threshold = similar_threshold

        self._memories: list[PainMemory] = []
        self._load()

    def _load(self) -> None:
        """Carrega memórias do disco."""
        if not self._path.exists():
            return

        with open(self._path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    severity = PainSeverity[data["severity"]]
                    memory = PainMemory(
                        memory_id=data["memory_id"],
                        timestamp=data["timestamp"],
                        ticker=data["ticker"],
                        loss_amount=data["loss_amount"],
                        severity=severity,
                        weight=data["weight"],
                        original_weight=data["original_weight"],
                        thesis=data["thesis"],
                        what_went_wrong=data.get("what_went_wrong"),
                        trade_id=data.get("trade_id"),
                        tags=data.get("tags", []),
                        keywords=data.get("keywords", []),
                        recall_count=data.get("recall_count", 0),
                        last_recalled=data.get("last_recalled"),
                    )
                    self._memories.append(memory)
                except (json.JSONDecodeError, TypeError, KeyError) as e:
                    logger.warning("Skipping corrupt pain memory: %s", e)

    def _save(self, memory: PainMemory) -> None:
        """Salva memória no disco (append-only)."""
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(memory.to_dict(), ensure_ascii=False) + "\n")

    def _generate_memory_id(self) -> str:
        """Gera ID único para memória."""
        return f"pain_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{len(self._memories)}"

    def _extract_keywords(self, text: str) -> list[str]:
        """Extrai palavras-chave para matching similar."""
        if not text:
            return []

        # Palavras comuns de trading
        trading_keywords = {
            "breakout",
            "momentum",
            "dip",
            "earnings",
            "news",
            "trend",
            "reversal",
            "volume",
            "spike",
            "gap",
            "resistance",
            "support",
            "catalyst",
            "macro",
            "sector",
            "technical",
            "fundamental",
            "short",
            "squeeze",
            "bull",
            "bear",
        }

        text_lower = text.lower()
        words = set(text_lower.split())

        keywords = []
        for word in words:
            if word in trading_keywords or len(word) > 5:
                keywords.append(word)

        return list(set(keywords))

    def _calculate_similarity(self, setup: dict[str, Any], memory: PainMemory) -> float:
        """Calcula similaridade entre setup e memória.

        Args:
            setup: Setup atual (ticker, thesis, direction, etc.)
            memory: Memória de dor

        Returns:
            Similaridade 0-1
        """
        score = 0.0

        # Ticker match
        if setup.get("ticker", "").upper() == memory.ticker.upper():
            score += 0.4

        # Direction match
        if setup.get("direction", "") == setup.get("direction", ""):
            score += 0.1

        # Keyword overlap
        setup_keywords = set(self._extract_keywords(setup.get("thesis", "")))
        memory_keywords = set(memory.keywords)

        if setup_keywords and memory_keywords:
            overlap = len(setup_keywords & memory_keywords)
            union = len(setup_keywords | memory_keywords)
            if union > 0:
                score += 0.5 * (overlap / union)

        # Severity weight (higher severity = higher similarity score)
        score += 0.1 * (memory.severity.weight / 5.0)

        return min(1.0, score)

    def remember_pain(
        self,
        ticker: str,
        loss_amount: float,
        thesis: str,
        what_went_wrong: str | None = None,
        trade_id: str | None = None,
        tags: list[str] | None = None,
    ) -> PainMemory:
        """Registra uma dor (perda) na memória.

        Args:
            ticker: Ticker da posição
            loss_amount: Valor da perda (negativo)
            thesis: Tese original
            what_went_wrong: O que deu errado
            trade_id: ID do trade
            tags: Tags adicionais

        Returns:
            Memória criada
        """
        severity = PainSeverity.from_loss(loss_amount)
        weight = float(severity.weight)

        # Traumas tem peso extra
        if severity == PainSeverity.TRAUMATIC:
            weight *= 1.5

        keywords = self._extract_keywords(thesis + " " + (what_went_wrong or ""))

        memory = PainMemory(
            memory_id=self._generate_memory_id(),
            timestamp=datetime.now(timezone.utc).isoformat(),
            ticker=ticker.upper(),
            loss_amount=abs(loss_amount),
            severity=severity,
            weight=weight,
            original_weight=weight,
            thesis=thesis,
            what_went_wrong=what_went_wrong,
            trade_id=trade_id,
            tags=tags or [],
            keywords=keywords,
        )

        self._memories.append(memory)
        self._save(memory)

        logger.info(
            "Pain remembered: %s $%.2f (%s, weight=%.2f)",
            ticker,
            abs(loss_amount),
            severity.label,
            weight,
        )
        return memory

    def recall_similar_pains(
        self,
        setup: dict[str, Any],
        limit: int = 5,
        min_severity: PainSeverity | None = None,
    ) -> list[PainMemory]:
        """Recall dores similares ao setup atual.

        Args:
            setup: Setup atual (ticker, thesis, direction)
            limit: Máximo de memórias a retornar
            min_severity: Severidade mínima para considerar

        Returns:
            Lista de memórias similares ordenadas por similaridade
        """
        now = datetime.now(timezone.utc)

        # Calcular similaridades e aplicar decay
        scored_memories = []
        for memory in self._memories:
            # Filtrar por severidade mínima
            if min_severity and memory.severity.weight < min_severity.weight:
                continue

            # Calcular idade e aplicar decay
            try:
                memory_dt = datetime.fromisoformat(memory.timestamp.replace("Z", "+00:00"))
                if memory_dt.tzinfo is None:
                    memory_dt = memory_dt.replace(tzinfo=timezone.utc)
                days_old = (now - memory_dt).days
            except Exception:
                days_old = 0

            memory.weight = memory.calculate_decay(days_old, self._decay_rate)

            # Calcular similaridade
            similarity = self._calculate_similarity(setup, memory)

            if similarity >= self._similar_threshold:
                scored_memories.append((similarity, memory))

        # Ordenar por similaridade
        scored_memories.sort(key=lambda x: x[0], reverse=True)

        # Boost nas memórias recallidas
        result = []
        for similarity, memory in scored_memories[:limit]:
            memory.boost()
            result.append(memory)

        return result

    def get_traumas(self, limit: int = 10) -> list[PainMemory]:
        """Retorna traumas (dores severas)."""
        traumas = [m for m in self._memories if m.severity == PainSeverity.TRAUMATIC]
        return list(reversed(traumas[-limit:]))

    def get_active_pains(self, days: int = 30, min_weight: float = 1.0) -> list[PainMemory]:
        """Retorna dores recentes com peso significativo.

        Args:
            days: Últimos N dias
            min_weight: Peso mínimo

        Returns:
            Lista de memórias ativas
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        active = []

        for memory in self._memories:
            try:
                memory_dt = datetime.fromisoformat(memory.timestamp.replace("Z", "+00:00"))
                if memory_dt.tzinfo is None:
                    memory_dt = memory_dt.replace(tzinfo=timezone.utc)
                if memory_dt < cutoff:
                    continue
            except Exception:
                continue

            if memory.weight >= min_weight:
                active.append(memory)

        return sorted(active, key=lambda m: m.weight, reverse=True)

    def get_stats(self) -> dict[str, Any]:
        """Retorna estatísticas da memória de dor."""
        if not self._memories:
            return {
                "total_memories": 0,
                "traumas": 0,
                "avg_weight": 0,
                "total_loss": 0,
            }

        total_loss = sum(m.loss_amount for m in self._memories)
        avg_weight = sum(m.weight for m in self._memories) / len(self._memories)
        traumas = sum(1 for m in self._memories if m.severity == PainSeverity.TRAUMATIC)

        # Top tickers com mais dor
        ticker_pain = {}
        for m in self._memories:
            ticker_pain[m.ticker] = ticker_pain.get(m.ticker, 0) + m.loss_amount

        top_tickers = sorted(ticker_pain.items(), key=lambda x: x[1], reverse=True)[:5]

        return {
            "total_memories": len(self._memories),
            "traumas": traumas,
            "avg_weight": round(avg_weight, 3),
            "total_loss": round(total_loss, 2),
            "top_painful_tickers": [(t, round(l, 2)) for t, l in top_tickers],
            "decay_rate": self._decay_rate,
        }

    def check_setup_risk(
        self,
        setup: dict[str, Any],
        max_pain_weight: float = 2.0,
    ) -> dict[str, Any]:
        """Verifica se setup tem risco baseado em dores passadas.

        Args:
            setup: Setup atual (ticker, thesis, direction)
            max_pain_weight: Peso máximo de dor aceitável

        Returns:
            Dict com:
            - safe: bool
            - risk_level: "low" | "medium" | "high"
            - similar_pains: lista de dores similares
            - recommendation: str
        """
        similar = self.recall_similar_pains(setup, limit=10)

        if not similar:
            return {
                "safe": True,
                "risk_level": "low",
                "similar_pains": [],
                "recommendation": "No similar painful memories found.",
            }

        # Calcular risco total
        total_pain_weight = sum(m.weight for m in similar)
        max_severity = max(m.severity.weight for m in similar)

        # Risco level
        if total_pain_weight < 2.0 and max_severity < 3:
            risk_level = "low"
            safe = True
            recommendation = "Setup has mild historical pain. Proceed with normal caution."
        elif total_pain_weight < 5.0 and max_severity < 4:
            risk_level = "medium"
            safe = True
            recommendation = (
                f"Setup has {len(similar)} similar painful memories. "
                "Increase stop-loss distance or reduce size."
            )
        else:
            risk_level = "high"
            safe = total_pain_weight < max_pain_weight
            recommendation = (
                f"WARNING: {len(similar)} similar painful memories with high severity. "
                "Consider skipping this setup or reducing position significantly."
            )

        return {
            "safe": safe,
            "risk_level": risk_level,
            "similar_pains": [m.to_dict() for m in similar[:3]],
            "total_pain_weight": round(total_pain_weight, 2),
            "recommendation": recommendation,
        }

    def render_for_bob(self, max_chars: int = 1000) -> str:
        """Renderiza memórias de dor para o prompt do Bob."""
        traumas = self.get_traumas(limit=3)
        active = self.get_active_pains(days=7, min_weight=2.0)

        if not traumas and not active:
            return ""

        lines = ["\n=== MEMÓRIAS DE DOR - EVITAR REPETIR ===\n"]

        if traumas:
            lines.append("⚠️ TRAUMAS (perdas >$500):")
            for trauma in traumas:
                lines.append(
                    f"- {trauma.ticker}: -${trauma.loss_amount:.2f} ({trauma.severity.label})"
                )
                if trauma.what_went_wrong:
                    lines.append(f"  O que deu errado: {trauma.what_went_wrong[:80]}...")
            lines.append("")

        if active:
            lines.append("Dores recentes (últimos 7 dias):")
            for pain in active[:5]:
                lines.append(f"- {pain.ticker}: -${pain.loss_amount:.2f} (peso {pain.weight:.1f})")
            lines.append("")

        lines.append("=== FIM DAS MEMÓRIAS ===\n")

        result = "\n".join(lines)
        if len(result) > max_chars:
            result = result[:max_chars] + "\n..."

        return result


# Singleton
_pain_memory_system: PainMemorySystem | None = None


def get_pain_memory() -> PainMemorySystem:
    """Retorna singleton de PainMemorySystem."""
    global _pain_memory_system
    if _pain_memory_system is None:
        _pain_memory_system = PainMemorySystem()
        logger.info("PainMemorySystem initialized")
    return _pain_memory_system


if __name__ == "__main__":
    # Test mode
    system = get_pain_memory()

    # Registrar algumas dores de teste
    system.remember_pain(
        ticker="AAPL",
        loss_amount=-150,
        thesis="Breakout above resistance with volume spike",
        what_went_wrong="Resistance held, gap down next day",
    )

    system.remember_pain(
        ticker="TSLA",
        loss_amount=-600,
        thesis="Earnings beat expected, pre-market jump",
        what_went_wrong="Guidance lowered, sell-off during call",
    )

    # Stats
    stats = system.get_stats()
    print(f"Total memories: {stats['total_memories']}")
    print(f"Traumas: {stats['traumas']}")
    print(f"Avg weight: {stats['avg_weight']}")
    print(f"\n{system.render_for_bob()}")
