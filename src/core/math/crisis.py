"""
CrisisMath — 12 modelos de crise com interface unificada compute().

Wraps experts/crisis/models/* que já possuem evaluate(CrisisInput) -> SensorResult.
Adiciona método compute(data: dict) -> dict para integração com o pipeline.

Modelos:
  bis_credit_gap      — BIS Credit-to-GDP Gap Sensor
  credit_asset_growth — fixed-weight credit/asset percentile heuristic
  debt_service_ratio  — debt-service historical-percentile heuristic
  growth_at_risk      — Growth-at-Risk (quantile regression)
  hawkes_stress       — Hawkes Stress Process (clustering de eventos)
  imf_mispricing      — compatibility key for an equity rolling-z heuristic
  lppls_bubble        — LPPLS Bubble Detection (log-periodic power law)
  markov_regime       — Markov Regime Switching
  minsky_keen         — compatibility key for a fixed debt-fragility heuristic
  network_contagion   — Network Contagion (requires bank exposures)
  shiller_valuation   — housing ratio percentile heuristic (not Shiller CAPE)
  systemic_bank_risk  — Systemic Bank Risk (requires bank balance sheets)
"""

from __future__ import annotations
from typing import Any

# ── Imports dos modelos originais ──────────────────────────────────────
from experts.crisis.contracts.schemas import (
    CrisisInput,
    MacroObservation,
    MarketObservation,
    SensorResult,
)
from experts.crisis.logic.scoring import classify_alert_level, classify_regime

from experts.crisis.models.bis_credit_gap import BISCreditGapModel
from experts.crisis.models.credit_asset_growth import CreditAssetGrowthModel
from experts.crisis.models.debt_service_ratio import DebtServiceRatioModel
from experts.crisis.models.growth_at_risk import GrowthAtRiskModel
from experts.crisis.models.hawkes_stress import HawkesStressModel
from experts.crisis.models.imf_mispricing import IMFMispricingModel
from experts.crisis.models.lppls_bubble import LPPLSBubbleModel
from experts.crisis.models.markov_regime import MarkovRegimeModel
from experts.crisis.models.minsky_keen import MinskyKeenModel
from experts.crisis.models.network_contagion import NetworkContagionModel
from experts.crisis.models.shiller_valuation import ShillerValuationModel
from experts.crisis.models.systemic_bank_risk import SystemicBankRiskModel

# ── Registry ───────────────────────────────────────────────────────────

CRISIS_MODELS = {
    "bis_credit_gap": BISCreditGapModel,
    "credit_asset_growth": CreditAssetGrowthModel,
    "debt_service_ratio": DebtServiceRatioModel,
    "growth_at_risk": GrowthAtRiskModel,
    "hawkes_stress": HawkesStressModel,
    "imf_mispricing": IMFMispricingModel,
    "lppls_bubble": LPPLSBubbleModel,
    "markov_regime": MarkovRegimeModel,
    "minsky_keen": MinskyKeenModel,
    "network_contagion": NetworkContagionModel,
    "shiller_valuation": ShillerValuationModel,
    "systemic_bank_risk": SystemicBankRiskModel,
}


# ── Helper: dict → CrisisInput ─────────────────────────────────────────


def _dict_to_observations(data: dict[str, Any]) -> list[MacroObservation]:
    """Converte dict de features financeiras para MacroObservation."""
    obs_list = data.get("observations", [])
    if obs_list:
        return [MacroObservation(**o) if isinstance(o, dict) else o for o in obs_list]

    feature_names = {
        "credit_to_gdp",
        "credit_growth_yoy",
        "gdp_growth_yoy",
        "debt_service_ratio",
        "house_price_index",
        "rent_index",
        "income_index",
        "equity_index",
        "policy_rate",
        "unemployment_rate",
        "inflation_yoy",
    }
    if not any(data.get(name) is not None for name in feature_names):
        return []
    if not data.get("date"):
        raise ValueError("flat crisis observations require an explicit ISO-8601 date")

    # Compatibility for one flat observation, without inventing a timestamp.
    obs = MacroObservation(
        date=data["date"],
        credit_to_gdp=data.get("credit_to_gdp"),
        credit_growth_yoy=data.get("credit_growth_yoy"),
        gdp_growth_yoy=data.get("gdp_growth_yoy"),
        debt_service_ratio=data.get("debt_service_ratio"),
        house_price_index=data.get("house_price_index"),
        rent_index=data.get("rent_index"),
        income_index=data.get("income_index"),
        equity_index=data.get("equity_index"),
        policy_rate=data.get("policy_rate"),
        unemployment_rate=data.get("unemployment_rate"),
        inflation_yoy=data.get("inflation_yoy"),
    )
    return [obs]


def _dict_to_market_series(data: dict[str, Any]) -> list[MarketObservation] | None:
    """Converte dict para MarketObservation series."""
    market = data.get("market_series") or data.get("market")
    if not market:
        # Closing-price arrays need real dates; synthetic t0/t1 labels are forbidden.
        prices = data.get("prices") or data.get("close_prices") or []
        if prices:
            dates = data.get("market_dates") or []
            if len(dates) != len(prices):
                raise ValueError("prices require market_dates with identical length")
            return [MarketObservation(date=d, close=p) for d, p in zip(dates, prices)]
        return None
    if isinstance(market, list):
        return [MarketObservation(**m) if isinstance(m, dict) else m for m in market]
    return None


# ── Unified compute() ──────────────────────────────────────────────────


def crisis_evaluate(model_name: str, data: dict[str, Any]) -> dict[str, Any]:
    """Roda um modelo CrisisMath específico com dados em formato dict.

    Args:
        model_name: chave do CRISIS_MODELS registry
        data: dict com campos financeiros (observations, market_series, etc.)

    Returns:
        dict com score, confidence, status, explanation, details
    """
    model_cls = CRISIS_MODELS.get(model_name)
    if model_cls is None:
        return {
            "model": model_name,
            "score": 0.0,
            "confidence": 0.0,
            "method_kind": "unavailable",
            "horizon": None,
            "sample_size": 0,
            "as_of": None,
            "calibration_status": "failed",
            "status": "error",
            "explanation": f"Modelo '{model_name}' não encontrado. Disponível: {list(CRISIS_MODELS)}",
        }

    try:
        obs = _dict_to_observations(data)
        market = _dict_to_market_series(data)
        inp = CrisisInput(
            country=data.get("country"),
            asset_symbol=data.get("asset_symbol"),
            frequency=data.get("frequency", "monthly"),
            observations=obs,
            market_series=market,
            metadata=data.get("metadata", {}),
        )
        model = model_cls()
        result: SensorResult = model.evaluate(inp)
        return {
            "model": model_name,
            "sensor_name": result.sensor_name,
            "score": result.score,
            "confidence": result.confidence,
            "status": result.status,
            "explanation": result.explanation,
            "method_kind": result.method_kind,
            "horizon": result.horizon,
            "sample_size": result.sample_size,
            "as_of": result.as_of,
            "calibration_status": result.calibration_status,
            "details": result.details,
        }
    except Exception as exc:
        return {
            "model": model_name,
            "score": 0.0,
            "confidence": 0.0,
            "method_kind": "unavailable",
            "horizon": None,
            "sample_size": 0,
            "as_of": None,
            "calibration_status": "failed",
            "status": "error",
            "explanation": str(exc)[:200],
        }


def crisis_aggregate(
    data: dict[str, Any],
    models: list[str] = None,
) -> dict[str, Any]:
    """Roda todos (ou lista específica de) modelos CrisisMath e agrega scores.

    Returns:
        dict com scores individuais, score agregado, regime, alert_level
    """
    to_run = models or list(CRISIS_MODELS.keys())
    results: dict[str, dict[str, Any]] = {}
    scores: list[float] = []
    confidences: list[float] = []

    for name in to_run:
        r = crisis_evaluate(name, data)
        results[name] = r
        if r["status"] == "ok":
            scores.append(r["score"])
            confidences.append(r["confidence"])

    if not scores:
        known_as_of = [result.get("as_of") for result in results.values() if result.get("as_of")]
        known_samples = [
            result.get("sample_size", 0)
            for result in results.values()
            if result.get("sample_size", 0) > 0
        ]
        return {
            "results": results,
            "status": "unavailable",
            "aggregate_score": None,
            "aggregate_confidence": 0.0,
            "regime": "unavailable",
            "alert_level": "unavailable",
            "models_run": len(to_run),
            "models_ok": 0,
            "models_failed": len(to_run),
            "method_kind": "unavailable",
            "horizon": None,
            "sample_size": max(known_samples) if known_samples else 0,
            "as_of": max(known_as_of) if known_as_of else None,
            "calibration_status": "unavailable",
        }

    avg_score = sum(scores) / len(scores)
    avg_conf = sum(confidences) / len(confidences)
    available = [result for result in results.values() if result["status"] == "ok"]
    known_samples = [result["sample_size"] for result in available if result["sample_size"] > 0]
    known_as_of = [result["as_of"] for result in available if result["as_of"]]
    alert = classify_alert_level(avg_score)
    regime = classify_regime(avg_score, avg_score, avg_score)

    return {
        "results": results,
        "status": "ok" if len(scores) == len(to_run) else "partial",
        "aggregate_score": round(avg_score, 4),
        "aggregate_confidence": round(avg_conf, 4),
        "regime": regime,
        "alert_level": alert,
        "models_run": len(to_run),
        "models_ok": len(scores),
        "models_failed": len(to_run) - len(scores),
        "method_kind": "component_mean_ensemble",
        "horizon": "mixed_component_horizons",
        "sample_size": min(known_samples) if known_samples else 0,
        "as_of": max(known_as_of) if known_as_of else None,
        "calibration_status": "component_level_only",
    }


def crisis_classify(score: float) -> str:
    """Classifica score 0-1 em nível de alerta."""
    return classify_alert_level(score)
