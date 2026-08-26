"""
f51-hub adapter — conecta o motor f51 aos dados reais do SuperEzio.

Lê fraud_patterns/red_flag_rules.json do hub e monta um F51Engine
configurado com as regras reais de risco.
"""

from __future__ import annotations

import json
import logging
import math
import statistics
from pathlib import Path
from typing import Any

from f51 import DifficultyEstimator, F51Engine, RiskRule, SpiderSense, VeracityGate
from f51.formulas import heuristic_uncertainty
from f51.graph import Context, Graph, Node, NodeResult

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


def _finite_float(val: Any) -> float | None:
    """Return a real finite observation; never invent a numeric default."""
    try:
        value = float(val)
    except (ValueError, TypeError):
        return None
    return value if math.isfinite(value) else None


def _first_finite(*values: Any) -> float | None:
    for value in values:
        parsed = _finite_float(value)
        if parsed is not None:
            return parsed
    return None


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

        def make_evaluator(rid: str, cond: str, _tmpl: str | None):
            def evaluate(data: dict[str, Any]) -> tuple[bool, str]:
                features = data.get("features", {})
                triggered = False
                evidence = ""

                if rid == "unusual_volume_without_clear_news":
                    z = features.get("volume_z_score")
                    triggered = z is not None and 2.0 <= z < 3.5
                    if triggered:
                        evidence = f"volume_z_score={z:.2f}"

                elif rid == "extreme_volume_spike":
                    z = features.get("volume_z_score")
                    triggered = z is not None and z >= 3.5
                    if triggered:
                        evidence = f"extreme_volume_zscore={z:.2f}"

                elif rid == "price_spike_high_volatility":
                    observed_return = features.get("daily_return")
                    daily_ret = abs(observed_return) if observed_return is not None else None
                    mcap = features.get("market_cap")
                    triggered = daily_ret is not None and (
                        daily_ret >= 0.15
                        or (daily_ret >= 0.10 and mcap is not None and mcap < 200_000_000)
                    )
                    if triggered:
                        evidence = f"daily_return={daily_ret:.2%}, mcap={mcap}"

                elif rid == "microcap_concentration":
                    mcap = features.get("market_cap")
                    triggered = mcap is not None and mcap < 50_000_000
                    if triggered:
                        evidence = f"market_cap={mcap}"

                elif rid == "vague_hype_sector_description":
                    hype_count = features.get("hype_keyword_count", 0)
                    triggered = hype_count >= 2
                    if triggered:
                        evidence = f"hype_keywords={hype_count}"

                elif rid == "no_revenue_with_operations":
                    revenue = features.get("total_revenue", None)
                    mcap = features.get("market_cap")
                    triggered = revenue == 0 and (mcap is not None and mcap > 10_000_000)
                    if triggered:
                        evidence = f"revenue={revenue}, mcap={mcap}"

                return triggered, evidence

            return evaluate

        evaluator = make_evaluator(rule_id, condition_str, item.get("evidence_id_template"))
        limitation = item.get("limitation_when_absent") or ""
        rules.append(
            RiskRule(name=rule_id, weight=weight, evaluate=evaluator, limitation=limitation)
        )
    return rules


def _build_claims(trace: dict[str, Any]) -> list[tuple[str, float, str]]:
    """Read explicit claims only; observed features are not their own proof."""
    claims: list[tuple[str, float, str]] = []
    raw_claims = trace.get("claims") or []
    for item in raw_claims:
        if isinstance(item, dict):
            field = str(item.get("field", "")).strip()
            value = _finite_float(item.get("value"))
            context = str(item.get("source") or item.get("context") or "explicit")
        elif isinstance(item, (tuple, list)) and len(item) >= 2:
            field = str(item[0]).strip()
            value = _finite_float(item[1])
            context = str(item[2]) if len(item) >= 3 else "explicit"
        else:
            continue
        if field and value is not None:
            claims.append((field, value, context))
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
        from f51.gates import AdversarialCritic
        from f51.scoring import RiskEngine

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
        missing = features.get("missing_data_ratio", 1.0)
        volatility = features.get("annual_volatility")
        text = str(inp.get("user_text", ""))
        u = heuristic_uncertainty(text, features)
        volatility_penalty = min(max(volatility, 0.0), 2.0) if volatility is not None else 0.0
        u = min(0.95, u + 0.2 * missing + 0.1 * volatility_penalty)
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
        present = sum(1 for f in fields if f in features and features[f] is not None)
        completeness = present / len(fields)

        rsi = features.get("rsi_14")
        daily_ret = features.get("daily_return")
        consistent = 1.0
        if rsi is not None and daily_ret is not None and rsi > 70 and daily_ret < 0:
            consistent *= 0.7
        if rsi is not None and daily_ret is not None and rsi < 30 and daily_ret > 0:
            consistent *= 0.7
        vol_z = features.get("volume_z_score")
        if vol_z is not None and abs(vol_z) > 3:
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
                confidence=0.0,
                evidence={"passed": False, "reason": "no_independent_claims"},
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
        observed = {
            k: v for k, v in features.items() if k not in {"missing_data_ratio", "data_points"}
        }
        if not observed:
            return NodeResult(
                "adversarial_critic",
                value="",
                confidence=0.0,
                evidence={"issues": ["no_financial_features"], "robustness": 0.0},
            )
        result = self.critic.evaluate_finance(features)
        return NodeResult(
            "adversarial_critic",
            value="",
            confidence=result.confidence,
            evidence={"issues": result.errors, "robustness": result.confidence},
        )

    @staticmethod
    def extract_features(trace: dict[str, Any]) -> dict[str, Any]:
        """Extract only finite observations or causal candle-derived values."""
        tech = trace.get("technicals", {}) or {}
        prof = trace.get("profile") or trace.get("fundamentals") or {}
        risk = trace.get("risk", {}) or {}
        quant = trace.get("quant", {}) or {}
        sentiment = trace.get("sentiment", {}) or {}
        reddit = trace.get("reddit") or trace.get("social") or {}
        price_payload = trace.get("price", {}) or {}
        candles = trace.get("candles") or trace.get("ohlcv") or []
        if not candles and isinstance(price_payload, dict):
            candles = price_payload.get("candles") or price_payload.get("ohlcv") or []

        closes = [
            value
            for candle in candles
            if isinstance(candle, dict)
            and (value := _finite_float(candle.get("close"))) is not None
            and value > 0
        ]
        price = _first_finite(
            tech.get("price"),
            price_payload.get("price") if isinstance(price_payload, dict) else None,
            price_payload.get("last") if isinstance(price_payload, dict) else None,
            closes[-1] if closes else None,
        )

        daily_return = None
        if len(closes) >= 2 and closes[-2] != 0:
            daily_return = closes[-1] / closes[-2] - 1.0

        candle_volumes = [
            value
            for candle in candles
            if isinstance(candle, dict)
            and (value := _finite_float(candle.get("volume"))) is not None
            and value >= 0
        ]
        volume = _first_finite(tech.get("volume"), candle_volumes[-1] if candle_volumes else None)
        avg_volume = None
        volume_z = None
        historical_volumes = candle_volumes[:-1]
        if volume is not None and historical_volumes:
            avg_volume = statistics.fmean(historical_volumes)
            if len(historical_volumes) >= 2:
                std_volume = statistics.stdev(historical_volumes)
                if std_volume > 0:
                    volume_z = (volume - avg_volume) / std_volume

        mcap = _first_finite(prof.get("market_cap"), prof.get("marketCap"))

        summary = str(prof.get("summary") or prof.get("description") or "").lower()
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
        candidates = {
            "price": price,
            "daily_return": daily_return,
            "volume": volume,
            "avg_volume": avg_volume,
            "volume_z_score": volume_z,
            "market_cap": mcap,
            "rsi_14": _finite_float(tech.get("rsi_14")),
            "annual_volatility": _finite_float(risk.get("annual_volatility")),
            "var_95": _finite_float(risk.get("var_95")),
            "sharpe_ratio": _finite_float(risk.get("sharpe_ratio")),
            "total_revenue": _first_finite(prof.get("total_revenue"), prof.get("revenue")),
            "sentiment_score": _first_finite(
                sentiment.get("sentiment_score"), sentiment.get("score")
            ),
            "reddit_sentiment": _first_finite(reddit.get("sentiment_score"), reddit.get("score")),
            "monte_carlo_prob_up": _finite_float(quant.get("monte_carlo_prob_up")),
            "ml_prob_up": _finite_float(quant.get("ml_prob_up")),
        }
        features = {key: value for key, value in candidates.items() if value is not None}
        if summary:
            features["hype_keyword_count"] = sum(1 for kw in hype_keywords if kw in summary)
        expected = (
            "price",
            "daily_return",
            "volume_z_score",
            "market_cap",
            "rsi_14",
            "annual_volatility",
            "sentiment_score",
        )
        observed = sum(1 for key in expected if key in features)
        features["missing_data_ratio"] = 1.0 - observed / len(expected)
        features["data_points"] = len(closes)
        return features

    def run_on_trace(self, trace: dict[str, Any], domain: str = "trading") -> dict[str, Any]:
        """Roda o f51 motor em um trace completo do SuperEzio."""
        features = self.extract_features(trace)

        user_text = str(trace.get("user_message") or trace.get("message") or "")
        from f51 import SpiderSense

        spider = SpiderSense()
        danger, alerts = spider.detect(user_text)

        claims = _build_claims(trace)
        raw_truth = trace.get("independent_ground_truth")
        independent_truth = (
            {
                str(key): value
                for key, raw_value in raw_truth.items()
                if (value := _finite_float(raw_value)) is not None
            }
            if isinstance(raw_truth, dict)
            else {}
        )
        f51_input = {
            "features": features,
            "claims": claims,
            "ground_truth": independent_truth,
            "ticker": trace.get("ticker", ""),
            "user_text": user_text,
            "danger": danger,
            "alerts": [a.__dict__ for a in alerts],
        }

        result = self.engine.run(f51_input, domain=domain)

        risk_result = self.risk_engine.evaluate({"features": features})
        risk_result["score_type"] = "deterministic_rule_risk_score"
        result["hub_risk"] = risk_result

        vgate = self.veracity_gate.verify(claims, independent_truth, tolerance=0.15)
        result["veracity_explicit"] = {
            "passed": vgate.passed,
            "confidence": vgate.confidence,
            "verified": vgate.verified,
            "total": vgate.total,
            "mismatches": vgate.mismatches,
            "details": vgate.details,
        }
        reason_codes: list[str] = []
        if not claims:
            reason_codes.append("NO_INDEPENDENT_CLAIMS")
        if claims and not independent_truth:
            reason_codes.append("NO_INDEPENDENT_GROUND_TRUTH")
        if not vgate.passed:
            reason_codes.append("VERACITY_NOT_ESTABLISHED")
        if vgate.verified < 2:
            reason_codes.append("INSUFFICIENT_INDEPENDENT_VERIFICATION")
        if features.get("missing_data_ratio", 1.0) > 0.5:
            reason_codes.append("INSUFFICIENT_MARKET_EVIDENCE")

        evidence_ready = not reason_codes
        result["heuristic_score"] = result.get("decision_score", result.get("confidence", 0.0))
        result["score_type"] = "uncalibrated_decision_score"
        result["calibration_status"] = "not_calibrated"
        result["evidence_status"] = "verified" if evidence_ready else "insufficient"
        result["reason_codes"] = reason_codes
        result["passed"] = bool(result.get("passed")) and evidence_ready

        return result
