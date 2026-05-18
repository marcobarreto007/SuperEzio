"""Smoke tests — CrisisMath ensemble, scoring, normalization (deterministico, sem rede)."""

import numpy as np
from experts.crisis.contracts.schemas import (
    CrisisInput,
    MacroObservation,
    MarketObservation,
    SensorResult,
    CrisisReport,
)
from experts.crisis.logic.ensemble import aggregate_scores
from experts.crisis.logic.scoring import classify_alert_level, classify_regime
from experts.crisis.logic.normalization import clamp, minmax_score, percentile_rank
from experts.crisis.models.bis_credit_gap import BISCreditGapModel
from experts.crisis.models.markov_regime import MarkovRegimeModel
from experts.crisis.models.shiller_valuation import ShillerValuationModel
from experts.crisis.models.minsky_keen import MinskyKeenModel
from experts.crisis.models.lppls_bubble import (
    LPPLSBubbleModel,
    _second_derivative,
    _zero_crossings,
    _lppls_fit_quality,
)


def _ok_sensor(name, score):
    return SensorResult(
        sensor_name=name,
        score=score,
        confidence=80.0,
        status="ok",
        explanation="test",
    )


class TestSensorResult:
    def test_ok_status(self):
        sr = SensorResult(
            sensor_name="test",
            score=75.0,
            confidence=80.0,
            status="ok",
            explanation="works",
        )
        assert sr.sensor_name == "test"
        assert sr.score == 75.0
        assert sr.status == "ok"

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


class TestCrisisReport:
    def test_minimal(self):
        cr = CrisisReport(
            systemic_risk_score=30.0,
            bubble_risk_score=20.0,
            liquidity_stress_score=10.0,
            credit_fragility_score=15.0,
            final_risk_score=22.0,
            regime="normal",
            alert_level="green",
            confidence=80.0,
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

    def test_single_sensor(self):
        result = aggregate_scores(
            [
                _ok_sensor("BISCreditGapModel", 50.0),
            ]
        )
        # BISCreditGapModel weight=0.20 in systemic_risk
        assert 0 < result["systemic_risk_score"] < 55
        # confidence: 1/8 * 100 = 12.5
        assert result["confidence"] == 12.5

    def test_all_sensors_ok(self):
        sensors = [
            _ok_sensor("BISCreditGapModel", 40.0),
            _ok_sensor("DebtServiceRatioModel", 30.0),
            _ok_sensor("CreditAssetGrowthModel", 50.0),
            _ok_sensor("ShillerValuationModel", 60.0),
            _ok_sensor("IMFMispricingModel", 45.0),
            _ok_sensor("MinskyKeenModel", 55.0),
            _ok_sensor("MarkovRegimeModel", 35.0),
            _ok_sensor("LPPLSBubbleModel", 25.0),
            _ok_sensor("HawkesStressModel", 30.0),
            _ok_sensor("GrowthAtRiskModel", 20.0),
        ]
        result = aggregate_scores(sensors)
        assert result["confidence"] == 100.0  # 10 valid >= 8, capped at 100
        assert 0 <= result["final_risk_score"] <= 100
        assert result["systemic_risk_score"] > 0
        assert result["bubble_risk_score"] > 0
        assert result["credit_fragility_score"] > 0
        assert result["liquidity_stress_score"] > 0

    def test_final_score_weights(self):
        """Final = systemic*0.35 + bubble*0.25 + credit*0.20 + liquidity*0.20"""
        result = aggregate_scores(
            [
                _ok_sensor("BISCreditGapModel", 100.0),
                _ok_sensor("CreditAssetGrowthModel", 0.0),
                _ok_sensor("MarkovRegimeModel", 0.0),
            ]
        )
        # systemic: BIS(0.20) + CreditAsset(0.20) + Markov(0.10) → (100*0.20)/(0.50)=40
        # bubble: CreditAsset only (0.30) → 0/0.30=0
        # credit: BIS only (0.40) → 100*0.40/0.40=100
        # liquidity: Markov only (0.40) → 0/0.40=0
        # final = 40*0.35 + 0*0.25 + 100*0.20 + 0*0.20 = 34.0
        assert result["final_risk_score"] == 34.0

    def test_confidence_capped_at_100(self):
        sensors = [_ok_sensor(f"M{i}", 50.0) for i in range(20)]
        result = aggregate_scores(sensors)
        assert result["confidence"] == 100.0

    def test_error_status_ignored(self):
        sensors = [
            _ok_sensor("BISCreditGapModel", 50.0),
            SensorResult(
                sensor_name="ShillerValuationModel",
                score=0.0,
                confidence=0.0,
                status="error",
                explanation="fail",
            ),
        ]
        result = aggregate_scores(sensors)
        assert result["confidence"] == 12.5  # only 1 valid


class TestClassifyAlertLevel:
    def test_green(self):
        assert classify_alert_level(10.0) == "green"
        assert classify_alert_level(24.9) == "green"

    def test_yellow(self):
        assert classify_alert_level(25.0) == "yellow"
        assert classify_alert_level(49.9) == "yellow"

    def test_red(self):
        assert classify_alert_level(50.0) == "red"
        assert classify_alert_level(74.9) == "red"

    def test_black(self):
        assert classify_alert_level(75.0) == "black"
        assert classify_alert_level(100.0) == "black"


class TestClassifyRegime:
    def test_normal(self):
        assert classify_regime(20.0, 30.0, 30.0) == "normal"

    def test_overheating(self):
        assert classify_regime(50.0, 50.0, 30.0) == "overheating"
        assert classify_regime(30.0, 60.0, 20.0) == "overheating"

    def test_stress(self):
        assert classify_regime(70.0, 50.0, 60.0) == "stress"
        assert classify_regime(40.0, 80.0, 50.0) == "stress"

    def test_crisis(self):
        assert classify_regime(80.0, 20.0, 75.0) == "crisis"
        assert classify_regime(40.0, 40.0, 90.0) == "crisis"


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
            MacroObservation(date=f"2024-{m:02d}", credit_to_gdp=100.0 + m * 5.0)
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

    def test_crisis_regime(self):
        ms = [MarketObservation(date=f"2024-{d:02d}-15", close=100.0) for d in range(1, 10)]
        ms[-1] = MarketObservation(
            date="2024-09-15", close=100.0, realized_volatility=0.35, credit_spread=6.0
        )
        ci = CrisisInput(market_series=ms)
        model = MarkovRegimeModel()
        result = model.evaluate(ci)
        assert result.score == 100.0
        assert "CRISE" in result.explanation

    def test_normal_regime(self):
        ms = [MarketObservation(date=f"2024-{d:02d}-15", close=100.0) for d in range(1, 10)]
        ms[-1] = MarketObservation(
            date="2024-09-15", close=100.0, realized_volatility=0.10, credit_spread=1.0
        )
        ci = CrisisInput(market_series=ms)
        model = MarkovRegimeModel()
        result = model.evaluate(ci)
        assert result.score == 20.0
        assert "NORMAL" in result.explanation

    def test_stress_regime(self):
        ms = [MarketObservation(date=f"2024-{d:02d}-15", close=100.0) for d in range(1, 10)]
        ms[-1] = MarketObservation(
            date="2024-09-15", close=100.0, realized_volatility=0.25, credit_spread=2.0
        )
        ci = CrisisInput(market_series=ms)
        model = MarkovRegimeModel()
        result = model.evaluate(ci)
        assert result.score == 70.0
        assert "STRESS" in result.explanation


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
        assert result.score >= 75  # >= 75th percentile → high score


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


class TestLPPLSBubbleModel:
    def test_insufficient_data(self):
        ci = CrisisInput(
            market_series=[
                MarketObservation(date=f"2024-{d:03d}", close=100.0) for d in range(1, 30)
            ]
        )
        model = LPPLSBubbleModel()
        result = model.evaluate(ci)
        assert result.status == "insufficient_data"

    def test_stable_prices(self):
        """Flat prices → no bubble signal → low score"""
        ms = [MarketObservation(date=f"2024-{d:03d}", close=100.0) for d in range(1, 70)]
        ci = CrisisInput(market_series=ms)
        model = LPPLSBubbleModel()
        result = model.evaluate(ci)
        assert result.status in ("ok", "warning")
        assert result.score <= 0.3  # flat → low bubble score

    def test_stress_signal(self):
        """Slightly trending prices → some signal"""
        ms = [MarketObservation(date=f"2024-{d:03d}", close=100.0 + d * 0.02) for d in range(1, 70)]
        ci = CrisisInput(market_series=ms)
        model = LPPLSBubbleModel()
        result = model.evaluate(ci)
        assert result.status in ("ok", "warning", "stress")
        assert 0.0 <= result.score <= 1.0
        assert 0.0 <= result.confidence <= 1.0


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
