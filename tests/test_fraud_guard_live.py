"""Regression: the fraud guard must actually evaluate computable rules.

History: red_flag_rules.json had 15 provider-gated rules (R001-R015) with no
"computable" flag, while the engines only implement 6 DataHub-computable ids.
Result: 0 rules built, confidence always 0.0 — a dead guard. These tests pin
the dataset/engine contract so the guard can never silently die again.
"""

from __future__ import annotations

import asyncio

import pytest

from core.investor.fraud_analyst import FraudPatternAnalyst
from core.investor.fraud_memory import get_fraud_memory

COMPUTABLE_IDS = {
    "extreme_volume_spike",
    "unusual_volume_without_clear_news",
    "price_spike_high_volatility",
    "microcap_concentration",
    "vague_hype_sector_description",
    "no_revenue_with_operations",
}


def test_computable_rules_are_exactly_the_six_engine_implemented_ids():
    memory = get_fraud_memory()
    computable = memory.get_computable_rules()
    ids = {rule["rule_id"] for rule in computable}
    assert ids == COMPUTABLE_IDS, "computable rule set drifted from the engine contract"


def test_non_computable_rules_are_explicitly_flagged():
    memory = get_fraud_memory()
    non_computable = memory.get_non_computable_rules()
    assert len(non_computable) >= 15
    assert all(rule.get("computable") is False for rule in non_computable)


def test_extreme_volume_spike_fires():
    analyst = FraudPatternAnalyst()
    rule = next(
        r
        for r in get_fraud_memory().get_computable_rules()
        if r["rule_id"] == "extreme_volume_spike"
    )
    fired, evidence = analyst._evaluate_single_rule(
        rule, {"volume_z_score": 4.2, "data_date": "2026-08-21"}, "TEST"
    )
    assert fired is True
    assert evidence is not None
    assert "extreme_volume_zscore_TEST" in evidence


def test_unusual_volume_band_fires_without_subsume():
    analyst = FraudPatternAnalyst()
    rule = next(
        r
        for r in get_fraud_memory().get_computable_rules()
        if r["rule_id"] == "unusual_volume_without_clear_news"
    )
    fired, _ = analyst._evaluate_single_rule(
        rule, {"volume_z_score": 2.5, "data_date": "2026-08-21"}, "TEST"
    )
    assert fired is True
    fired_subsumed, _ = analyst._evaluate_single_rule(
        rule,
        {"volume_z_score": 2.5, "data_date": "2026-08-21"},
        "TEST",
        extreme_already_fired=True,
    )
    assert fired_subsumed is False


def test_microcap_concentration_fires_and_clears():
    analyst = FraudPatternAnalyst()
    rule = next(
        r
        for r in get_fraud_memory().get_computable_rules()
        if r["rule_id"] == "microcap_concentration"
    )
    fired, _ = analyst._evaluate_single_rule(
        rule, {"market_cap": 10_000_000, "data_date": "2026-08-21"}, "TEST"
    )
    assert fired is True
    cleared, _ = analyst._evaluate_single_rule(
        rule, {"market_cap": 500_000_000, "data_date": "2026-08-21"}, "TEST"
    )
    assert cleared is False


def test_full_analyze_triggers_rules_without_network():
    analyst = FraudPatternAnalyst()
    market_data = {
        "ticker": "TEST",
        "volume_z_score": 4.5,
        "recent_volume": 9_000_000,
        "avg_volume_20d": 1_000_000,
        "daily_return": 0.18,
        "market_cap": 30_000_000,
        "description": "",
        "revenue": None,
        "data_date": "2026-08-21",
    }
    result = asyncio.run(analyst.analyze("TEST", market_data=market_data))

    assert result["specialist"] == "fraud_pattern_analyst"
    assert "extreme_volume_zscore_TEST" in result["evidence_ids"][0]
    assert result["rule_risk_score"] > 0
    assert result["confidence"] > 0
    assert "pump_and_dump" in result["matched_patterns"]


def test_f51_adapter_builds_all_six_rules_and_they_fire():
    pytest.importorskip("f51")
    from core.f51_adapter.adapter import _build_risk_rules_from_hub

    rules = _build_risk_rules_from_hub()
    assert len(rules) == 6, "adapter must build exactly the 6 computable rules"

    by_name = {rule.name: rule for rule in rules}
    extreme = by_name["extreme_volume_spike"]
    triggered, evidence = extreme.evaluate({"features": {"volume_z_score": 4.0}})
    assert triggered is True
    assert "4.00" in evidence
