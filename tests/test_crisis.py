"""Smoke tests — CrisisMath ensemble, scoring, normalization (deterministico, sem rede)."""

from datetime import date, timedelta

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from experts.crisis.contracts.schemas import (
    CrisisInput,
    CrisisReport,
    MacroObservation,
    MarketObservation,
    SensorResult,
)
from experts.crisis.logic.ensemble import aggregate_scores
from experts.crisis.logic.normalization import clamp, minmax_score, percentile_rank
from experts.crisis.logic.scoring import classify_alert_level, classify_regime
from experts.crisis.models.bis_credit_gap import BISCreditGapModel
from experts.crisis.models.growth_at_risk import (
    GrowthAtRiskModel,
    _pinball_loss,
    _quantile_regression,
)
from experts.crisis.models.hawkes_stress import _fit_exponential_hawkes
from experts.crisis.models.lppls_bubble import (
    LPPLSBubbleModel,
    _lppls_fit_quality,
    _second_derivative,
    _zero_crossings,
)
from experts.crisis.models.markov_regime import (
    MarkovRegimeModel,
    _fit_gaussian_hmm,
    _forward_filter,
)
from experts.crisis.models.minsky_keen import MinskyKeenModel
from experts.crisis.models.network_contagion import NetworkContagionModel
from experts.crisis.models.shiller_valuation import ShillerValuationModel
from experts.crisis.models.systemic_bank_risk import SystemicBankRiskModel


def _month(index: int) -> str:
    year, month_zero_based = divmod(index, 12)
    return f"{2024 + year:04d}-{month_zero_based + 1:02d}"


def _day(index: int) -> str:
    return (date(2024, 1, 1) + timedelta(days=index)).isoformat()


def _ok_sensor(name, score):
    return SensorResult(
        sensor_name=name,
        score=score,
        confidence=0.8,
        status="ok",
        explanation="test",
    )


class TestSensorResult:
    def test_ok_status(self):
        sr = SensorResult(
            sensor_name="test",
            score=0.75,
            confidence=0.8,
            status="ok",
            explanation="works",
        )
        assert sr.sensor_name == "test"
        assert sr.score == 0.75
        assert sr.status == "ok"

    @pytest.mark.parametrize("field", ["score", "confidence"])
    @pytest.mark.parametrize("value", [-0.01, 1.01])
    def test_rejects_values_outside_unit_interval(self, field, value):
        payload = {
            "sensor_name": "invalid",
            "score": 0.5,
            "confidence": 0.5,
            "status": "ok",
            "explanation": "invalid bounds",
        }
        payload[field] = value
        with pytest.raises(ValidationError):
            SensorResult(**payload)

    def test_error_status(self):
        sr = SensorResult(
            sensor_name="fail",
            score=0.0,
            confidence=0.0,
            status="insufficient_data",
            explanation="no data",
        )
        assert sr.status == "insufficient_data"


class TestCrisisInput:
    def test_empty_input(self):
        ci = CrisisInput(country="US")
        assert ci.country == "US"
        assert ci.observations == []
        assert ci.frequency == "monthly"

    def test_with_observations(self):
        obs = [MacroObservation(date="2024-01", credit_to_gdp=180.0)]
        ci = CrisisInput(country="BR", observations=obs)
        assert len(ci.observations) == 1
        assert ci.observations[0].credit_to_gdp == 180.0

    def test_market_series(self):
        ms = [MarketObservation(date="2024-01-15", close=100.0, realized_volatility=0.15)]
        ci = CrisisInput(market_series=ms)
        assert ci.market_series[0].close == 100.0

    @pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
    def test_rejects_non_finite_values(self, value):
        with pytest.raises(ValidationError):
            MarketObservation(date="2024-01-01", close=value)

    def test_rejects_invalid_dates_and_frequency(self):
        with pytest.raises(ValidationError):
            MacroObservation(date="t0", gdp_growth_yoy=0.01)
        with pytest.raises(ValidationError):
            CrisisInput(frequency="sometimes")

    def test_rejects_non_monotonic_series(self):
        observations = [
            MacroObservation(date="2024-02", gdp_growth_yoy=0.01),
            MacroObservation(date="2024-01", gdp_growth_yoy=0.02),
        ]
        with pytest.raises(ValidationError):
            CrisisInput(observations=observations)


class TestCrisisReport:
    def test_minimal(self):
        cr = CrisisReport(
            systemic_risk_score=0.30,
            bubble_risk_score=0.20,
            liquidity_stress_score=0.10,
            credit_fragility_score=0.15,
            final_risk_score=0.22,
            regime="normal",
            alert_level="green",
            confidence=0.80,
            summary="OK",
        )
        assert cr.alert_level == "green"
        assert cr.regime == "normal"


class TestAggregateScores:
    def test_empty(self):
        result = aggregate_scores([])
        assert result["systemic_risk_score"] == 0.0
        assert result["final_risk_score"] == 0.0
        assert result["confidence"] == 0.0
        assert result["status"] == "unavailable"

    def test_single_sensor(self):
        result = aggregate_scores(
            [
                _ok_sensor("BISCreditGapModel", 0.50),
            ]
        )
        # BISCreditGapModel weight=0.20 in systemic_risk
        assert 0 < result["systemic_risk_score"] < 0.55
        assert result["confidence"] == pytest.approx(0.8 / 12)

    def test_high_severity_is_still_operationally_valid(self):
        from experts.crisis.models import BaseCrisisModel

        sensor = BaseCrisisModel._result("HighRisk", 0.90, 0.80, "high risk")
        assert sensor.status == "ok"
        assert sensor.severity == "crisis"

    def test_all_sensors_ok(self):
        sensors = [
            _ok_sensor("BISCreditGapModel", 0.40),
            _ok_sensor("DebtServiceRatioModel", 0.30),
            _ok_sensor("CreditAssetGrowthModel", 0.50),
            _ok_sensor("ShillerValuationModel", 0.60),
            _ok_sensor("IMFMispricingModel", 0.45),
            _ok_sensor("MinskyKeenModel", 0.55),
            _ok_sensor("MarkovRegimeModel", 0.35),
            _ok_sensor("LPPLSBubbleModel", 0.25),
            _ok_sensor("HawkesStressModel", 0.30),
            _ok_sensor("GrowthAtRiskModel", 0.20),
        ]
        result = aggregate_scores(sensors)
        assert result["confidence"] == pytest.approx(0.8 * 10 / 12)
        assert 0 <= result["final_risk_score"] <= 1
        assert result["systemic_risk_score"] > 0
        assert result["bubble_risk_score"] > 0
        assert result["credit_fragility_score"] > 0
        assert result["liquidity_stress_score"] > 0

    def test_final_score_weights(self):
        """Final = systemic*0.35 + bubble*0.25 + credit*0.20 + liquidity*0.20"""
        result = aggregate_scores(
            [
                _ok_sensor("BISCreditGapModel", 1.0),
                _ok_sensor("CreditAssetGrowthModel", 0.0),
                _ok_sensor("MarkovRegimeModel", 0.0),
            ]
        )
        # systemic: BIS(.20) + CreditAsset(.20) + Markov(.10) → (1*.20)/(.50)=.40
        # bubble: CreditAsset only (0.30) → 0/0.30=0
        # credit: BIS only (0.40) → 1*0.40/0.40=1
        # liquidity: Markov only (0.40) → 0/0.40=0
        # final = .40*.35 + 0*.25 + 1*.20 + 0*.20 = .34
        assert result["final_risk_score"] == pytest.approx(0.34)

    def test_confidence_capped_at_one(self):
        sensors = [_ok_sensor(f"M{i}", 0.50) for i in range(20)]
        result = aggregate_scores(sensors)
        assert result["confidence"] == pytest.approx(0.8)

    def test_error_status_ignored(self):
        sensors = [
            _ok_sensor("BISCreditGapModel", 0.50),
            SensorResult(
                sensor_name="ShillerValuationModel",
                score=0.0,
                confidence=0.0,
                status="error",
                explanation="fail",
            ),
        ]
        result = aggregate_scores(sensors)
        assert result["confidence"] == pytest.approx(0.8 / 12)


class TestClassifyAlertLevel:
    def test_green(self):
        assert classify_alert_level(0.10) == "green"
        assert classify_alert_level(0.249) == "green"

    def test_yellow(self):
        assert classify_alert_level(0.25) == "yellow"
        assert classify_alert_level(0.499) == "yellow"

    def test_red(self):
        assert classify_alert_level(0.50) == "red"
        assert classify_alert_level(0.749) == "red"

    def test_black(self):
        assert classify_alert_level(0.75) == "black"
        assert classify_alert_level(1.0) == "black"

    @given(st.floats(min_value=0.0, max_value=1.0, allow_nan=False))
    @settings(max_examples=1000)
    def test_always_returns_known_level(self, score):
        assert classify_alert_level(score) in {"green", "yellow", "red", "black"}


class TestClassifyRegime:
    def test_normal(self):
        assert classify_regime(0.20, 0.30, 0.30) == "normal"

    def test_overheating(self):
        assert classify_regime(0.50, 0.50, 0.30) == "overheating"
        assert classify_regime(0.30, 0.60, 0.20) == "overheating"

    def test_stress(self):
        assert classify_regime(0.70, 0.50, 0.60) == "stress"
        assert classify_regime(0.40, 0.80, 0.50) == "stress"

    def test_crisis(self):
        assert classify_regime(0.80, 0.20, 0.75) == "crisis"
        assert classify_regime(0.40, 0.40, 0.90) == "crisis"


def test_crisis_expert_classifies_high_normalized_ensemble_as_crisis():
    from experts.crisis.contracts.schemas import CrisisInput
    from experts.crisis.expert.crisis_expert import CrisisMathExpert

    sensor_names = (
        "BISCreditGapModel",
        "DebtServiceRatioModel",
        "CreditAssetGrowthModel",
        "ShillerValuationModel",
        "IMFMispricingModel",
        "MarkovRegimeModel",
        "MinskyKeenModel",
        "GrowthAtRiskModel",
        "LPPLSBubbleModel",
        "HawkesStressModel",
    )

    def make_sensor(name):
        return type(
            name,
            (),
            {
                "evaluate": lambda self, data: SensorResult(
                    sensor_name=name,
                    score=0.90,
                    confidence=0.90,
                    status="ok",
                    explanation="synthetic high risk",
                )
            },
        )()

    expert = CrisisMathExpert(fraud_patterns=object())
    expert.sensors = [make_sensor(name) for name in sensor_names]
    report = expert.analyze(CrisisInput())

    assert report.alert_level == "black"
    assert report.regime == "crisis"
    assert report.final_risk_score == pytest.approx(0.90)


class TestNormalization:
    def test_clamp_default(self):
        assert clamp(50.0) == 50.0
        assert clamp(-10.0) == 0.0
        assert clamp(150.0) == 100.0

    def test_clamp_custom(self):
        assert clamp(25.0, 0.0, 50.0) == 25.0
        assert clamp(100.0, 0.0, 50.0) == 50.0

    def test_minmax_score(self):
        result = minmax_score(50.0, 0.0, 100.0)
        assert result == 50.0

    def test_minmax_score_invert(self):
        result = minmax_score(50.0, 0.0, 100.0, invert=True)
        assert result == 50.0

    def test_minmax_score_bounds(self):
        assert minmax_score(0.0, 0.0, 100.0) == 0.0
        assert minmax_score(100.0, 0.0, 100.0) == 100.0

    def test_minmax_score_equal_bounds(self):
        assert minmax_score(50.0, 10.0, 10.0) == 100.0

    def test_percentile_rank_empty(self):
        assert percentile_rank([], 5.0) == 50.0

    def test_percentile_rank_basic(self):
        result = percentile_rank([1, 2, 3, 4, 5], 3)
        assert 0.0 <= result <= 100.0


class TestBISCreditGapModel:
    def test_insufficient_data(self):
        ci = CrisisInput(
            observations=[
                MacroObservation(date="2024-01", credit_to_gdp=180.0),
            ]
        )
        model = BISCreditGapModel()
        result = model.evaluate(ci)
        assert result.status == "insufficient_data"
        assert result.score == 0.0

    def test_low_gap(self):
        """12 obs with flat credit_to_gdp → gap ~0 → low score"""
        obs = [MacroObservation(date=f"2024-{m:02d}", credit_to_gdp=180.0) for m in range(1, 13)]
        ci = CrisisInput(observations=obs)
        model = BISCreditGapModel()
        result = model.evaluate(ci)
        assert result.status == "ok"
        assert result.score <= 25.0  # gap ~0

    def test_rising_gap(self):
        """Rising credit/gdp → positive gap → higher score"""
        obs = [
            MacroObservation(date=_month(m - 1), credit_to_gdp=100.0 + m * 5.0)
            for m in range(1, 25)
        ]
        ci = CrisisInput(observations=obs)
        model = BISCreditGapModel()
        result = model.evaluate(ci)
        assert result.status == "ok"
        assert "current_gap" in result.details


class TestMarkovRegimeModel:
    def test_insufficient_data(self):
        ci = CrisisInput(
            market_series=[
                MarketObservation(date="2024-01-15", close=100.0),
            ]
        )
        model = MarkovRegimeModel()
        result = model.evaluate(ci)
        assert result.status == "insufficient_data"

    def test_synthetic_stress_regime(self):
        rng = np.random.default_rng(51)
        returns = np.concatenate([rng.normal(0.0005, 0.003, 180), rng.normal(-0.004, 0.035, 60)])
        closes = 100.0 * np.exp(np.r_[0.0, np.cumsum(returns)])
        market = [
            MarketObservation(date=_day(index), close=float(close))
            for index, close in enumerate(closes)
        ]
        result = MarkovRegimeModel().evaluate(CrisisInput(frequency="daily", market_series=market))
        assert result.status == "ok"
        assert result.method_kind == "statistical_model"
        assert result.details["posterior_kind"] == "filtered_causal"
        assert result.details["converged"] is True
        assert result.score > 0.65

    def test_forward_filter_is_causal_for_fixed_parameters(self):
        rng = np.random.default_rng(7)
        values = np.r_[rng.normal(0.0, 0.004, 100), rng.normal(0.0, 0.03, 80)]
        fit = _fit_gaussian_hmm(values)
        cutoff = 120
        prefix, _, _ = _forward_filter(
            values[:cutoff], fit.means, fit.variances, fit.transition, fit.initial
        )
        full, _, _ = _forward_filter(values, fit.means, fit.variances, fit.transition, fit.initial)
        assert np.allclose(prefix[-1], full[cutoff - 1], atol=1e-12)

    def test_constant_series_is_not_called_normal(self):
        market = [MarketObservation(date=_day(i), close=100.0) for i in range(80)]
        result = MarkovRegimeModel().evaluate(CrisisInput(frequency="daily", market_series=market))
        assert result.status == "insufficient_data"
        assert result.confidence == 0.0


class TestShillerValuationModel:
    def test_insufficient_data(self):
        ci = CrisisInput(
            observations=[
                MacroObservation(
                    date="2024-01",
                    house_price_index=100.0,
                    rent_index=50.0,
                    income_index=80.0,
                ),
            ]
        )
        model = ShillerValuationModel()
        result = model.evaluate(ci)
        assert result.status == "insufficient_data"

    def test_stable_valuation(self):
        obs = [
            MacroObservation(
                date=f"2024-{m:02d}",
                house_price_index=100.0,
                rent_index=50.0,
                income_index=80.0,
            )
            for m in range(1, 13)
        ]
        ci = CrisisInput(observations=obs)
        model = ShillerValuationModel()
        result = model.evaluate(ci)
        assert result.status == "ok"
        assert result.score >= 0
        assert "price_to_rent_pct" in result.details

    def test_extreme_valuation(self):
        """Last obs has much higher house price relative to rent/income"""
        obs = [
            MacroObservation(
                date=f"2024-{m:02d}",
                house_price_index=100.0,
                rent_index=50.0,
                income_index=80.0,
            )
            for m in range(1, 12)
        ]
        obs.append(
            MacroObservation(
                date="2024-12",
                house_price_index=300.0,
                rent_index=50.0,
                income_index=80.0,
            )
        )
        ci = CrisisInput(observations=obs)
        model = ShillerValuationModel()
        result = model.evaluate(ci)
        assert result.status == "ok"
        # score is 0-1 (was 0-100); details still expose the raw 0-100
        # percentile for readability.
        assert result.score >= 0.75  # >= 75th percentile → high score


class TestMinskyKeenModel:
    def test_insufficient_data(self):
        ci = CrisisInput(
            observations=[
                MacroObservation(
                    date="2024-01",
                    credit_to_gdp=180.0,
                    gdp_growth_yoy=2.0,
                    policy_rate=5.0,
                ),
            ]
        )
        model = MinskyKeenModel()
        result = model.evaluate(ci)
        assert result.status == "insufficient_data"

    def test_hedge_like(self):
        obs = [
            MacroObservation(
                date=f"2024-{m:02d}",
                credit_to_gdp=100.0,
                gdp_growth_yoy=4.0,
                policy_rate=1.0,
            )
            for m in range(1, 6)
        ]
        ci = CrisisInput(observations=obs)
        model = MinskyKeenModel()
        result = model.evaluate(ci)
        assert result.status == "ok"
        assert "Hedge" in result.details["minsky_state"]

    def test_ponzi_like(self):
        obs = [
            MacroObservation(
                date=f"2024-{m:02d}",
                credit_to_gdp=100.0,
                gdp_growth_yoy=4.0,
                policy_rate=1.0,
            )
            for m in range(1, 5)
        ]
        obs.append(
            MacroObservation(
                date="2024-05",
                credit_to_gdp=250.0,
                gdp_growth_yoy=-1.0,
                policy_rate=10.0,
            )
        )
        ci = CrisisInput(observations=obs)
        model = MinskyKeenModel()
        result = model.evaluate(ci)
        assert result.status == "ok"
        assert "Ponzi" in result.details["minsky_state"]


class TestHawkesStressModel:
    def test_clustered_events_outscore_regular_poisson_events(self):
        regular = np.linspace(5.0, 195.0, 40)
        clustered = np.concatenate(
            [base + np.arange(8, dtype=float) * 0.2 for base in (20, 60, 100, 140, 180)]
        )
        poisson_like = _fit_exponential_hawkes(regular, horizon=220.0)
        self_exciting = _fit_exponential_hawkes(clustered, horizon=220.0)

        assert poisson_like.branching_ratio < 0.05
        assert self_exciting.branching_ratio > 0.60
        assert self_exciting.log_likelihood > self_exciting.poisson_log_likelihood
        assert self_exciting.alpha / self_exciting.beta < 1.0


class TestGrowthAtRiskModel:
    def test_intercept_only_quantile_is_the_sample_median(self):
        design = np.ones((5, 1), dtype=float)
        target = np.array([5.0, 1.0, 4.0, 2.0, 3.0])
        beta = _quantile_regression(design, target, q=0.5)
        prediction = np.full_like(target, beta[0])

        assert beta[0] == pytest.approx(3.0)
        assert _pinball_loss(target, prediction, 0.5) == pytest.approx(0.6)

    def test_reports_rolling_pinball_validation(self):
        observations = []
        for index in range(42):
            debt_service = 8.0 + 0.15 * index + 0.8 * np.sin(index / 3.0)
            gdp_growth = 0.035 - 0.0035 * debt_service + 0.002 * np.cos(index)
            observations.append(
                MacroObservation(
                    date=_month(index),
                    credit_to_gdp=100.0 + 1.3 * index,
                    debt_service_ratio=debt_service,
                    house_price_index=100.0 + 0.7 * index + np.sin(index / 2.0),
                    gdp_growth_yoy=gdp_growth,
                )
            )
        result = GrowthAtRiskModel().evaluate(
            CrisisInput(frequency="monthly", observations=observations)
        )

        assert result.status == "ok"
        assert result.calibration_status == "rolling_validated"
        assert result.details["rolling_folds"] >= 8
        assert result.details["pinball_loss"] >= 0.0


class TestUnavailableSystemicModels:
    def test_covar_and_debtrank_require_real_network_data(self):
        market = [MarketObservation(date=_day(index), close=100.0 + index) for index in range(120)]
        result = NetworkContagionModel().evaluate(
            CrisisInput(frequency="daily", market_series=market)
        )
        assert result.status == "insufficient_data"
        assert result.method_kind == "unavailable"
        assert "bilateral exposure matrix" in result.explanation

    def test_srisk_requires_bank_level_balance_sheets(self):
        observations = [
            MacroObservation(
                date=_month(index),
                equity_index=100.0 + index,
                credit_to_gdp=120.0 + index,
            )
            for index in range(36)
        ]
        result = SystemicBankRiskModel().evaluate(CrisisInput(observations=observations))
        assert result.status == "insufficient_data"
        assert result.method_kind == "unavailable"
        assert "bank-level equity returns" in result.explanation


class TestLPPLSBubbleModel:
    def test_insufficient_data(self):
        ci = CrisisInput(
            market_series=[MarketObservation(date=_day(d), close=100.0) for d in range(1, 30)]
        )
        model = LPPLSBubbleModel()
        result = model.evaluate(ci)
        assert result.status == "insufficient_data"

    def test_stable_prices(self):
        """A constant series cannot calibrate LPPLS and must remain unavailable."""
        ms = [MarketObservation(date=_day(d), close=100.0) for d in range(1, 130)]
        ci = CrisisInput(market_series=ms)
        model = LPPLSBubbleModel()
        result = model.evaluate(ci)
        assert result.status == "insufficient_data"
        assert result.score == 0.0

    def test_stress_signal(self):
        """Slightly trending prices → some signal"""
        ms = [MarketObservation(date=_day(d), close=100.0 + d * 0.02) for d in range(1, 130)]
        ci = CrisisInput(market_series=ms)
        model = LPPLSBubbleModel()
        result = model.evaluate(ci)
        assert result.status == "ok"
        assert 0.0 <= result.score <= 1.0
        assert 0.0 <= result.confidence <= 1.0

    def test_smooth_exponential_is_not_an_lppls_bubble(self):
        market = [
            MarketObservation(date=_day(index), close=float(100.0 * np.exp(0.003 * index)))
            for index in range(180)
        ]
        result = LPPLSBubbleModel().evaluate(CrisisInput(frequency="daily", market_series=market))

        assert result.status == "ok"
        assert result.score <= 0.20
        assert result.details["confirmed"] is False
        assert result.details["accepted_windows"] < 2


class TestLPPLSHelpers:
    def test_second_derivative_flat(self):
        y = np.array([1.0, 1.0, 1.0, 1.0, 1.0])
        d2 = _second_derivative(y)
        assert np.allclose(d2, 0.0)

    def test_second_derivative_parabola(self):
        y = np.array([1.0, 4.0, 9.0, 16.0, 25.0])  # x^2
        d2 = _second_derivative(y)
        assert np.allclose(d2, 2.0)

    def test_second_derivative_short(self):
        d2 = _second_derivative(np.array([1.0, 2.0]))
        assert len(d2) == 2
        assert d2[0] == 0.0

    def test_zero_crossings_none(self):
        y = np.array([1.0, 2.0, 3.0, 4.0])
        assert _zero_crossings(y) == 0

    def test_zero_crossings_many(self):
        y = np.array([1.0, -1.0, 1.0, -1.0, 1.0])
        assert _zero_crossings(y) == 4

    def test_lppls_fit_quality_constant(self):
        """Constant log-prices have undefined R² and must not look like a bubble."""
        log_prices = np.array([1.0] * 20)
        t = np.arange(20, dtype=float)
        r2 = _lppls_fit_quality(log_prices, t, tc=25.0, m=0.5, omega=6.0)
        assert r2 == 0.0

    def test_lppls_fit_quality_trending(self):
        log_prices = np.log(100.0 + np.arange(20) * 0.5)
        t = np.arange(20, dtype=float)
        r2 = _lppls_fit_quality(log_prices, t, tc=25.0, m=0.5, omega=6.0)
        assert -1.0 <= r2 <= 1.0  # some fit quality
