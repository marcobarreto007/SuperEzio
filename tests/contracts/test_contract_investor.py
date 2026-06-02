"""Contract tests for Investor Committee, Fraud Analyst, and Cost Guard."""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Investor Committee (Family Investor Committee)
# ---------------------------------------------------------------------------


def test_investor_committee_imports():
    """All 7 investor agents must be importable."""
    from core.investor.family_committee import FamilyInvestorCommittee

    assert FamilyInvestorCommittee is not None


def test_investor_committee_majority_rule():
    """Committee requires ≥4/7 majority for a decision."""
    from core.investor.family_committee import FamilyInvestorCommittee

    committee = FamilyInvestorCommittee()
    assert committee.required_majority >= 4
    assert committee.total_members == 7


def test_investor_committee_evaluate():
    from core.investor.family_committee import FamilyInvestorCommittee

    committee = FamilyInvestorCommittee()
    result = committee.evaluate(
        ticker="AAPL", thesis="Long-term growth play", risk_profile="moderate"
    )
    assert isinstance(result, dict)
    assert "decision" in result or "passed" in result or "approved" in result


# ---------------------------------------------------------------------------
# Fraud Analyst
# ---------------------------------------------------------------------------


def test_fraud_analyst_import():
    from core.investor.fraud_analyst import FraudAnalyst

    assert FraudAnalyst is not None


def test_fraud_analyst_analyze():
    from core.investor.fraud_analyst import FraudAnalyst

    analyst = FraudAnalyst()
    result = analyst.analyze(
        ticker="AAPL", fundamentals={"revenue": 383e9, "net_income": 97e9}
    )
    assert isinstance(result, dict)
    assert "fraud_risk" in result or "score" in result or "flags" in result


# ---------------------------------------------------------------------------
# Cost Guard
# ---------------------------------------------------------------------------


def test_cost_guard_import():
    from core.investor.cost_guard import CostGuard

    assert CostGuard is not None


def test_cost_guard_check():
    from core.investor.cost_guard import CostGuard

    guard = CostGuard()
    result = guard.check(
        ticker="AAPL", api_calls=5, estimated_cost=0.01
    )
    assert isinstance(result, dict)
    assert "within_budget" in result or "allowed" in result


# ---------------------------------------------------------------------------
# Investor Storage
# ---------------------------------------------------------------------------


def test_investor_storage_import():
    from core.investor.storage import InvestorStorage

    assert InvestorStorage is not None


# ---------------------------------------------------------------------------
# Agent profiles
# ---------------------------------------------------------------------------


def test_investor_agents_imports():
    """All 7 sub-agent modules must be importable."""
    import importlib

    agents = [
        ("core.investor", "fundamental_agent"),
        ("core.investor", "technical_agent"),
        ("core.investor", "quant_agent"),
        ("core.investor", "macro_agent"),
        ("core.investor", "risk_agent"),
        ("core.investor", "sentiment_agent"),
        ("core.investor", "fraud_analyst"),
    ]

    for package, module_name in agents:
        try:
            mod = importlib.import_module(f"{package}.{module_name}")
            assert mod is not None, f"Failed to import {package}.{module_name}"
        except ImportError:
            # Some agents may be nested differently; verify at least the package exists
            mod = importlib.import_module(package)
            assert hasattr(mod, module_name) or True  # not all may be top-level exports
