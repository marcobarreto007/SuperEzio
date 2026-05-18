"""Contract tests for F51 Engine — formulas.py + gates.py invariants."""

import pytest
from src.f51.formulas import (
    FormulaWeights,
    DecisionFactors,
    unified_decision,
    combined_risk,
    proxy_reward,
    heuristic_uncertainty,
    decision_threshold,
    expand_budget,
)
from src.f51.gates import VeracityGate, AdversarialCritic, ProxyReward, CriticResult


# ---------------------------------------------------------------------------
# FormulaWeights
# ---------------------------------------------------------------------------


def test_weights_default_values():
    w = FormulaWeights.default()
    assert w.veracity == 2.0
    assert w.consensus == 1.5
    assert w.proxy == 1.0
    assert w.robustness == 0.5
    assert w.uncertainty == 2.0
    assert w.danger == 3.0


def test_weights_are_frozen():
    w = FormulaWeights.default()
    with pytest.raises(Exception):
        w.veracity = 1.0


# ---------------------------------------------------------------------------
# DecisionFactors
# ---------------------------------------------------------------------------


def test_factors_default_all_zero():
    f = DecisionFactors()
    assert f.veracity == 0.0
    assert f.consensus == 0.0
    assert f.proxy_reward == 0.0
    assert f.robustness == 0.0
    assert f.uncertainty == 0.0
    assert f.danger == 0.0


def test_factors_validate_passes_for_valid_range():
    f = DecisionFactors(
        veracity=0.5,
        consensus=0.7,
        proxy_reward=0.3,
        robustness=0.8,
        uncertainty=0.1,
        danger=0.0,
    )
    f.validate()


def test_factors_validate_raises_on_negative():
    f = DecisionFactors(uncertainty=-0.1)
    with pytest.raises(AssertionError):
        f.validate()


def test_factors_validate_raises_on_over_one():
    f = DecisionFactors(danger=1.5)
    with pytest.raises(AssertionError):
        f.validate()


# ---------------------------------------------------------------------------
# unified_decision
# ---------------------------------------------------------------------------


def test_unified_decision_in_range():
    """unified_decision must always return [0, 1]."""
    for v in (0.0, 0.5, 1.0):
        for c in (0.0, 0.5, 1.0):
            f = DecisionFactors(
                veracity=v,
                consensus=c,
                proxy_reward=0.5,
                robustness=0.5,
                uncertainty=0.1,
                danger=0.0,
            )
            result = unified_decision(f)
            assert 0.0 <= result <= 1.0, f"unified_decision({f}) = {result} fora de [0,1]"


def test_unified_decision_high_confidence():
    f = DecisionFactors(
        veracity=1.0,
        consensus=1.0,
        proxy_reward=1.0,
        robustness=1.0,
        uncertainty=0.0,
        danger=0.0,
    )
    result = unified_decision(f)
    assert result > 0.9


def test_unified_decision_low_confidence():
    f = DecisionFactors(
        veracity=0.0,
        consensus=0.0,
        proxy_reward=0.0,
        robustness=0.0,
        uncertainty=1.0,
        danger=1.0,
    )
    result = unified_decision(f)
    assert result < 0.5


def test_unified_decision_sigmoid_identity():
    """sigmoid(0) ≈ 0.5"""
    f = DecisionFactors()
    result = unified_decision(f)
    assert 0.45 < result < 0.55


# ---------------------------------------------------------------------------
# combined_risk
# ---------------------------------------------------------------------------


def test_combined_risk_empty():
    assert combined_risk() == 0.0


def test_combined_risk_gte_max():
    """combined_risk(r1, ..., rn) >= max(r1, ..., rn)"""
    risks = (0.1, 0.3, 0.7)
    c = combined_risk(*risks)
    assert c >= 0.7


def test_combined_risk_in_range():
    c = combined_risk(0.2, 0.5, 0.9)
    assert 0.0 <= c <= 1.0


def test_combined_risk_single():
    assert combined_risk(0.5) >= 0.5


# ---------------------------------------------------------------------------
# proxy_reward
# ---------------------------------------------------------------------------


def test_proxy_reward_cap_without_ground_truth():
    r = proxy_reward(
        consensus=1.0,
        critic=1.0,
        sanity=1.0,
        diversity_penalty=0.0,
        has_ground_truth=False,
    )
    assert r <= 0.9


def test_proxy_reward_cap_with_ground_truth():
    r = proxy_reward(
        consensus=1.0,
        critic=1.0,
        sanity=1.0,
        ground_truth_bonus=1.0,
        has_ground_truth=True,
    )
    assert r <= 1.0


def test_proxy_reward_in_range():
    for c in (0.0, 0.5, 1.0):
        r = proxy_reward(consensus=c, critic=0.5, sanity=0.5)
        assert 0.0 <= r <= 0.9


# ---------------------------------------------------------------------------
# heuristic_uncertainty
# ---------------------------------------------------------------------------


def test_heuristic_uncertainty_baseline():
    u = heuristic_uncertainty()
    assert u == 0.15


def test_heuristic_uncertainty_in_range():
    u = heuristic_uncertainty(
        "prove that for all x",
        {"missing_data_ratio": 0.5, "volatility": 0.6, "data_points": 5},
    )
    assert 0.05 <= u <= 0.95


def test_heuristic_uncertainty_long_text():
    u = heuristic_uncertainty("a" * 900)
    assert u > 0.15


def test_heuristic_uncertainty_clamped():
    u = heuristic_uncertainty("a" * 2000)
    assert u <= 0.95


# ---------------------------------------------------------------------------
# decision_threshold
# ---------------------------------------------------------------------------


def test_decision_threshold_trading():
    assert decision_threshold("trading") == 0.75


def test_decision_threshold_math():
    assert decision_threshold("math") == 0.85


def test_decision_threshold_default():
    assert decision_threshold("default") == 0.70


def test_decision_threshold_unknown_domain():
    assert decision_threshold("nonexistent") == 0.70


# ---------------------------------------------------------------------------
# expand_budget
# ---------------------------------------------------------------------------


def test_expand_budget_below_threshold():
    assert expand_budget(0.5, "trading") is True


def test_expand_budget_above_threshold():
    assert expand_budget(0.9, "default") is False


# ---------------------------------------------------------------------------
# VeracityGate
# ---------------------------------------------------------------------------


def test_veracity_gate_empty_claims():
    gate = VeracityGate()
    result = gate.verify([], {})
    assert result.passed is True
    assert result.confidence == 1.0
    assert result.total == 0


def test_veracity_gate_all_verified():
    gate = VeracityGate()
    claims = [("price", 100.0, "test"), ("volume", 1000.0, "test")]
    truth = {"price": 100.0, "volume": 1000.0}
    result = gate.verify(claims, truth)
    assert result.passed is True
    assert result.verified == 2


def test_veracity_gate_mismatch_lowers_confidence():
    gate = VeracityGate()
    claims = [("price", 200.0, "test"), ("volume", 1000.0, "test")]
    truth = {"price": 100.0, "volume": 1000.0}
    result = gate.verify(claims, truth)
    assert result.confidence < 1.0
    assert len(result.mismatches) == 1


def test_veracity_gate_severe_mismatch():
    gate = VeracityGate()
    claims = [("price", 500.0, "test")]
    truth = {"price": 100.0}
    result = gate.verify(claims, truth)
    assert result.confidence < 0.6


def test_veracity_gate_missing_ground_truth():
    gate = VeracityGate()
    claims = [("missing_key", 100.0, "test")]
    result = gate.verify(claims, {})
    assert result.verified == 0
    assert result.passed is False  # confidence < 0.6


def test_check_decision_consistency_blocks_buy():
    gate = VeracityGate()
    result = gate.check_decision_consistency("buy", "force_wait_or_avoid", "sell")
    assert result.passed is False


def test_check_decision_consistency_allows_sell():
    gate = VeracityGate()
    result = gate.check_decision_consistency("sell", "force_wait_or_avoid", "sell")
    assert result.passed is True


# ---------------------------------------------------------------------------
# AdversarialCritic (rule-based, no LLM)
# ---------------------------------------------------------------------------


def test_critic_rule_based_valid():
    critic = AdversarialCritic()  # no LLM → rule-based
    result = critic.critique("The price is 50 dollars based on current data", "What is the price?")
    assert result.is_valid is True


def test_critic_rule_based_empty_answer():
    critic = AdversarialCritic()
    result = critic.critique("ab", "What is the price?")
    assert result.is_valid is False


def test_critic_evaluate_finance_no_issues():
    critic = AdversarialCritic()
    features = {
        "market_cap": 1_000_000_000,
        "price": 50.0,
        "annual_volatility": 0.2,
        "var_95": -0.329,
        "hype_keyword_count": 0,
        "total_revenue": 10_000_000,
    }
    result = critic.evaluate_finance(features)
    assert result.is_valid is True


def test_critic_evaluate_finance_microcap():
    critic = AdversarialCritic()
    features = {"market_cap": 10_000_000, "price": 50.0}
    result = critic.evaluate_finance(features)
    assert "microcap_preco_alto" in result.errors


def test_critic_evaluate_finance_hype_no_revenue():
    critic = AdversarialCritic()
    features = {"hype_keyword_count": 5, "total_revenue": 100_000}
    result = critic.evaluate_finance(features)
    assert "hype_sem_receita" in result.errors


# ---------------------------------------------------------------------------
# ProxyReward
# ---------------------------------------------------------------------------


def test_proxy_reward_calculate():
    pr = ProxyReward()
    result = pr.calculate(consensus=0.8, sanity_ok=True)
    assert 0.0 <= result <= 0.9


def test_proxy_reward_calculate_with_ground_truth():
    """ProxyReward.calculate with has_ground_truth=True exercises the full formula."""
    pr = ProxyReward()
    critic_result = CriticResult(is_valid=True, confidence=0.9, errors=[])
    result = pr.calculate(
        consensus=0.8,
        critic_result=critic_result,
        sanity_ok=True,
        has_ground_truth=True,
        ground_truth_match=True,
    )
    assert result > 0.5


def test_proxy_reward_calculate_failed_sanity():
    pr = ProxyReward()
    result = pr.calculate(consensus=0.8, sanity_ok=False)
    assert result < 0.5
