"""
f51-hub adapter — conecta o motor f51 aos dados reais do SuperEzio.

Lê fraud_patterns/red_flag_rules.json do hub e monta um F51Engine
configurado com as regras reais de risco.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from f51 import F51Engine, RiskRule, VeracityGate, SpiderSense, DifficultyEstimator
from f51.formulas import heuristic_uncertainty
from f51.graph import Graph, Node, NodeResult, Context

PROJECT_ROOT = Path(__file__).resolve().parents[3]
FRAUD_RULES_PATH = PROJECT_ROOT / "data" / "fraud_patterns" / "red_flag_rules.json"
FRAUD_PATTERNS_PATH = PROJECT_ROOT / "data" / "fraud_patterns" / "fraud_patterns.json"
logger = logging.getLogger(__name__)


def _load_json(path: Path) -> dict | list:
    if not path.exists():
        logger.warning("[F51_ADAPTER] missing JSON file: %s", path)
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("[F51_ADAPTER] failed to parse %s: %s", path, exc)
        return {}


def _volume_z_score(volume: int, avg_volume: float) -> float:
    if avg_volume <= 0:
        return 0.0
    return (volume - avg_volume) / max(avg_volume, 1.0)


def _build_risk_rules_from_hub() -> list[RiskRule]:
    """Converte red_flag_rules.json do hub em RiskRule do f51."""
    data = _load_json(FRAUD_RULES_PATH)
    rules = []
    for item in data.get("rules", []):
        if not item.get("computable"):
            continue
        rule_id = item["rule_id"]
        weight = float(item.get("weight", 0.25))
        condition_str = item.get("condition", "")

        def make_evaluator(rid: str, cond: str, tmpl: str | None):
            def evaluate(data: dict[str, Any]) -> tuple[bool, str]:
                features = data.get("features", {})
                triggered = False
                evidence = ""

                if rid == "unusual_volume_without_clear_news":
                    z = features.get("volume_z_score", 0)
                    triggered = 2.0 <= z < 3.5
                    if triggered:
                        evidence = f"volume_z_score={z:.2f}"

                elif rid == "extreme_volume_spike":
                    z = features.get("volume_z_score", 0)
                    triggered = z >= 3.5
                    if triggered:
                        evidence = f"extreme_volume_zscore={z:.2f}"

                elif rid == "price_spike_high_volatility":
                    daily_ret = abs(features.get("daily_return", 0))
                    mcap = features.get("market_cap", 0)
                    triggered = daily_ret >= 0.15 or (
                        daily_ret >= 0.10 and mcap < 200_000_000
                    )
                    if triggered:
                        evidence = f"daily_return={daily_ret:.2%}, mcap={mcap}"

                elif rid == "microcap_concentration":
                    mcap = features.get("market_cap", 0)
                    triggered = mcap < 50_000_000
                    if triggered:
                        evidence = f"market_cap={mcap}"

                elif rid == "vague_hype_sector_description":
                    hype_count = features.get("hype_keyword_count", 0)
                    triggered = hype_count >= 2
                    if triggered:
                        evidence = f"hype_keywords={hype_count}"

                elif rid == "no_revenue_with_operations":
                    revenue = features.get("total_revenue", None)
                    mcap = features.get("market_cap", 0)
                    triggered = (revenue == 0 or revenue is None) and mcap > 10_000_000
                    if triggered:
                        evidence = f"revenue={revenue}, mcap={mcap}"

                return triggered, evidence

            return evaluate

        evaluator = make_evaluator(
            rule_id, condition_str, item.get("evidence_id_template")
        )
        limitation = item.get("limitation_when_absent") or ""
        rules.append(
            RiskRule(
                name=rule_id, weight=weight, evaluate=evaluator, limitation=limitation
            )
        )
    return rules


def _missing_data_ratio(trace: dict[str, Any]) -> float:
    """Estima fração de campos críticos ausentes no trace."""
    critical_keys = ["technicals", "profile", "risk", "quant", "sentiment"]
    missing = 0
    for k in critical_keys:
        val = trace.get(k)
        if not val or (isinstance(val, dict) and len(val) <= 2):
            missing += 1
    return missing / len(critical_keys)


def _build_claims(trace: dict[str, Any]) -> list[tuple[str, float, str]]:
    """Extrai claims verificáveis do trace para o VeracityGate."""
    claims: list[tuple[str, float, str]] = []
    tech = trace.get("technicals", {}) or {}
    risk = trace.get("risk", {}) or {}
    quant = trace.get("quant", {}) or {}

    if tech.get("rsi_14") is not None:
        claims.append(("rsi_14", float(tech["rsi_14"]), "technical"))
    if tech.get("price") is not None:
        claims.append(("price", float(tech["price"]), "technical"))
    if risk.get("annual_volatility") is not None:
        claims.append(("annual_volatility", float(risk["annual_volatility"]), "risk"))
    if quant.get("monte_carlo_prob_up") is not None:
        claims.append(
            ("monte_carlo_prob_up", float(quant["monte_carlo_prob_up"]), "quant")
        )
    return claims


class F51HubAdapter:
    """Adaptador que liga o motor f51 aos dados do SuperEzio."""

    def __init__(self):
        self.rules = _build_risk_rules_from_hub()
        self.veracity_gate = VeracityGate()
        self.spider = SpiderSense()
        self.estimator = DifficultyEstimator()
        graph = self._build_financial_graph()
        self.engine = F51Engine(graph=graph)
        from f51.scoring import RiskEngine
        from f51.gates import AdversarialCritic

        self.risk_engine = RiskEngine(rules=self.rules)
        self.critic = AdversarialCritic()

    def _build_financial_graph(self) -> Graph:
        graph = Graph()
        graph.add(Node("spider_sense", lambda ctx: self._node_spider(ctx)))
        graph.add(Node("difficulty_estimator", lambda ctx: self._node_difficulty(ctx)))
        graph.add(
            Node(
                "platinum_scorer",
                lambda ctx: self._node_platinum(ctx),
                depends_on=["spider_sense", "difficulty_estimator"],
            )
        )
        graph.add(Node("veracity_gate", lambda ctx: self._node_veracity(ctx)))
        graph.add(
            Node(
                "adversarial_critic",
                lambda ctx: self._node_critic(ctx),
                depends_on=["veracity_gate", "difficulty_estimator"],
            )
        )
        return graph

    @staticmethod
    def _node_spider(ctx: Context) -> NodeResult:
        inp = ctx.input or {}
        text = str(inp.get("user_text", ""))
        danger, alerts = ctx.metadata.get("spider_result", (0.0, []))
        if not alerts and text:
            spider = SpiderSense()
            danger, alerts = spider.detect(text)
        return NodeResult(
            "spider_sense",
            value=danger,
            confidence=1.0 - danger,
            evidence={"alerts": [a.__dict__ for a in alerts], "danger": danger},
        )

    @staticmethod
    def _node_difficulty(ctx: Context) -> NodeResult:
        inp = ctx.input or {}
        features = inp.get("features", {})
        missing = features.get("missing_data_ratio", 0.0)
        volatility = features.get("annual_volatility", 0.2)
        text = str(inp.get("user_text", ""))
        u = heuristic_uncertainty(text, features)
        u = min(0.95, u + 0.2 * missing + 0.1 * volatility)
        return NodeResult(
            "difficulty_estimator",
            value=u,
            confidence=1.0 - u,
            evidence={"missing_data_ratio": missing, "volatility": volatility},
        )

    @staticmethod
    def _node_platinum(ctx: Context) -> NodeResult:
        inp = ctx.input or {}
        features = inp.get("features", {})
        fields = [
            "price",
            "rsi_14",
            "annual_volatility",
            "sharpe_ratio",
            "var_95",
            "sentiment_score",
            "market_cap",
        ]
        present = sum(
            1 for f in fields if features.get(f) is not None and features.get(f) != 0
        )
        completeness = present / len(fields)

        rsi = features.get("rsi_14", 50)
        daily_ret = features.get("daily_return", 0)
        consistent = 1.0
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
            value=score,
            confidence=score,
            evidence={"completeness": completeness, "consistency": consistent},
        )

    @staticmethod
    def _node_veracity(ctx: Context) -> NodeResult:
        inp = ctx.input or {}
        claims = inp.get("claims", [])
        ground_truth = inp.get("ground_truth", {})
        if not claims:
            return NodeResult(
                "veracity_gate",
                value="",
                confidence=1.0,
                evidence={"reason": "sem_claims"},
            )
        gate = VeracityGate()
        result = gate.verify(claims, ground_truth, tolerance=0.15)
        return NodeResult(
            "veracity_gate",
            value="",
            confidence=result.confidence,
            evidence={
                "passed": result.passed,
                "verified": result.verified,
                "total": result.total,
                "mismatches": result.mismatches,
            },
        )

    def _node_critic(self, ctx: Context) -> NodeResult:
        inp = ctx.input or {}
        features = inp.get("features", {})
        result = self.critic.evaluate_finance(features)
        return NodeResult(
            "adversarial_critic",
            value="",
            confidence=result.confidence,
            evidence={"issues": result.errors, "robustness": result.confidence},
        )

    @staticmethod
    def extract_features(trace: dict[str, Any]) -> dict[str, Any]:
        """Extrai features numéricas de um trace do DataCollector."""
        tech = trace.get("technicals", {}) or {}
        prof = trace.get("profile", {}) or {}
        risk = trace.get("risk", {}) or {}
        quant = trace.get("quant", {}) or {}
        sentiment = trace.get("sentiment", {}) or {}
        reddit = trace.get("reddit", {}) or {}

        price = tech.get("price") if tech.get("price") is not None else 0
        if isinstance(price, (int, float)) and price > 0:
            rsi = tech.get("rsi_14") if tech.get("rsi_14") is not None else 50
            if rsi > 80:
                daily_ret = 0.18
            elif rsi < 20:
                daily_ret = -0.18
            else:
                daily_ret = 0.02
        else:
            daily_ret = 0.0

        volume = tech.get("volume") if tech.get("volume") is not None else 0
        avg_volume = volume
        volume_z = 0.0

        mcap = prof.get("market_cap") if prof.get("market_cap") is not None else 0
        if isinstance(mcap, str):
            mcap = 0

        summary = str(prof.get("summary", "")).lower()
        hype_keywords = [
            "artificial intelligence",
            "ai-powered",
            "blockchain",
            "cryptocurrency",
            "quantum",
            "lithium",
            "cannabis",
            "marijuana",
            "metaverse",
            "nft",
            "web3",
            "chatbot",
            "autonomous vehicle",
            "disruptive",
            "revolutionary",
            "groundbreaking",
            "game-changer",
            "paradigm shift",
        ]
        hype_count = sum(1 for kw in hype_keywords if kw in summary)

        total_revenue = prof.get("total_revenue")
        if total_revenue is None:
            pe = prof.get("pe_ratio")
            if isinstance(pe, (int, float)) and pe > 0 and mcap > 0:
                total_revenue = mcap / pe
            else:
                total_revenue = 1

        features = {
            "price": float(price),
            "daily_return": daily_ret,
            "volume": int(volume),
            "avg_volume": float(avg_volume),
            "volume_z_score": volume_z,
            "market_cap": float(mcap),
            "rsi_14": float(tech.get("rsi_14") if tech.get("rsi_14") is not None else 50),
            "annual_volatility": float(risk.get("annual_volatility") if risk.get("annual_volatility") is not None else 0.2),
            "var_95": float(risk.get("var_95") if risk.get("var_95") is not None else -0.02),
            "sharpe_ratio": float(risk.get("sharpe_ratio") if risk.get("sharpe_ratio") is not None else 0),
            "hype_keyword_count": hype_count,
            "total_revenue": float(total_revenue) if total_revenue else 0,
            "sentiment_score": float(sentiment.get("sentiment_score") if sentiment.get("sentiment_score") is not None else 0),
            "reddit_sentiment": float(reddit.get("sentiment_score") if reddit.get("sentiment_score") is not None else 0),
            "monte_carlo_prob_up": float(quant.get("monte_carlo_prob_up") if quant.get("monte_carlo_prob_up") is not None else 50),
            "ml_prob_up": float(quant.get("ml_prob_up") if quant.get("ml_prob_up") is not None else 50),
            "missing_data_ratio": _missing_data_ratio(trace),
        }
        return features

    def run_on_trace(
        self, trace: dict[str, Any], domain: str = "trading"
    ) -> dict[str, Any]:
        """Roda o f51 motor em um trace completo do SuperEzio."""
        features = self.extract_features(trace)

        user_text = trace.get("user_message", "")
        from f51 import SpiderSense

        spider = SpiderSense()
        danger, alerts = spider.detect(user_text)

        f51_input = {
            "features": features,
            "claims": _build_claims(trace),
            "ground_truth": features,
            "ticker": trace.get("ticker", ""),
            "user_text": user_text,
            "danger": danger,
            "alerts": [a.__dict__ for a in alerts],
        }

        self.engine._metadata = {"spider_result": (danger, alerts)}

        result = self.engine.run(f51_input, domain=domain)

        risk_result = self.risk_engine.evaluate(features)
        result["hub_risk"] = risk_result

        claims = f51_input["claims"]
        if claims:
            vgate = self.veracity_gate.verify(claims, features, tolerance=0.15)
            result["veracity_explicit"] = {
                "passed": vgate.passed,
                "confidence": vgate.confidence,
                "mismatches": vgate.mismatches,
            }

        return result
