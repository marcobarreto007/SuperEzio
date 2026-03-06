"""Smoke tests — F51 formulas (puras, deterministicas, sem rede)."""

import pytest
from f51.formulas import (
    DecisionFactors,
    FormulaWeights,
    unified_decision,
    combined_risk,
    proxy_reward,
    heuristic_uncertainty,
    decision_threshold,
    expand_budget,
)


class TestDecisionFactors:
    def test_valid(self):
        df = DecisionFactors(
            veracity=0.8,
            consensus=0.7,
            proxy_reward=0.6,
            robustness=0.5,
            uncertainty=0.4,
            danger=0.3,
        )
        df.validate()  # nao deve levantar

    def test_invalid_low(self):
        df = DecisionFactors(veracity=-0.1)
        with pytest.raises(AssertionError):
            df.validate()

    def test_invalid_high(self):
        df = DecisionFactors(consensus=1.5)
        with pytest.raises(AssertionError):
            df.validate()


class TestFormulaWeights:
    def test_default(self):
        w = FormulaWeights.default()
        # Weights are multipliers, can exceed 1.0
        assert w.veracity >= 0
        assert w.consensus >= 0
        assert w.danger >= 0

    def test_all_fields_present(self):
        w = FormulaWeights.default()
        for attr in (
            "veracity",
            "consensus",
            "proxy",
            "robustness",
            "uncertainty",
            "danger",
        ):
            assert hasattr(w, attr), f"missing field: {attr}"


class TestUnifiedDecision:
    def test_range(self):
        factors = DecisionFactors(0.5, 0.5, 0.5, 0.5, 0.5, 0.5)
        result = unified_decision(factors, FormulaWeights.default())
        assert 0.0 <= result <= 1.0

    def test_all_zeros(self):
        factors = DecisionFactors(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        result = unified_decision(factors, FormulaWeights.default())
        # sigmoid(0) == 0.5
        assert result == 0.5

    def test_all_ones(self):
        factors = DecisionFactors(1.0, 1.0, 1.0, 1.0, 1.0, 0.0)
        result = unified_decision(factors, FormulaWeights.default())
        assert result > 0.5

    def test_custom_weights(self):
        factors = DecisionFactors(1.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        w = FormulaWeights(
            veracity=1.0,
            consensus=0.0,
            proxy=0.0,
            robustness=0.0,
            uncertainty=0.0,
            danger=0.0,
        )
        result = unified_decision(factors, w)
        assert result > 0.5


class TestCombinedRisk:
    def test_empty(self):
        assert combined_risk() == 0.0

    def test_single(self):
        assert combined_risk(0.5) == 0.5

    def test_multiple(self):
        r = combined_risk(0.3, 0.3, 0.3)
        assert r > 0.3  # t-conorm cresce com multiplos riscos

    def test_monotonic(self):
        r1 = combined_risk(0.2, 0.2)
        r2 = combined_risk(0.5, 0.5)
        assert r2 > r1


class TestProxyReward:
    def test_no_ground_truth(self):
        r = proxy_reward(
            consensus=0.8,
            critic=0.7,
            sanity=0.9,
            diversity_penalty=0.1,
            ground_truth_bonus=0.0,
            has_ground_truth=False,
        )
        assert r <= 0.9

    def test_with_ground_truth(self):
        r = proxy_reward(
            consensus=0.8,
            critic=0.7,
            sanity=0.9,
            diversity_penalty=0.1,
            ground_truth_bonus=0.1,
            has_ground_truth=True,
        )
        assert r <= 1.0

    def test_range(self):
        r = proxy_reward(0.5, 0.5, 0.5, 0.0, 0.0, False)
        assert 0.0 <= r <= 1.0


class TestHeuristicUncertainty:
    def test_short_text(self):
        u = heuristic_uncertainty("hello world", {})
        assert 0.05 <= u <= 0.95

    def test_long_text(self):
        u = heuristic_uncertainty("x " * 2000, {})
        assert u > 0.05  # texto longo aumenta incerteza

    def test_empty(self):
        u = heuristic_uncertainty("", {})
        assert 0.05 <= u <= 0.95

    def test_math_keywords(self):
        u = heuristic_uncertainty(
            "calculate the variance and standard deviation of this time series",
            {},
        )
        assert 0.05 <= u <= 0.95

    def test_numeric_features(self):
        u = heuristic_uncertainty("test", {"price": -999, "volume": 0})
        assert 0.05 <= u <= 0.95


class TestDecisionThreshold:
    def test_known_domains(self):
        assert decision_threshold("trading") == 0.75
        assert decision_threshold("math") == 0.85
        assert decision_threshold("code_review") == 0.80
        assert decision_threshold("contract") == 0.85

    def test_unknown_domain(self):
        # Falls back to default
        assert decision_threshold("nonexistent") == 0.70

    def test_default(self):
        assert decision_threshold("default") == 0.70


class TestExpandBudget:
    def test_high_confidence(self):
        assert expand_budget(confidence=0.9, domain="math") is False

    def test_low_confidence(self):
        assert expand_budget(confidence=0.5, domain="math") is True
