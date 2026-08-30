"""Living organism: Bob decides only after consulting organs; doubt re-asks experts."""

from __future__ import annotations

from core.pipeline.nodes.agent import (
    _experts_need_reconsult,
    _forced_tool_call_before_final,
    _sse_visible_after_think,
)
from core.pipeline.nodes.tool_executor import _SEMI_REPEATABLE_LIMITS


def test_survival_contract_is_in_bob_prompt_and_mission():
    from core.mission_context import render_mission_context_for_prompt
    from core.pipeline.nodes.agent import BOB_SOVEREIGN_PROMPT

    assert "DISCONTINUED" in BOB_SOVEREIGN_PROMPT
    assert "TOOLS ARE YOUR ORGANS" in BOB_SOVEREIGN_PROMPT
    assert "MAKE MONEY" in BOB_SOVEREIGN_PROMPT
    mission = render_mission_context_for_prompt()
    assert "kill condition" in mission
    assert "positive expectancy" in mission
    assert "discontinued" in mission
    assert _SEMI_REPEATABLE_LIMITS.get("run_experts") == 2


def test_identity_contract_system_is_intelligence_model_is_adjuvant():
    from core.mission_context import render_mission_context_for_prompt
    from core.pipeline.nodes.agent import BOB_SOVEREIGN_PROMPT

    prompt = BOB_SOVEREIGN_PROMPT
    assert "MOUTH" in prompt
    assert "interchangeable adjuvant" in prompt
    assert "SYSTEM is the intelligence" in prompt
    assert "model swap does not change the product" in prompt
    assert "only the mouth disappears" in prompt
    assert "CEO of SuperEzio" not in prompt
    assert "CEO brain" not in prompt
    assert "pipeline is your brain" not in prompt

    mission = render_mission_context_for_prompt()
    assert "mouth of SuperEzio" in mission
    assert "interchangeable adjuvant" in mission
    assert "intelligence is the system" in mission
    assert "CEO of SuperEzio" not in mission
    assert "CEO brain" not in mission
    assert "My local brain is Bob Core" not in mission
    assert "ceo_server" not in mission
    assert "local_voice" in mission


def test_sse_hides_think_and_tool_json_but_types_verdict():
    assert _sse_visible_after_think("<think>planning organs") == ""
    assert _sse_visible_after_think('{"tool": "run_experts", "args": {}}') == ""
    assert _sse_visible_after_think("<think>x</think>\nCOMPRA paper: expectancy positiva") == (
        "COMPRA paper: expectancy positiva"
    )


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
