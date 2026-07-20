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
from .graph import F51Engine, Graph, Node, Context, NodeResult
from .formulas import (
    unified_decision,
    DecisionFactors,
    FormulaWeights,
    combined_risk,
    proxy_reward,
    heuristic_uncertainty,
    sigmoid,
    t_norm,
    t_conorm,
)
from .detectors import SpiderSense, SpiderAlert, DifficultyEstimator, TRAP_PATTERNS
from .scoring import (
    PlatinumScorer,
    Candidate,
    DeterministicScorer,
    RiskEngine,
    RiskRule,
)
from .gates import (
    VeracityGate,
    VeracityResult,
    AdversarialCritic,
    CriticResult,
    ProxyReward,
)

__all__ = [
    "F51Engine",
    "Graph",
    "Node",
    "Context",
    "NodeResult",
    "unified_decision",
    "DecisionFactors",
    "FormulaWeights",
    "combined_risk",
    "proxy_reward",
    "heuristic_uncertainty",
    "sigmoid",
    "t_norm",
    "t_conorm",
    "SpiderSense",
    "SpiderAlert",
    "DifficultyEstimator",
    "TRAP_PATTERNS",
    "PlatinumScorer",
    "Candidate",
    "DeterministicScorer",
    "RiskEngine",
    "RiskRule",
    "VeracityGate",
    "VeracityResult",
    "AdversarialCritic",
    "CriticResult",
    "ProxyReward",
]
