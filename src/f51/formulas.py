"""
f51 unified core — fórmulas matemáticas.
Todas as fórmulas de decisão em um lugar, sem duplicação.
Funções base (sigmoid, clamp, t_norm, t_conorm) importadas de core.math.
"""

from __future__ import annotations
from dataclasses import dataclass

from core.math.utils import (  # noqa: F401 — re-exported by __init__
    sigmoid,
    clamp,
    t_norm,
    t_conorm,
)

# =============================================================================
# FÓRMULA PLATINUM UNIFICADA
# =============================================================================


@dataclass(frozen=True)
class FormulaWeights:
    """Pesos da fórmula unificada de decisão.

    D = argmax σ(
        w_veracity * V(a) +
        w_consensus * C(a) +
        w_proxy * P(a) +
        w_robustness * R(a) -
        w_uncertainty * U(input) -
        w_danger * S(input)
    )
    """

    veracity: float = 2.0
    consensus: float = 1.5
    proxy: float = 1.0
    robustness: float = 0.5
    uncertainty: float = 2.0  # peso negativo
    danger: float = 3.0  # peso negativo — fraud detection deve pesar forte

    @staticmethod
    def default() -> FormulaWeights:
        return FormulaWeights()


@dataclass
class DecisionFactors:
    """Fatores que alimentam a fórmula de decisão."""

    veracity: float = 0.0  # claims batem com dados?
    consensus: float = 0.0  # múltiplas fontes concordam?
    proxy_reward: float = 0.0  # histórico similar deu certo?
    robustness: float = 0.0  # passou em verificação adversarial?
    uncertainty: float = 0.0  # dificuldade do problema/dado
    danger: float = 0.0  # armadilhas detectadas

    def validate(self):
        for k, v in self.__dict__.items():
            assert 0.0 <= v <= 1.0, f"{k}={v} fora de [0,1]"


def unified_decision(
    factors: DecisionFactors,
    weights: FormulaWeights = None,
) -> float:
    """Score heurístico de decisão, dados os fatores e pesos fixos.

    O sigmoid limita o resultado a ``[0, 1]``, mas não o transforma em
    probabilidade. Sem calibração prospectiva e validação fora da amostra,
    este valor não deve ser interpretado como ``P(sucesso)``.
    """
    w = weights or FormulaWeights.default()
    factors.validate()

    raw = (
        +w.veracity * factors.veracity
        + w.consensus * factors.consensus
        + w.proxy * factors.proxy_reward
        + w.robustness * factors.robustness
        - w.uncertainty * factors.uncertainty
        - w.danger * factors.danger
    )
    return sigmoid(raw)


# =============================================================================
# FÓRMULA DE RISCO (T-NORM)
# =============================================================================


def combined_risk(*risks: float) -> float:
    """Risco combinado via t-conorm: P(pelo menos um ocorre).

    Substitui max(r1, r2, ..., rn) que subestima risco conjunto.
    """
    if not risks:
        return 0.0
    result = 0.0
    for r in risks:
        result = t_conorm(result, clamp(r))
    return result


# =============================================================================
# PROXY REWARD (sem ground truth)
# =============================================================================


def proxy_reward(
    consensus: float,
    critic: float,
    sanity: float,
    diversity_penalty: float = 0.0,
    ground_truth_bonus: float = 0.0,
    has_ground_truth: bool = False,
) -> float:
    """Recompensa calculada sem gabarito.

    reward = 0.3·consenso + 0.4·critic + 0.2·sanity
             - 0.1·diversity_penalty + 0.2·ground_truth_bonus
    Cap: 0.9 sem ground truth, 1.0 com.
    """
    total = (
        0.3 * clamp(consensus)
        + 0.4 * clamp(critic)
        + 0.2 * clamp(sanity)
        - 0.1 * clamp(diversity_penalty)
    ) + (0.2 * clamp(ground_truth_bonus) if has_ground_truth else 0.0)
    cap = 1.0 if has_ground_truth else 0.9
    return clamp(total, 0.0, cap)


# =============================================================================
# HEURISTIC UNCERTAINTY
# =============================================================================


def heuristic_uncertainty(
    text: str = "",
    numeric_features: dict[str, float] = None,
) -> float:
    """Estimativa de incerteza baseada em features textuais e numéricas.

    u = 0.15 (baseline)
    + penalidades por features de dificuldade
    clamp(u, 0.05, 0.95)
    """
    u = 0.15
    text_lower = text.lower()

    # Features de dificuldade textual
    if len(text) > 800:
        u += 0.20
    if len(text) > 1600:
        u += 0.20
    for kw in ["prove", "show that", "for all", "suppose"]:
        if kw in text_lower:
            u += 0.10
            break
    for kw in ["triangle", "circle", "angle", "perpendicular"]:
        if kw in text_lower:
            u += 0.10
            break
    for kw in ["number of", "count", "ways", "choose"]:
        if kw in text_lower:
            u += 0.10
            break
    if "mod" in text_lower or "congruen" in text_lower:
        u += 0.10

    # Features numéricas
    if numeric_features:
        if numeric_features.get("missing_data_ratio", 0) > 0.3:
            u += 0.15
        if numeric_features.get("volatility", 0) > 0.5:
            u += 0.15
        if numeric_features.get("data_points", 100) < 20:
            u += 0.10

    return clamp(u, 0.05, 0.95)


# =============================================================================
# THRESHOLDS POR DOMÍNIO
# =============================================================================


def decision_threshold(domain: str = "default") -> float:
    """Threshold mínimo de confiança para tomar decisão."""
    return {
        "trading": 0.75,
        "math": 0.85,
        "code_review": 0.80,
        "contract": 0.85,
        "default": 0.70,
    }.get(domain, 0.70)


def expand_budget(confidence: float, domain: str = "default") -> bool:
    """Deve expandir orçamento computacional?"""
    return confidence < decision_threshold(domain)
