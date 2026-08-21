"""Unit tests for the SuperEzio Investor Portfolio Allocator."""

import pytest
from scripts.investor_portfolio_allocator import calculate_allocation


def test_emergency_reserve_prioritization():
    # Capital of 10,000 with 3,000 monthly expenses and 4 months target needs 12,000 -> full 10,000 goes to emergency reserve
    plan = calculate_allocation(
        total_capital=10000.0,
        monthly_expenses=3000.0,
        emergency_months=4.0,
    )
    assert plan.emergency_reserve == 10000.0
    assert plan.investable_surplus == 0.0
    assert plan.core_allocation == 0.0
    assert plan.explore_allocation == 0.0


def test_high_interest_debt_payoff():
    # Capital of 25,000, 3,500 expenses x 4 months = 14,000 emergency reserve.
    # 5,000 debt at 19.99% -> gets paid off in full (5,000).
    # Remaining investable surplus = 25,000 - 14,000 - 5,000 = 6,000.
    plan = calculate_allocation(
        total_capital=25000.0,
        monthly_expenses=3500.0,
        emergency_months=4.0,
        debt_balance=5000.0,
        debt_interest_rate=19.99,
        risk_tolerance="moderate",
    )
    assert plan.emergency_reserve == 14000.0
    assert plan.debt_payoff == 5000.0
    assert plan.investable_surplus == 6000.0
    assert plan.core_allocation == 5400.0
    assert plan.explore_allocation == 600.0
    assert len(plan.recommended_etfs) > 0


def test_low_interest_debt_preservation():
    # Debt at 3.0% (below 6.0% hurdle) -> is not forcefully cleared before investing
    plan = calculate_allocation(
        total_capital=25000.0,
        monthly_expenses=3500.0,
        emergency_months=4.0,
        debt_balance=5000.0,
        debt_interest_rate=3.0,
        risk_tolerance="growth",
    )
    assert plan.emergency_reserve == 14000.0
    assert plan.debt_payoff == 0.0
    assert plan.investable_surplus == 11000.0
    assert plan.explore_allocation == round(11000.0 * 0.15, 2)


def test_invalid_capital_rejected():
    with pytest.raises(ValueError, match="Total capital must be greater than zero"):
        calculate_allocation(total_capital=0.0)
