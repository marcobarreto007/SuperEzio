"""
f51 unified core — scorers.
PlatinumScorer (consenso) + PennyLab (determinístico) + RiskEngine (regras).
"""

from __future__ import annotations
from dataclasses import dataclass
from collections import Counter
from typing import Any

from .formulas import sigmoid, clamp, t_conorm

# =============================================================================
# PLATINUM SCORER — consenso entre múltiplas fontes
# =============================================================================


@dataclass
class Candidate:
    """Uma hipótese/candidato a solução."""

    final: str
    check_pass: float = 0.0  # fração 0-1 de verificações que passou
    refuted: bool = False  # foi refutado pelo crítico?
    confidence: float = 0.5  # confiança auto-reportada


class PlatinumScorer:
    """Avalia confiança em um conjunto de candidatos.

    P(success) = σ(3·consenso + 2·check + 1.5·(1-refuted_ratio) - 2.5·U)
    """

    @staticmethod
    def score(candidates: list[Candidate], uncertainty: float = 0.0) -> float:
        if not candidates:
            return 0.0

        # Consenso: frequência da resposta modal
        finals = [c.final.lower().strip() for c in candidates]
        mode_freq = Counter(finals).most_common(1)[0][1]
        p_consensus = mode_freq / len(candidates)

        # Check: média de verificações que passaram
        p_check = sum(c.check_pass for c in candidates) / len(candidates)

        # Refutação: fração NÃO refutada
        p_refute = sum(1 for c in candidates if not c.refuted) / len(candidates)

        # Fórmula
        raw = (
            3.0 * p_consensus
            + 2.0 * p_check
            + 1.5 * p_refute
            - 2.5 * clamp(uncertainty)
        )
        return sigmoid(raw)

    @staticmethod
    def rank(candidates: list[Candidate]) -> list[Candidate]:
        """Ordena candidatos por score."""
        scored = []
        for c in candidates:
            s = c.check_pass + (0.0 if c.refuted else 1.0) + c.confidence
            scored.append((s, c))
        scored.sort(key=lambda x: -x[0])
        return [s[1] for s in scored]

    @staticmethod
    def best(candidates: list[Candidate]) -> Candidate | None:
        ranked = PlatinumScorer.rank(candidates)
        return ranked[0] if ranked else None


# =============================================================================
# DETERMINISTIC SCORER — scores compostos por regras
# =============================================================================


class DeterministicScorer:
    """Motor de scoring determinístico com composição linear.

    Substitui PennyLab scoring e FraudPatternAnalyst.
    Cada score é uma composição de sub-scores com pesos.
    """

    @staticmethod
    def linear(components: dict[str, float], weights: dict[str, float]) -> float:
        """Score linear ponderado com saturação em 1.0."""
        total = 0.0
        for name, value in components.items():
            w = weights.get(name, 1.0)
            total += w * clamp(value)
        return clamp(total / max(sum(weights.values()), 0.01))

    @staticmethod
    def hierarchical(
        features: dict[str, float],
        rules: list[tuple[str, list[str], list[float]]],
    ) -> dict[str, float]:
        """Score hierárquico: regras compostas de features.

        rules = [(output_name, [feature_names], [weights])]
        Ex: [("trap_risk", ["pump", "spread"], [0.5, 0.5])]
        """
        results = {}
        for output_name, feats, weights in rules:
            values = [features.get(f, 0.0) for f in feats]
            total_w = sum(weights)
            if total_w == 0:
                results[output_name] = 0.0
                continue
            score = sum(v * w for v, w in zip(values, weights)) / total_w
            results[output_name] = clamp(score)
        return results

    @staticmethod
    def threshold_decision(
        scores: dict[str, float],
        rules: list[tuple[str, float, str]],
    ) -> str:
        """Árvore de thresholds: retorna primeira regra que satisfaz.

        rules = [(score_name, min_threshold, decision)]
        """
        for name, threshold, decision in rules:
            if scores.get(name, 0.0) >= threshold:
                return decision
        return "none"


# =============================================================================
# RISK ENGINE — regras computáveis + whale signals
# =============================================================================


@dataclass
class RiskRule:
    """Uma regra de risco computável."""

    name: str
    weight: float
    evaluate: callable = lambda data: (False, "")  # (triggered, evidence)
    limitation: str = ""


class RiskEngine:
    """Motor de risco baseado em regras.

    Substitui FraudPatternAnalyst.
    Usa t-conorm para combinar riscos (não max()).
    """

    def __init__(self, rules: list[RiskRule] | None = None):
        self.rules = rules or []

    def evaluate(self, data: dict[str, Any]) -> dict[str, Any]:
        triggered = []
        evidence_ids = []
        limitations = []
        risk_scores = []

        for rule in self.rules:
            try:
                fired, evidence = rule.evaluate(data)
            except Exception:
                continue

            if fired:
                triggered.append(rule.name)
                if evidence:
                    evidence_ids.append(evidence)
                risk_scores.append(rule.weight)
            elif rule.limitation:
                limitations.append(rule.limitation)

        # Risco combinado via t-conorm (não max!)
        combined = 0.0
        for s in risk_scores:
            combined = t_conorm(combined, s)

        return {
            "risk_score": round(combined, 3),
            "triggered_rules": triggered,
            "evidence_ids": evidence_ids,
            "n_evaluated": len(self.rules),
            "limitations": limitations,
        }
