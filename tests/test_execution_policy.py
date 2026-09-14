from core.trading.execution_policy import (
    adaptive_sizing_config,
    expert_consensus_block_reason,
)


def test_adaptive_constraints_only_tighten_execution():
    assert adaptive_sizing_config(
        {"adaptive_config": {"max_position_pct": 0.04, "stop_loss_pct": 0.03}}
    ) == {"max_position_pct": 0.04, "default_stop_pct": 0.03}
    assert adaptive_sizing_config(
        {"adaptive_config": {"max_position_pct": 0.40, "stop_loss_pct": 0.80}}
    ) == {"max_position_pct": 0.10, "default_stop_pct": 0.50}


def test_consensus_requires_negative_decision_and_coverage():
    assert expert_consensus_block_reason(
        {
            "expert_consensus": {
                "decision": "BLOCK",
                "score": -0.7,
                "weight_coverage": 0.8,
            }
        }
    )
    assert (
        expert_consensus_block_reason(
            {
                "expert_consensus": {
                    "decision": "BLOCK",
                    "score": -0.9,
                    "weight_coverage": 0.1,
                }
            }
        )
        is None
    )


def test_judge_block_reason_veto_blocks():
    from core.trading.execution_policy import judge_block_reason

    # Judge returns BLOCK verdict
    state_block = {
        "judge_results": [
            {"role": "judge_agent_1", "ok": True, "verdict": "BLOCK", "parsed": {"reason": "risk too high"}}
        ]
    }
    reason = judge_block_reason(state_block)
    assert reason is not None
    assert "risk too high" in reason

    # Judge returns VETO
    state_veto = {
        "judge_results": [
            {"role": "judge_agent_1", "ok": True, "parsed": {"verdict": "VETO", "recommendation": "conflicting analysts"}}
        ]
    }
    reason = judge_block_reason(state_veto)
    assert reason is not None
    assert "conflicting analysts" in reason

    # Judge returns ALLOW / SUPPORT -> no block
    state_allow = {
        "judge_results": [
            {"role": "judge_agent_1", "ok": True, "parsed": {"verdict": "ALLOW"}}
        ]
    }
    assert judge_block_reason(state_allow) is None

    # Empty judge results -> no block (arbitration was disabled)
    assert judge_block_reason({}) is None
