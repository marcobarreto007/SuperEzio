"""Contract tests for Fraud Analyst, Cost Guard, and Investor Storage."""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Fraud Analyst
# ---------------------------------------------------------------------------


def test_fraud_analyst_import():
    from core.investor.fraud_analyst import FraudPatternAnalyst

    assert FraudPatternAnalyst is not None


def test_fraud_analyst_instantiation():
    from core.investor.fraud_analyst import FraudPatternAnalyst

    analyst = FraudPatternAnalyst()
    assert analyst is not None


# ---------------------------------------------------------------------------
# Cost Guard
# ---------------------------------------------------------------------------


def test_cost_guard_import():
    from core.investor.cost_guard import CostGuard

    assert CostGuard is not None


def test_cost_guard_instantiation():
    from core.investor.cost_guard import CostGuard

    guard = CostGuard()
    assert guard is not None
    assert hasattr(guard, "check")


# ---------------------------------------------------------------------------
# Investor Storage
# ---------------------------------------------------------------------------


def test_investor_storage_import():
    from core.investor.storage import InvestorStorage

    assert InvestorStorage is not None


# ---------------------------------------------------------------------------
# Agent profiles
# ---------------------------------------------------------------------------


def test_investor_modules_importable():
    """All investor sub-modules must be importable."""
    import importlib

    modules = [
        "core.investor.cost_guard",
        "core.investor.fraud_analyst",
        "core.investor.fraud_memory",
        "core.investor.storage",
    ]

    for module_name in modules:
        mod = importlib.import_module(module_name)
        assert mod is not None, f"Failed to import {module_name}"
