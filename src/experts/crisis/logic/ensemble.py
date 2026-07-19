"""
Ensemble logic to combine sensor scores.
"""

from typing import Any

from ..contracts.schemas import SensorResult


def aggregate_scores(results: list[SensorResult]) -> dict[str, Any]:
    valid_results = {r.sensor_name: r.score for r in results if r.status == "ok"}

    # Defaults
    scores = {
        "systemic_risk_score": 0.0,
        "bubble_risk_score": 0.0,
        "credit_fragility_score": 0.0,
        "liquidity_stress_score": 0.0,
        "final_risk_score": 0.0,
        "confidence": 0.0,
        "status": "unavailable",
        "models_available": 0,
    }

    if not valid_results:
        return scores

    scores["status"] = "ok" if len(valid_results) == len(results) else "partial"
    scores["models_available"] = len(valid_results)

    def weighted_avg(weights: dict) -> float:
        total_w = 0.0
        val = 0.0
        for k, w in weights.items():
            if k in valid_results:
                val += valid_results[k] * w
                total_w += w
        return val / total_w if total_w > 0 else 0.0

    scores["systemic_risk_score"] = weighted_avg(
        {
            "BISCreditGapModel": 0.20,
            "DebtServiceRatioModel": 0.15,
            "CreditAssetGrowthModel": 0.20,
            "ShillerValuationModel": 0.15,
            "IMFMispricingModel": 0.10,
            "MinskyKeenModel": 0.10,
            "MarkovRegimeModel": 0.10,
        }
    )

    scores["bubble_risk_score"] = weighted_avg(
        {
            "CreditAssetGrowthModel": 0.30,
            "ShillerValuationModel": 0.40,
            "IMFMispricingModel": 0.20,
            "LPPLSBubbleModel": 0.10,
        }
    )

    scores["credit_fragility_score"] = weighted_avg(
        {
            "BISCreditGapModel": 0.40,
            "DebtServiceRatioModel": 0.30,
            "MinskyKeenModel": 0.30,
        }
    )

    scores["liquidity_stress_score"] = weighted_avg(
        {
            "MarkovRegimeModel": 0.40,
            "HawkesStressModel": 0.30,
            "GrowthAtRiskModel": 0.30,
        }
    )

    final = (
        scores["systemic_risk_score"] * 0.35
        + scores["bubble_risk_score"] * 0.25
        + scores["credit_fragility_score"] * 0.20
        + scores["liquidity_stress_score"] * 0.20
    )
    scores["final_risk_score"] = min(max(final, 0.0), 1.0)

    # Confidence combines model confidence and coverage across the 12-sensor ensemble.
    valid = [r for r in results if r.status == "ok"]
    mean_confidence = sum(r.confidence for r in valid) / len(valid)
    coverage = min(len(valid) / 12.0, 1.0)
    scores["confidence"] = mean_confidence * coverage

    return scores
