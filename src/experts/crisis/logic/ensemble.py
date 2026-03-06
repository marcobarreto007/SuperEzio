"""
Ensemble logic to combine sensor scores.
"""

from typing import List, Dict
from ..contracts.schemas import SensorResult


def aggregate_scores(results: List[SensorResult]) -> Dict[str, float]:
    valid_results = {r.sensor_name: r.score for r in results if r.status == "ok"}

    # Defaults
    scores = {
        "systemic_risk_score": 0.0,
        "bubble_risk_score": 0.0,
        "credit_fragility_score": 0.0,
        "liquidity_stress_score": 0.0,
        "final_risk_score": 0.0,
        "confidence": 0.0,
    }

    if not valid_results:
        return scores

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

    scores["final_risk_score"] = weighted_avg(
        {
            "systemic_risk_score_virtual": 0.35,  # virtual mapping below
            "bubble_risk_score_virtual": 0.25,
            "credit_fragility_score_virtual": 0.20,
            "liquidity_stress_score_virtual": 0.20,
        }
    )  # Actually we just combine the computed ones

    final = (
        scores["systemic_risk_score"] * 0.35
        + scores["bubble_risk_score"] * 0.25
        + scores["credit_fragility_score"] * 0.20
        + scores["liquidity_stress_score"] * 0.20
    )
    scores["final_risk_score"] = final

    # Confidence drops if sensors missing
    scores["confidence"] = (len(valid_results) / 8.0) * 100.0  # Assumes 8 core sensors
    scores["confidence"] = min(scores["confidence"], 100.0)

    return scores
