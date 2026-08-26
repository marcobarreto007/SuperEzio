"""
f51 unified core — motor de decisão com incerteza calibrada.

Combina o melhor de SuperEzio (PennyLab, FraudPatternAnalyst, VeracityGate,
RiskCalculator) com o melhor de NelsonMath (SpiderSense, PlatinumScorer,
ProxyReward, HeuristicUncertainty) em uma arquitetura de grafo.

Uso:
    from f51 import F51Engine
    engine = F51Engine()
    result = engine.run({"ticker": "AAPL"}, domain="trading")
    print(result["confidence"], result["passed"])

Módulos:
    formulas.py       — fórmulas matemáticas (fator único de verdade)
    detectors.py      — SpiderSense, DifficultyEstimator
    scoring.py        — PlatinumScorer, DeterministicScorer, RiskEngine
    gates.py          — VeracityGate, AdversarialCritic, ProxyReward
    graph.py          — Graph, F51Engine (orquestração)
"""

from __future__ import annotations

from .detectors import TRAP_PATTERNS, DifficultyEstimator, SpiderAlert, SpiderSense
from .formulas import (
    DecisionFactors,
    FormulaWeights,
    combined_risk,
    heuristic_uncertainty,
    proxy_reward,
    sigmoid,
    t_conorm,
    t_norm,
    unified_decision,
)
from .gates import (
    AdversarialCritic,
    CriticResult,
    ProxyReward,
    VeracityGate,
    VeracityResult,
)
from .graph import Context, F51Engine, Graph, Node, NodeResult
from .scoring import (
    Candidate,
    DeterministicScorer,
    PlatinumScorer,
    RiskEngine,
    RiskRule,
)

__all__ = [
    "TRAP_PATTERNS",
    "AdversarialCritic",
    "Candidate",
    "Context",
    "CriticResult",
    "DecisionFactors",
    "DeterministicScorer",
    "DifficultyEstimator",
    "F51Engine",
    "FormulaWeights",
    "Graph",
    "Node",
    "NodeResult",
    "PlatinumScorer",
    "ProxyReward",
    "RiskEngine",
    "RiskRule",
    "SpiderAlert",
    "SpiderSense",
    "VeracityGate",
    "VeracityResult",
    "combined_risk",
    "heuristic_uncertainty",
    "proxy_reward",
    "sigmoid",
    "t_conorm",
    "t_norm",
    "unified_decision",
]
