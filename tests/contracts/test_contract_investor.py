"""Contract tests for Investor Committee, Fraud Analyst, and Cost Guard."""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Investor Committee (Family Investor Committee)
# ---------------------------------------------------------------------------


def test_investor_committee_imports():
    from core.investor.committee import InvestorCommittee

    assert InvestorCommittee is not None


def test_investor_committee_instantiation():
    from core.investor.committee import InvestorCommittee

    committee = InvestorCommittee()
    assert committee is not None
    assert hasattr(committee, "analyze")


def test_investor_committee_has_members():
    from core.investor.committee import InvestorCommittee

    committee = InvestorCommittee()
    assert hasattr(committee, "_parse_and_validate") or hasattr(committee, "_detect_fomo")


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
        "core.investor.committee",
        "core.investor.cost_guard",
        "core.investor.fraud_analyst",
        "core.investor.fraud_memory",
        "core.investor.prompts",
        "core.investor.storage",
    ]

    for module_name in modules:
        mod = importlib.import_module(module_name)
        assert mod is not None, f"Failed to import {module_name}"
