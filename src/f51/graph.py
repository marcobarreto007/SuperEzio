"""
f51 unified core — grafo de execução.
Orquestra nós paralelos com fusão de crença.
"""

from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from .formulas import (
    unified_decision,
    DecisionFactors,
    decision_threshold,
    expand_budget,
)

# =============================================================================
# TIPOS DO GRAFO
# =============================================================================


@dataclass
class NodeResult:
    """Resultado de um nó do grafo."""

    node: str
    value: Any = None
    confidence: float = 0.0
    evidence: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    elapsed_ms: float = 0.0

    @property
    def ok(self) -> bool:
        return not self.error


@dataclass
class Context:
    """Contexto compartilhado entre nós do grafo."""

    input: Any = None
    domain: str = "default"
    results: dict[str, NodeResult] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    start_time: float = 0.0

    def add(self, node: str, result: NodeResult):
        self.results[node] = result

    def get(self, node: str) -> NodeResult | None:
        return self.results.get(node)

    def factor(self, node: str, field: str = "value", default: float = 0.0) -> float:
        r = self.results.get(node)
        if r and r.ok:
            # 1. Tenta atributo direto no NodeResult (ex: confidence)
            if field != "value" and hasattr(r, field):
                v = getattr(r, field)
            # 2. Tenta atributo no r.value (se r.value for objeto)
            elif hasattr(r.value, field):
                v = getattr(r.value, field)
            # 3. Usa r.value diretamente
            else:
                v = r.value

            if isinstance(v, (int, float)):
                return float(v)
        return default

    @property
    def elapsed(self) -> float:
        return time.time() - self.start_time


# =============================================================================
# NÓS
# =============================================================================


@dataclass
class Node:
    """Um nó do grafo."""

    name: str
    fn: Callable[[Context], NodeResult]
    depends_on: list[str] = field(default_factory=list)
    parallel: bool = True  # pode rodar em paralelo com outros nós


class Graph:
    """Grafo de execução DAG.

    Resolve dependências automaticamente e executa nós
    que podem rodar em paralelo simultaneamente.
    """

    def __init__(self, nodes: list[Node] | None = None):
        self.nodes: dict[str, Node] = {}
        if nodes:
            for n in nodes:
                self.nodes[n.name] = n

    def add(self, node: Node):
        self.nodes[node.name] = node

    def execute(self, input: Any, domain: str = "default") -> Context:
        ctx = Context(input=input, domain=domain, start_time=time.time())
        executed = set()
        remaining = set(self.nodes.keys())

        while remaining:
            ready = [
                n
                for n in remaining
                if all(dep in executed for dep in self.nodes[n].depends_on)
            ]
            for node_name in ready:
                remaining.remove(node_name)
                node = self.nodes[node_name]
                t0 = time.time()
                try:
                    result = node.fn(ctx)
                except Exception as e:
                    result = NodeResult(node=node_name, error=str(e))
                result.elapsed_ms = (time.time() - t0) * 1000
                ctx.add(node_name, result)
                executed.add(node_name)

        return ctx


# =============================================================================
# F51 ENGINE
# =============================================================================


class F51Engine:
    """Motor de decisão unificado com grafo, fórmula, e memória.

    Uso:
        engine = F51Engine()
        result = engine.run(input_data, domain="trading")
    """

    def __init__(self, graph: Graph | None = None, memory=None):
        self.graph = graph or self._build_default_graph()
        self.memory = memory  # EpisodeMemory instance

    def run(self, input: Any, domain: str = "default") -> dict[str, Any]:
        ctx = self.graph.execute(input, domain=domain)

        # Extrai fatores da fórmula unificada dos resultados do grafo
        factors = DecisionFactors(
            veracity=ctx.factor("veracity_gate", "confidence"),
            consensus=ctx.factor("platinum_scorer"),
            proxy_reward=self._compute_proxy(ctx),
            robustness=ctx.factor("adversarial_critic", "confidence"),
            uncertainty=ctx.factor("difficulty_estimator"),
            danger=ctx.factor("spider_sense"),
        )

        confidence = unified_decision(factors)
        threshold = decision_threshold(domain)
        should_expand = expand_budget(confidence, domain)

        return {
            "confidence": round(confidence, 3),
            "threshold": threshold,
            "passed": confidence >= threshold,
            "expand_compute": should_expand,
            "factors": factors.__dict__,
            "nodes": {
                name: {
                    "ok": r.ok,
                    "confidence": r.confidence,
                    "elapsed_ms": r.elapsed_ms,
                    "error": r.error,
                }
                for name, r in ctx.results.items()
            },
            "evidence": {
                name: r.evidence for name, r in ctx.results.items() if r.evidence
            },
            "elapsed_ms": ctx.elapsed * 1000,
        }

    def _compute_proxy(self, ctx: Context) -> float:
        critic = ctx.get("adversarial_critic")
        critic_conf = critic.confidence if critic and critic.ok else 0.5
        return 0.3 * ctx.factor("platinum_scorer") + 0.4 * critic_conf + 0.2 * 0.8

    def _build_default_graph(self) -> Graph:
        """Constrói o grafo padrão com todos os detectores/scorers/gates."""
        from .detectors import SpiderSense, DifficultyEstimator
        from .gates import VeracityGate, AdversarialCritic

        spider = SpiderSense()
        estimator = DifficultyEstimator()
        gate = VeracityGate()

        graph = Graph()
        graph.add(
            Node(
                "spider_sense",
                lambda ctx: NodeResult(
                    "spider_sense",
                    *spider.detect(str(ctx.input)),
                    evidence={"danger": 1.0},
                ),
            )
        )
        graph.add(
            Node(
                "difficulty_estimator",
                lambda ctx: NodeResult(
                    "difficulty_estimator",
                    estimator.estimate(str(ctx.input)),
                ),
            )
        )
        # --- platinum_scorer: qualidade/consistência dos dados ---
        _PLATINUM_FIELDS = [
            "price",
            "rsi_14",
            "annual_volatility",
            "sharpe_ratio",
            "var_95",
            "sentiment_score",
            "market_cap",
        ]

        def _default_platinum_node(ctx: Context) -> NodeResult:
            features = (
                ctx.input.get("features", {}) if isinstance(ctx.input, dict) else {}
            )
            if not features:
                return NodeResult("platinum_scorer", 0.5, confidence=0.5)

            # Completude: fração de campos-chave presentes e não-zero
            present = sum(
                1
                for f in _PLATINUM_FIELDS
                if features.get(f) is not None and features.get(f) != 0
            )
            completeness = present / len(_PLATINUM_FIELDS)

            # Consistência: RSI vs daily_return
            consistent = 1.0
            rsi = features.get("rsi_14", 50)
            daily_ret = features.get("daily_return", 0)
            if rsi > 70 and daily_ret < 0:
                consistent *= 0.7
            if rsi < 30 and daily_ret > 0:
                consistent *= 0.7

            vol_z = abs(features.get("volume_z_score", 0))
            if vol_z > 3:
                consistent *= 0.8

            score = completeness * consistent
            return NodeResult(
                "platinum_scorer",
                score,
                confidence=score,
                evidence={"completeness": completeness, "consistency": consistent},
            )

        graph.add(
            Node(
                "platinum_scorer",
                _default_platinum_node,
                depends_on=["spider_sense"],
            )
        )

        # --- veracity_gate: verifica claims contra ground_truth ---
        def _default_veracity_node(ctx: Context) -> NodeResult:
            if not isinstance(ctx.input, dict):
                return NodeResult(
                    "veracity_gate", "", confidence=1.0, evidence={"reason": "no_dict"}
                )

            claims = ctx.input.get("claims", [])
            ground_truth = ctx.input.get("ground_truth", {})

            if not claims:
                return NodeResult(
                    "veracity_gate",
                    "",
                    confidence=1.0,
                    evidence={"reason": "sem_claims"},
                )

            result = gate.verify(claims, ground_truth, tolerance=0.15)
            return NodeResult(
                "veracity_gate",
                "",
                confidence=result.confidence,
                evidence={
                    "passed": result.passed,
                    "verified": result.verified,
                    "total": result.total,
                    "mismatches": result.mismatches,
                },
            )

        graph.add(Node("veracity_gate", _default_veracity_node))

        # --- adversarial_critic: consistência lógica financeira ---
        critic = AdversarialCritic()

        def _default_critic_node(ctx: Context) -> NodeResult:
            features = (
                ctx.input.get("features", {}) if isinstance(ctx.input, dict) else {}
            )
            result = critic.evaluate_finance(features)
            return NodeResult(
                "adversarial_critic",
                "",
                confidence=result.confidence,
                evidence={"issues": result.errors, "robustness": result.confidence},
            )

        graph.add(Node("adversarial_critic", _default_critic_node))
        return graph
