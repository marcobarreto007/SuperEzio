"""Component tests: CrisisMath (12 models + ensemble + scoring + normalization)."""


# ── Normalization ──
def test_clamp():
    from experts.crisis.logic.normalization import clamp

    assert clamp(50, 0, 100) == 50
    assert clamp(150, 0, 100) == 100
    assert clamp(-10, 0, 100) == 0


def test_percentile_rank():
    from experts.crisis.logic.normalization import percentile_rank

    r = percentile_rank([10, 20, 30, 40, 50], 35)
    assert 0 <= r <= 100


def test_minmax_score():
    from experts.crisis.logic.normalization import minmax_score

    s = minmax_score(30, 10, 50)
    assert 0 <= s <= 100


# ── Scoring ──
def test_classify_alert_level():
    from experts.crisis.logic.scoring import classify_alert_level

    assert classify_alert_level(15) == "green"
    assert classify_alert_level(40) == "yellow"
    assert classify_alert_level(65) == "red"
    assert classify_alert_level(85) == "black"


def test_classify_regime():
    from experts.crisis.logic.scoring import classify_regime

    r = classify_regime(score=30, bubble_score=10, stress_score=20)
    assert r in ("normal", "overheating", "stress", "crisis")


# ── Ensemble ──
def test_aggregate_scores():
    from experts.crisis.logic.ensemble import aggregate_scores
    from experts.crisis.contracts.schemas import SensorResult

    results = [
        SensorResult(
            sensor_name="TestModel",
            score=45.0,
            confidence=0.8,
            status="ok",
            explanation="test",
        ),
    ]
    agg = aggregate_scores(results)
    assert isinstance(agg, dict)
    assert "final_risk_score" in agg


def test_aggregate_scores_empty():
    from experts.crisis.logic.ensemble import aggregate_scores

    agg = aggregate_scores([])
    assert agg["final_risk_score"] == 0.0


# ── Schemas ──
def test_crisis_input():
    from experts.crisis.contracts.schemas import CrisisInput, MacroObservation

    obs = MacroObservation(
        date="2024-01-01",
        credit_to_gdp=160.0,
        policy_rate=5.0,
        gdp_growth_yoy=1.5,
        inflation_yoy=3.2,
        unemployment_rate=6.0,
        debt_service_ratio=14.5,
    )
    inp = CrisisInput(country="CA", observations=[obs])
    assert inp.country == "CA"


def test_sensor_result():
    from experts.crisis.contracts.schemas import SensorResult

    sr = SensorResult(
        sensor_name="test_model",
        score=45.0,
        confidence=0.8,
        status="ok",
        explanation="test",
    )
    assert sr.sensor_name == "test_model"
    assert sr.score == 45.0


# ── Helper: builds CrisisInput with 24 monthly observations ──
def _make_crisis_input(**kw):
    from experts.crisis.contracts.schemas import CrisisInput, MacroObservation

    defaults = dict(
        credit_to_gdp=160.0,
        policy_rate=5.0,
        gdp_growth_yoy=1.5,
        inflation_yoy=3.2,
        unemployment_rate=6.0,
        debt_service_ratio=14.5,
        credit_growth_yoy=4.0,
        house_price_index=120.0,
    )
    defaults.update(kw)
    # 24 months of data (models like BIS need ≥12)
    obs_list = []
    for i in range(24):
        obs_dict = dict(defaults)
        obs_dict["date"] = f"2024-{(i % 12) + 1:02d}-01"
        obs_list.append(MacroObservation(**obs_dict))
    return CrisisInput(country="CA", observations=obs_list)


# ── 12 Models (instantiation + basic scoring) ──
MODEL_SPECS = [
    ("bis_credit_gap", "BISCreditGapModel"),
    ("debt_service_ratio", "DebtServiceRatioModel"),
    ("shiller_valuation", "ShillerValuationModel"),
    ("markov_regime", "MarkovRegimeModel"),
    ("hawkes_stress", "HawkesStressModel"),
    ("lppls_bubble", "LPPLSBubbleModel"),
    ("minsky_keen", "MinskyKeenModel"),
    ("credit_asset_growth", "CreditAssetGrowthModel"),
    ("growth_at_risk", "GrowthAtRiskModel"),
    ("imf_mispricing", "IMFMispricingModel"),
    ("network_contagion", "NetworkContagionModel"),
    ("systemic_bank_risk", "SystemicBankRiskModel"),
]


def _test_model(model_attr, class_name):
    import importlib

    mod = importlib.import_module(f"experts.crisis.models.{model_attr}")
    cls = getattr(mod, class_name)
    instance = cls()
    inp = _make_crisis_input()
    result = instance.evaluate(inp)
    assert result is not None, f"{class_name}.evaluate() returned None"
    assert result.sensor_name == class_name
    assert 0 <= result.score <= 100, f"{class_name} score {result.score} out of range"
    return result


def test_bis_credit_gap():
    _test_model("bis_credit_gap", "BISCreditGapModel")


def test_debt_service_ratio():
    _test_model("debt_service_ratio", "DebtServiceRatioModel")


def test_shiller_valuation():
    _test_model("shiller_valuation", "ShillerValuationModel")


def test_markov_regime():
    _test_model("markov_regime", "MarkovRegimeModel")


def test_hawkes_stress():
    _test_model("hawkes_stress", "HawkesStressModel")


def test_lppls_bubble():
    _test_model("lppls_bubble", "LPPLSBubbleModel")


def test_minsky_keen():
    _test_model("minsky_keen", "MinskyKeenModel")


def test_credit_asset_growth():
    _test_model("credit_asset_growth", "CreditAssetGrowthModel")


def test_growth_at_risk():
    _test_model("growth_at_risk", "GrowthAtRiskModel")


def test_imf_mispricing():
    _test_model("imf_mispricing", "IMFMispricingModel")


def test_network_contagion():
    _test_model("network_contagion", "NetworkContagionModel")


def test_systemic_bank_risk():
    _test_model("systemic_bank_risk", "SystemicBankRiskModel")


# ── Crisis Expert ──
def test_crisis_expert_analyze():
    from experts.crisis.expert.crisis_expert import CrisisMathExpert
    from experts.crisis.contracts.schemas import CrisisInput, MacroObservation

    expert = CrisisMathExpert()
    obs = MacroObservation(
        date="2024-06-01",
        credit_to_gdp=160.0,
        policy_rate=5.0,
        gdp_growth_yoy=1.5,
        inflation_yoy=3.2,
        unemployment_rate=6.0,
        debt_service_ratio=14.5,
    )
    inp = CrisisInput(country="CA", observations=[obs], asset_symbol="TEST")
    result = expert.analyze(inp)
    assert hasattr(result, "regime")
    assert hasattr(result, "alert_level")
    assert result.regime in ("normal", "overheating", "stress", "crisis")


# ── Core Math Crisis ──
def test_crisis_evaluate():
    from core.math.crisis import crisis_evaluate

    data = {
        "observations": [
            {
                "date": "2024-06-01",
                "credit_to_gdp": 160.0,
                "policy_rate": 5.0,
                "gdp_growth_yoy": 1.5,
                "inflation_yoy": 3.2,
                "unemployment_rate": 6.0,
                "debt_service_ratio": 14.5,
            }
        ],
        "country": "CA",
    }
    result = crisis_evaluate("bis_credit_gap", data)
    assert isinstance(result, dict)
    assert "score" in result


def test_crisis_aggregate():
    from core.math.crisis import crisis_aggregate

    data = {
        "observations": [
            {
                "date": "2024-06-01",
                "credit_to_gdp": 160.0,
                "policy_rate": 5.0,
                "gdp_growth_yoy": 1.5,
                "inflation_yoy": 3.2,
                "unemployment_rate": 6.0,
                "debt_service_ratio": 14.5,
            }
        ],
        "country": "CA",
    }
    result = crisis_aggregate(data, models=["bis_credit_gap", "minsky_keen", "hawkes_stress"])
    assert isinstance(result, dict)
    assert "aggregate_score" in result


def test_crisis_classify():
    from core.math.crisis import crisis_classify

    assert crisis_classify(0.15) == "green"
    assert crisis_classify(0.85) == "black"


print("CrisisMath: ALL TESTS PASSED")
