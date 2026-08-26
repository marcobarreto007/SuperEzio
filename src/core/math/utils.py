"""
Funções matemáticas utilitárias.

Importadas de core.mathcore.base — fonte canônica única.
"""

from __future__ import annotations

import math
from collections.abc import Sequence


def sigmoid(x: float) -> float:
    """σ(x) estável contra overflow."""
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    """Restringe x ao intervalo [lo, hi]."""
    return max(lo, min(hi, x))


def t_norm(a: float, b: float) -> float:
    """T-norm produto: P(A ∧ B)."""
    return a * b


def t_conorm(a: float, b: float) -> float:
    """T-conorm (soma probabilística): P(A ∨ B) = 1-(1-a)(1-b)."""
    return 1.0 - (1.0 - a) * (1.0 - b)


def percentile_rank(values: Sequence[float], value: float) -> float:
    """Percentil de value em values (0-100)."""
    if not values:
        return 50.0
    below = sum(1 for v in values if v < value)
    equal = sum(1 for v in values if v == value)
    return 100.0 * (below + 0.5 * equal) / len(values)


def zscore(value: float, mean: float, std: float) -> float:
    """Z-score padrão."""
    if std == 0:
        return 0.0
    return (value - mean) / std
