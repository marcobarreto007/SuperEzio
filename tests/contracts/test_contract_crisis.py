"""Contract tests for Crisis Expert, Ensemble, and crisis model interfaces."""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Crisis Expert
# ---------------------------------------------------------------------------


def test_crisis_expert_imports():
    from experts.crisis.expert.crisis_expert import CrisisMathExpert

    assert CrisisMathExpert is not None


def test_crisis_expert_instantiation():
    from experts.crisis.expert.crisis_expert import CrisisMathExpert

    expert = CrisisMathExpert()
    assert expert is not None
    assert len(expert.sensors) == 12  # all 12 crisis models registered


# ---------------------------------------------------------------------------
# Crisis Ensemble (functional module, no class)
# ---------------------------------------------------------------------------


def test_crisis_ensemble_aggregate_import():
    from experts.crisis.logic.ensemble import aggregate_scores

    assert callable(aggregate_scores)


def test_crisis_ensemble_aggregate_empty():
    from experts.crisis.logic.ensemble import aggregate_scores

    result = aggregate_scores([])
    assert isinstance(result, dict)
    assert "final_risk_score" in result
    assert result["final_risk_score"] == 0.0
    assert result["confidence"] == 0.0


# ---------------------------------------------------------------------------
# Crisis Schemas
# ---------------------------------------------------------------------------


def test_crisis_schemas_import():
    from experts.crisis.contracts.schemas import CrisisInput, SensorResult, CrisisReport

    assert CrisisInput is not None
    assert SensorResult is not None
    assert CrisisReport is not None


def test_crisis_input_default():
    from experts.crisis.contracts.schemas import CrisisInput

    inp = CrisisInput()
    assert inp.frequency == "monthly"
    assert inp.observations == []


def test_crisis_report_default():
    from experts.crisis.contracts.schemas import CrisisReport

    report = CrisisReport(
        systemic_risk_score=0.0,
        bubble_risk_score=0.0,
        liquidity_stress_score=0.0,
        credit_fragility_score=0.0,
        final_risk_score=0.0,
        regime="normal",
        alert_level="green",
        confidence=100.0,
        sensor_results=[],
        summary="Test",
        recommendations=[],
        limitations=[],
    )
    assert report.regime == "normal"
    assert report.alert_level == "green"


# ---------------------------------------------------------------------------
# Crisis Scoring
# ---------------------------------------------------------------------------


def test_crisis_scoring_import():
    from experts.crisis.logic.scoring import classify_alert_level, classify_regime

    assert callable(classify_alert_level)
    assert callable(classify_regime)


def test_classify_alert_level():
    from experts.crisis.logic.scoring import classify_alert_level

    assert classify_alert_level(10) == "green"
    assert classify_alert_level(40) == "yellow"
    assert classify_alert_level(60) == "red"
    assert classify_alert_level(90) == "black"


def test_classify_regime():
    from experts.crisis.logic.scoring import classify_regime

    regime = classify_regime(20, 10, 5)
    assert regime in ("normal", "overheating", "stress", "crisis")


# ---------------------------------------------------------------------------
# Crisis Normalization
# ---------------------------------------------------------------------------


def test_crisis_normalization_import():
    from experts.crisis.logic.normalization import minmax_score, zscore_to_risk

    assert callable(minmax_score)
    assert callable(zscore_to_risk)


# ---------------------------------------------------------------------------
# Crisis Report
# ---------------------------------------------------------------------------


def test_crisis_report_builder_import():
    from experts.crisis.io.report import build_crisis_summary

    assert callable(build_crisis_summary)


# ---------------------------------------------------------------------------
# Crisis Tool Adapter
# ---------------------------------------------------------------------------


def test_crisis_tool_adapter_import():
    from experts.crisis.adapters.tool_adapter import tool_analyze_systemic_risk

    assert callable(tool_analyze_systemic_risk)


# ---------------------------------------------------------------------------
# Individual Crisis Models (import check)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "model_module,model_class",
    [
        ("experts.crisis.models.bis_credit_gap", "BISCreditGapModel"),
        ("experts.crisis.models.credit_asset_growth", "CreditAssetGrowthModel"),
        ("experts.crisis.models.debt_service_ratio", "DebtServiceRatioModel"),
        ("experts.crisis.models.growth_at_risk", "GrowthAtRiskModel"),
        ("experts.crisis.models.hawkes_stress", "HawkesStressModel"),
        ("experts.crisis.models.imf_mispricing", "IMFMispricingModel"),
        ("experts.crisis.models.lppls_bubble", "LPPLSBubbleModel"),
        ("experts.crisis.models.markov_regime", "MarkovRegimeModel"),
        ("experts.crisis.models.minsky_keen", "MinskyKeenModel"),
        ("experts.crisis.models.network_contagion", "NetworkContagionModel"),
        ("experts.crisis.models.shiller_valuation", "ShillerValuationModel"),
        ("experts.crisis.models.systemic_bank_risk", "SystemicBankRiskModel"),
    ],
)
def test_crisis_model_imports(model_module, model_class):
    """Every crisis model must be importable with its canonical class name."""
    import importlib

    mod = importlib.import_module(model_module)
    cls = getattr(mod, model_class, None)
    assert cls is not None, f"Missing class {model_class} in {model_module}"
