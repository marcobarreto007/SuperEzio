"""Reflection Committee - Multi-agent deliberação para decisões críticas.

Bob consulta um comitê de agentes especializados antes de tomar decisões:
- CAUTIOUS (Prudente): Foca em risco, vê o lado negativo
- OPTIMIST (Otimista): Foca em upside, vê oportunidade
- ANALYST (Analista): Dados puros, sem emoção
- HISTORIAN (Historiador): Baseado em histórico, lições passadas

O comitê vota e Bob segue o consenso (ou supermajority se houver conflito).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

DEFAULT_COMMITTEE_LOG_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent / "data" / "committee_log.jsonl"
)


class CommitteeRole(Enum):
    """Papéis no comitê."""

    CAUTIOUS = "Cautious"
    OPTIMIST = "Optimist"
    ANALYST = "Analyst"
    HISTORIAN = "Historian"


class VoteType(Enum):
    """Tipos de voto."""

    APPROVE = "approve"
    REJECT = "reject"
    ABSTAIN = "abstain"
    CONDITIONAL = "conditional"  # Aprova com condições


@dataclass
class CommitteeVote:
    """Voto de um membro do comitê."""

    role: CommitteeRole
    vote: VoteType
    confidence: float  # 0-1, quão confiante no voto
    reasoning: str
    conditions: list[str] = field(default_factory=list)  # Se conditional

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role.value,
            "vote": self.vote.value,
            "confidence": round(self.confidence, 3),
            "reasoning": self.reasoning,
            "conditions": self.conditions,
        }


@dataclass
class CommitteeDecision:
    """Decisão do comitê."""

    timestamp: str
    setup: dict[str, Any]
    votes: list[CommitteeVote]
    consensus: VoteType
    approval_rate: float  # 0-1
    reasoning_summary: str
    conditions: list[str] = field(default_factory=list)
    override_required: bool = False  # Se true, requer supermajority

    @property
    def is_approved(self) -> bool:
        """Se a decisão foi aprovada."""
        return self.consensus == VoteType.APPROVE or (
            self.consensus == VoteType.CONDITIONAL and self.approval_rate >= 0.6
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "setup": self.setup,
            "votes": [v.to_dict() for v in self.votes],
            "consensus": self.consensus.value,
            "approval_rate": round(self.approval_rate, 3),
            "reasoning_summary": self.reasoning_summary,
            "conditions": self.conditions,
            "override_required": self.override_required,
            "is_approved": self.is_approved,
        }


class CommitteeMember(ABC):
    """Base para membros do comitê."""

    def __init__(self, role: CommitteeRole):
        self.role = role

    @abstractmethod
    def evaluate(
        self, setup: dict[str, Any], context: dict[str, Any] | None = None
    ) -> CommitteeVote:
        """Avalia setup e retorna voto."""
        pass


class CautiousMember(CommitteeMember):
    """Membro prudente - foca em risco."""

    def __init__(self):
        super().__init__(CommitteeRole.CAUTIOUS)

    def evaluate(
        self,
        setup: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> CommitteeVote:
        """Vota baseado em risco."""
        context = context or {}

        # Fatores de risco
        risk_factors = []

        # Checar pain memory
        pain_risk = setup.get("pain_risk", "low")
        if pain_risk == "high":
            risk_factors.append("Alto risco baseado em dores passadas")

        # Checar confiança
        confidence = setup.get("confidence", 0)
        if confidence < 0.6:
            risk_factors.append("Confiança baixa")

        # Checar liquidez
        liquidity = setup.get("avg_daily_dollar_volume", 0)
        if liquidity < 10_000_000:
            risk_factors.append("Liquidez baixa")

        # Checar drawdown recente
        drawdown = context.get("drawdown_pct", 0)
        if drawdown > 10:
            risk_factors.append(f"Drawdown alto ({drawdown:.1f}%)")

        # Checar loss streak
        loss_streak = context.get("loss_streak", 0)
        if loss_streak >= 2:
            risk_factors.append(f"Loss streak ({loss_streak})")

        # Decisão
        num_risks = len(risk_factors)

        if num_risks >= 3 or (num_risks >= 2 and loss_streak >= 3):
            return CommitteeVote(
                role=self.role,
                vote=VoteType.REJECT,
                confidence=0.8,
                reasoning=f"Risco inaceitável: {', '.join(risk_factors)}",
            )
        elif num_risks >= 2:
            return CommitteeVote(
                role=self.role,
                vote=VoteType.CONDITIONAL,
                confidence=0.7,
                reasoning=f"Risco moderado: {', '.join(risk_factors)}",
                conditions=["Reduzir tamanho da posição", "Stop loss mais apertado"],
            )
        elif num_risks == 1:
            return CommitteeVote(
                role=self.role,
                vote=VoteType.ABSTAIN,
                confidence=0.6,
                reasoning=f"Risco presente mas aceitável: {risk_factors[0]}",
            )
        else:
            return CommitteeVote(
                role=self.role,
                vote=VoteType.APPROVE,
                confidence=0.5,
                reasoning="Risco dentro dos limites aceitáveis",
            )


class OptimistMember(CommitteeMember):
    """Membro otimista - foca em oportunidade."""

    def __init__(self):
        super().__init__(CommitteeRole.OPTIMIST)

    def evaluate(
        self,
        setup: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> CommitteeVote:
        """Vota baseado em oportunidade."""
        # Fatores de oportunidade
        opportunity_factors = []

        # Checar catalyst
        catalyst = setup.get("catalyst", "").lower()
        if any(kw in catalyst for kw in ["earnings", "beat", "guidance", "upgrade"]):
            opportunity_factors.append("Catalyst forte")

        # Checar confiança
        confidence = setup.get("confidence", 0)
        if confidence >= 0.7:
            opportunity_factors.append(f"Confiança alta ({confidence:.0%})")

        # Checar setup quality
        quality_gates = setup.get("gate_failures", [])
        if not quality_gates:
            opportunity_factors.append("Setup passou todos os gates")

        # Checar momentum
        momentum = setup.get("momentum", "").lower()
        if "bull" in momentum or "up" in momentum:
            opportunity_factors.append("Momentum positivo")

        # Checar recent wins
        win_streak = context.get("win_streak", 0)
        if win_streak >= 2:
            opportunity_factors.append(f"Win streak ({win_streak})")

        # Decisão
        num_opps = len(opportunity_factors)

        if num_opps >= 3:
            return CommitteeVote(
                role=self.role,
                vote=VoteType.APPROVE,
                confidence=0.9,
                reasoning=f"Oportunidade excelente: {', '.join(opportunity_factors)}",
            )
        elif num_opps >= 2:
            return CommitteeVote(
                role=self.role,
                vote=VoteType.APPROVE,
                confidence=0.7,
                reasoning=f"Oportunidade boa: {', '.join(opportunity_factors)}",
            )
        elif num_opps == 1:
            return CommitteeVote(
                role=self.role,
                vote=VoteType.ABSTAIN,
                confidence=0.5,
                reasoning=f"Oportunidade moderada: {opportunity_factors[0]}",
            )
        else:
            return CommitteeVote(
                role=self.role,
                vote=VoteType.REJECT,
                confidence=0.4,
                reasoning="Oportunidade insuficiente",
            )


class AnalystMember(CommitteeMember):
    """Membro analista - dados puros."""

    def __init__(self):
        super().__init__(CommitteeRole.ANALYST)

    def evaluate(
        self,
        setup: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> CommitteeVote:
        """Vota baseado em dados."""
        # Análise quantitativa
        score = 0.0
        factors = []

        # Confiança (0-25 pontos)
        confidence = setup.get("confidence", 0)
        score += confidence * 25

        # Liquidez (0-25 pontos)
        liquidity = setup.get("avg_daily_dollar_volume", 0)
        if liquidity >= 50_000_000:
            score += 25
            factors.append("Liquidez excelente")
        elif liquidity >= 10_000_000:
            score += 15
            factors.append("Liquidez boa")
        else:
            score += 5
            factors.append("Liquidez fraca")

        # Catalyst (0-25 pontos)
        catalyst = setup.get("catalyst", "")
        if catalyst and len(catalyst) > 50:
            score += 25
            factors.append("Catalyst detalhado")
        elif catalyst:
            score += 15
            factors.append("Catalyst presente")
        else:
            score += 5
            factors.append("Catalyst ausente")

        # Risk/Reward (0-25 pontos)
        rr_ratio = setup.get("risk_reward_ratio", 0)
        if rr_ratio >= 2.0:
            score += 25
            factors.append(f"R/R excelente ({rr_ratio:.1f})")
        elif rr_ratio >= 1.5:
            score += 15
            factors.append(f"R/R bom ({rr_ratio:.1f})")
        else:
            score += 5
            factors.append(f"R/R fraco ({rr_ratio:.1f})")

        # Decisão baseada em score
        if score >= 75:
            return CommitteeVote(
                role=self.role,
                vote=VoteType.APPROVE,
                confidence=score / 100,
                reasoning=f"Score alto ({score:.0f}/100): {', '.join(factors)}",
            )
        elif score >= 50:
            return CommitteeVote(
                role=self.role,
                vote=VoteType.ABSTAIN,
                confidence=score / 100,
                reasoning=f"Score médio ({score:.0f}/100): {', '.join(factors)}",
            )
        else:
            return CommitteeVote(
                role=self.role,
                vote=VoteType.REJECT,
                confidence=1 - (score / 100),
                reasoning=f"Score baixo ({score:.0f}/100): {', '.join(factors)}",
            )


class HistorianMember(CommitteeMember):
    """Membro historiador - baseado em histórico."""

    def __init__(self):
        super().__init__(CommitteeRole.HISTORIAN)

    def evaluate(
        self,
        setup: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> CommitteeVote:
        """Vota baseado em histórico."""
        context = context or {}

        # Histórico do ticker
        ticker = setup.get("ticker", "").upper()
        ticker_history = context.get("ticker_history", {}).get(ticker, {})

        # Performance passada
        past_trades = ticker_history.get("trades", 0)
        past_wins = ticker_history.get("wins", 0)

        factors = []

        if past_trades > 0:
            win_rate = past_wins / past_trades

            if win_rate >= 0.6:
                factors.append(f"Histórico favorável ({win_rate:.0%} win rate)")
                return CommitteeVote(
                    role=self.role,
                    vote=VoteType.APPROVE,
                    confidence=0.8,
                    reasoning=f"Ticker tem bom histórico: {win_rate:.0%} win rate em {past_trades} trades",
                )
            elif win_rate <= 0.4:
                factors.append(f"Histórico desfavorável ({win_rate:.0%} win rate)")
                return CommitteeVote(
                    role=self.role,
                    vote=VoteType.REJECT,
                    confidence=0.7,
                    reasoning=f"Ticker tem histórico ruim: {win_rate:.0%} win rate em {past_trades} trades",
                )
            else:
                factors.append(f"Histórico neutro ({win_rate:.0%} win rate)")
        else:
            factors.append("Sem histórico no ticker")

        # Checar lições aplicáveis
        lessons = context.get("applicable_lessons", [])
        if lessons:
            factors.append(f"{len(lessons)} lições aplicáveis")

        # Checar traumas
        traumas = context.get("similar_traumas", [])
        if traumas:
            factors.append(f"{len(traumas)} traumas similares")

        # Decisão
        if traumas and len(traumas) >= 2:
            return CommitteeVote(
                role=self.role,
                vote=VoteType.REJECT,
                confidence=0.8,
                reasoning=f"Múltiplos traumas similares: {', '.join(factors)}",
            )
        elif lessons and len(lessons) >= 2:
            return CommitteeVote(
                role=self.role,
                vote=VoteType.APPROVE,
                confidence=0.7,
                reasoning=f"Lição aplicável: {', '.join(factors)}",
            )
        else:
            return CommitteeVote(
                role=self.role,
                vote=VoteType.ABSTAIN,
                confidence=0.5,
                reasoning=f"Histórico insuficiente: {', '.join(factors)}",
            )


class ReflectionCommittee:
    """Comitê de reflexão do Bob."""

    def __init__(
        self,
        log_path: Path | None = None,
        approval_threshold: float = 0.75,  # 75% para aprovar
        override_threshold: float = 0.60,  # 60% para override de veto
    ):
        self._log_path = log_path or DEFAULT_COMMITTEE_LOG_PATH
        self._log_path.parent.mkdir(parents=True, exist_ok=True)

        self._approval_threshold = approval_threshold
        self._override_threshold = override_threshold

        # Inicializar membros
        self._members = [
            CautiousMember(),
            OptimistMember(),
            AnalystMember(),
            HistorianMember(),
        ]

        self._history: list[CommitteeDecision] = []

    def _save_decision(self, decision: CommitteeDecision) -> None:
        """Salva decisão no disco (append-only)."""
        with open(self._log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(decision.to_dict(), ensure_ascii=False) + "\n")

    def deliberate(
        self,
        setup: dict[str, Any],
        context: dict[str, Any] | None = None,
        require_unanimous: bool = False,
    ) -> CommitteeDecision:
        """Delibera sobre um setup.

        Args:
            setup: Setup de trade (ticker, thesis, confidence, etc.)
            context: Contexto adicional (histórico, performance, etc.)
            require_unanimous: Se True, requer aprovação unânime

        Returns:
            Decisão do comitê
        """
        context = context or {}

        # Coletar votos
        votes = []
        for member in self._members:
            try:
                vote = member.evaluate(setup, context)
                votes.append(vote)
            except Exception as e:
                logger.warning("Member %s failed to evaluate: %s", member.role.value, e)
                # Voto de falha = ABSTAIN
                votes.append(
                    CommitteeVote(
                        role=member.role,
                        vote=VoteType.ABSTAIN,
                        confidence=0.0,
                        reasoning=f"Erro na avaliação: {e}",
                    )
                )

        # Calcular resultado
        approve_count = sum(1 for v in votes if v.vote == VoteType.APPROVE)
        reject_count = sum(1 for v in votes if v.vote == VoteType.REJECT)
        conditional_count = sum(1 for v in votes if v.vote == VoteType.CONDITIONAL)
        total = len(votes)

        approval_rate = approve_count / total if total > 0 else 0

        # Determinar consenso
        if require_unanimous:
            if reject_count > 0:
                consensus = VoteType.REJECT
                approval_rate = 0
            else:
                consensus = VoteType.APPROVE
        elif reject_count >= (total / 2):
            # Maioria rejeita
            consensus = VoteType.REJECT
        elif approve_count >= (total * self._approval_threshold):
            # Supermaioria aprova
            consensus = VoteType.APPROVE
        elif conditional_count > 0 and approve_count + conditional_count >= (
            total * self._approval_threshold
        ):
            # Aprova com condições
            consensus = VoteType.CONDITIONAL
        else:
            # Sem consenso
            consensus = VoteType.ABSTAIN

        # Coletar condições
        conditions = []
        for vote in votes:
            if vote.vote == VoteType.CONDITIONAL:
                conditions.extend(vote.conditions)

        # Sumário de reasoning
        reasonings = [f"{v.role.value}: {v.reasoning}" for v in votes]
        reasoning_summary = "\n".join(reasonings)

        # Override necessário se houver veto forte
        override_required = reject_count > 0 and approval_rate >= self._override_threshold

        decision = CommitteeDecision(
            timestamp=datetime.now(timezone.utc).isoformat(),
            setup=setup,
            votes=votes,
            consensus=consensus,
            approval_rate=approval_rate,
            reasoning_summary=reasoning_summary,
            conditions=conditions,
            override_required=override_required,
        )

        self._history.append(decision)
        self._save_decision(decision)

        logger.info(
            "Committee decision: %s (approval_rate=%.2f, override=%s)",
            consensus.value,
            approval_rate,
            override_required,
        )

        return decision

    def get_vote_breakdown(self, decision: CommitteeDecision) -> dict[str, Any]:
        """Retorna breakdown detalhado de votos."""
        by_vote = {
            VoteType.APPROVE: [],
            VoteType.REJECT: [],
            VoteType.ABSTAIN: [],
            VoteType.CONDITIONAL: [],
        }

        for vote in decision.votes:
            by_vote[vote.vote].append(vote.role.value)

        return {
            "total": len(decision.votes),
            "by_vote": {k.value: v for k, v in by_vote.items()},
            "approval_rate": decision.approval_rate,
            "consensus": decision.consensus.value,
        }

    def get_stats(self) -> dict[str, Any]:
        """Retorna estatísticas do comitê."""
        if not self._history:
            return {
                "total_deliberations": 0,
                "approval_rate": 0,
                "most_common_consensus": None,
            }

        total = len(self._history)
        approvals = sum(1 for d in self._history if d.consensus == VoteType.APPROVE)
        rejections = sum(1 for d in self._history if d.consensus == VoteType.REJECT)

        # Consenso mais comum
        consensus_counts = {}
        for d in self._history:
            consensus_counts[d.consensus.value] = consensus_counts.get(d.consensus.value, 0) + 1

        most_common = max(consensus_counts, key=consensus_counts.get) if consensus_counts else None

        return {
            "total_deliberations": total,
            "approval_rate": approvals / total if total > 0 else 0,
            "rejection_rate": rejections / total if total > 0 else 0,
            "most_common_consensus": most_common,
            "avg_approval_rate": sum(d.approval_rate for d in self._history) / total
            if total > 0
            else 0,
        }

    def render_for_bob(self, decision: CommitteeDecision, max_chars: int = 1000) -> str:
        """Renderiza decisão do comitê para o Bob."""
        lines = [
            "\n=== COMITÊ DE REFLEXÃO ===",
            f"Consensus: {decision.consensus.value}",
            f"Approval rate: {decision.approval_rate:.1%}",
            "",
        ]

        for vote in decision.votes:
            symbol = (
                "✓"
                if vote.vote == VoteType.APPROVE
                else "✗"
                if vote.vote == VoteType.REJECT
                else "~"
            )
            lines.append(
                f"{symbol} {vote.role.value}: {vote.vote.value} (conf: {vote.confidence:.2f})"
            )
            lines.append(f"   {vote.reasoning}")

        if decision.conditions:
            lines.append("")
            lines.append("Condições:")
            for cond in decision.conditions:
                lines.append(f"- {cond}")

        lines.append("=== FIM DO COMITÊ ===\n")

        result = "\n".join(lines)
        if len(result) > max_chars:
            result = result[:max_chars] + "\n..."

        return result


# Singleton
_committee: ReflectionCommittee | None = None


def get_reflection_committee() -> ReflectionCommittee:
    """Retorna singleton de ReflectionCommittee."""
    global _committee
    if _committee is None:
        _committee = ReflectionCommittee()
        logger.info("ReflectionCommittee initialized")
    return _committee


if __name__ == "__main__":
    # Test mode
    committee = get_reflection_committee()

    setup = {
        "ticker": "AAPL",
        "thesis": "Breakout above resistance with strong volume",
        "confidence": 0.75,
        "catalyst": "Earnings beat expectations",
        "avg_daily_dollar_volume": 50_000_000,
        "risk_reward_ratio": 2.0,
        "momentum": "bullish",
        "pain_risk": "low",
        "gate_failures": [],
    }

    context = {
        "drawdown_pct": 5.0,
        "win_streak": 2,
        "loss_streak": 0,
        "ticker_history": {"AAPL": {"trades": 5, "wins": 3, "losses": 2}},
        "applicable_lessons": ["Use tighter stops on breakouts"],
        "similar_traumas": [],
    }

    decision = committee.deliberate(setup, context)

    print(f"Consensus: {decision.consensus.value}")
    print(f"Approval rate: {decision.approval_rate:.1%}")

    print("\n" + committee.render_for_bob(decision))
