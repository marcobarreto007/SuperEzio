"""
F51 Decision Formulas — re-export do módulo canônico f51/formulas.py.

Estas fórmulas são a fonte única de verdade para decisão F51.
Importam funções base de core.mathcore.base (sigmoid, clamp, t_norm, t_conorm).
"""

from f51.formulas import (
    FormulaWeights,
    DecisionFactors,
    unified_decision,
    combined_risk,
    proxy_reward,
    heuristic_uncertainty,
    decision_threshold,
    expand_budget,
)

__all__ = [
    "FormulaWeights",
    "DecisionFactors",
    "unified_decision",
    "combined_risk",
    "proxy_reward",
    "heuristic_uncertainty",
    "decision_threshold",
    "expand_budget",
]
