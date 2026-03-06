"""
F51 Gates — VeracityGate e AdversarialCritic.

Re-export do módulo canônico f51/gates/__init__.py.
AdversarialCritic.evaluate_finance() é a implementação DRY compartilhada
entre o grafo default F51 e o F51HubAdapter.
"""

from f51.gates import (
    VeracityGate,
    VeracityResult,
    AdversarialCritic,
    CriticResult,
)

__all__ = [
    "VeracityGate",
    "VeracityResult",
    "AdversarialCritic",
    "CriticResult",
]
