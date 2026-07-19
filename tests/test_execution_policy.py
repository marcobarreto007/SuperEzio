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
