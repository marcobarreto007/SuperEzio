"""Regression guards against fabricated predictive evidence."""

from __future__ import annotations

import asyncio

from core.data_collector.collector import DataCollector, QuantEngine
from data.data_hub import DataHub


def test_symbol_only_quant_engine_abstains_without_fake_neutral_probability() -> None:
    result = QuantEngine().analyze_asset("AAPL")

    assert result["status"] == "insufficient_data"
    assert result["direction_prob"] == {}
    assert result["calibration_status"] == "not_available"
    assert "ml_prob_up" not in result
    assert "combined_prob_up" not in result


def test_removed_quantum_dependency_is_never_executed() -> None:
    class LegacyRandomWalk:
        def run_simulation(self):  # pragma: no cover - execution is the failure
            raise AssertionError("removed random walk must never execute")

    collector = DataCollector(
        data_hub=object(),
        quantum_walk=LegacyRandomWalk(),
    )
    result = asyncio.run(collector._get_quantum_analysis())

    assert result["status"] == "removed"
    assert result["replacement"].startswith("MathHub.return_bootstrap")


def test_data_hub_does_not_advertise_random_quantum_provider() -> None:
    hub = DataHub(register_defaults=True)

    assert hub.list_routes("quantum") == []
    result = hub.run_quantum_simulation()
    assert result["status"] == "removed"
    assert "counts" not in result


def test_removed_sources_make_collection_quality_partial() -> None:
    payload = {
        "ticker": "AAPL",
        "collected_at": "2026-07-19T12:00:00+00:00",
        "quantum": {"status": "removed"},
    }

    DataCollector._attach_evidence(payload)

    assert payload["quantum"]["data_quality"] == "unavailable"
    assert payload["data_quality"] == "partial"
    assert "quantum" in payload["source_unavailable"]
