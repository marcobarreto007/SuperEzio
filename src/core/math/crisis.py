"""
CrisisMath — 12 modelos de crise com interface unificada compute().

Wraps experts/crisis/models/* que já possuem evaluate(CrisisInput) -> SensorResult.
Adiciona método compute(data: dict) -> dict para integração com o pipeline.

Modelos:
  bis_credit_gap      — BIS Credit-to-GDP Gap Sensor
  credit_asset_growth — Credit-Asset Growth Divergence
  debt_service_ratio  — Debt Service Ratio Monitor
  growth_at_risk      — Growth-at-Risk (quantile regression lite)
  hawkes_stress       — Hawkes Stress Process (clustering de eventos)
  imf_mispricing      — IMF House Price Mispricing
  lppls_bubble        — LPPLS Bubble Detection (log-periodic power law)
  markov_regime       — Markov Regime Switching
  minsky_keen         — Minsky-Keen Financial Instability
  network_contagion   — Network Contagion (CoVaR)
  shiller_valuation   — Shiller CAPE Valuation
  systemic_bank_risk  — Systemic Bank Risk (SRISK lite)
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

    # Fallback: constrói a partir de features planas
    obs = MacroObservation(
        date=data.get("date", "unknown"),
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
        # Fallback: usa close prices se disponíveis
        prices = data.get("prices") or data.get("close_prices") or []
        if prices:
            return [MarketObservation(date=f"t{i}", close=p) for i, p in enumerate(prices)]
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
            "score": result.score,
            "confidence": result.confidence,
            "status": result.status,
            "explanation": result.explanation,
            "details": result.details,
        }
    except Exception as exc:
        return {
            "model": model_name,
            "score": 0.0,
            "confidence": 0.0,
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
        return {
            "results": results,
            "aggregate_score": 0.0,
            "aggregate_confidence": 0.0,
            "regime": "normal",
            "alert_level": "green",
            "models_run": len(to_run),
            "models_ok": 0,
        }

    avg_score = sum(scores) / len(scores)
    avg_conf = sum(confidences) / len(confidences)
    alert = classify_alert_level(avg_score)
    regime = classify_regime(avg_score, avg_score, avg_score)

    return {
        "results": results,
        "aggregate_score": round(avg_score, 4),
        "aggregate_confidence": round(avg_conf, 4),
        "regime": regime,
        "alert_level": alert,
        "models_run": len(to_run),
        "models_ok": len(scores),
        "models_failed": len(to_run) - len(scores),
    }


def crisis_classify(score: float) -> str:
    """Classifica score 0-1 em nível de alerta."""
    return classify_alert_level(score)
