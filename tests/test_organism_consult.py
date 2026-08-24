"""Living organism: Bob decides only after consulting organs; doubt re-asks experts."""

from __future__ import annotations

from core.pipeline.nodes.agent import (
    _experts_need_reconsult,
    _forced_tool_call_before_final,
)
from core.pipeline.nodes.tool_executor import _SEMI_REPEATABLE_LIMITS


def test_run_experts_is_semi_repeatable_for_follow_up_doubt():
    assert _SEMI_REPEATABLE_LIMITS.get("run_experts") == 2


def test_thin_committee_forces_expert_reconsult():
    state = {
        "route": "ticker_analysis",
        "message": "analisa TD.TO",
        "ticker": "TD.TO",
        "data": {"ticker": "TD.TO", "ohlcv": [{"close": 1}]},
        "allowed_tools": ["run_experts", "final_answer"],
        "executed_tools": ["run_experts"],
        "executed_tool_counts": {"run_experts": 1},
        "expert_results": [{"role": "macro_risk", "error": "timeout", "ok": False}],
        "expert_summary": "partial",
    }
    assert _experts_need_reconsult(state) is True
    forced = _forced_tool_call_before_final(state)
    assert forced is not None
    assert forced["tool"] == "run_experts"
    assert "question" in forced["args"]


def test_healthy_committee_does_not_force_another_round():
    results = [
        {"role": "macro_risk", "ok": True},
        {"role": "fundamental_value", "ok": True},
        {"role": "momentum_technical", "ok": True},
        {"role": "contrarian_opportunity", "ok": True},
    ]
    state = {
        "route": "ticker_analysis",
        "message": "analisa TD.TO",
        "ticker": "TD.TO",
        "data": {"ticker": "TD.TO"},
        "allowed_tools": ["run_experts", "f51_firewall", "final_answer"],
        "executed_tools": ["run_experts"],
        "executed_tool_counts": {"run_experts": 1},
        "expert_results": results,
        "expert_summary": "consensus hold",
    }
    assert _experts_need_reconsult(state) is False
    forced = _forced_tool_call_before_final(state)
    assert forced is None or forced["tool"] != "run_experts"


def test_second_reconsult_stops_after_two_expert_runs():
    state = {
        "route": "ticker_analysis",
        "message": "analisa TD.TO",
        "ticker": "TD.TO",
        "data": {"ticker": "TD.TO"},
        "allowed_tools": ["run_experts", "final_answer"],
        "executed_tools": ["run_experts"],
        "executed_tool_counts": {"run_experts": 2},
        "expert_results": [{"role": "macro_risk", "error": "still_dead"}],
        "expert_summary": "broken",
    }
    forced = _forced_tool_call_before_final(state)
    assert forced is None or forced["tool"] != "run_experts"
