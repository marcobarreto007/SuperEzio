"""
F51 Scoring — PlatinumScorer e RiskEngine.

Re-export do módulo canônico f51/scoring/__init__.py.
Bug p_refute corrigido: sum(0 for ...) → sum(1 for ...).
"""

from f51.scoring import (
    PlatinumScorer,
    DeterministicScorer,
    RiskEngine,
    RiskRule,
    Candidate,
)

__all__ = [
    "PlatinumScorer",
    "DeterministicScorer",
    "RiskEngine",
    "RiskRule",
    "Candidate",
]
