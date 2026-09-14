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
            {
                "role": "judge_agent_1",
                "ok": True,
                "verdict": "BLOCK",
                "parsed": {"reason": "risk too high"},
            }
        ]
    }
    reason = judge_block_reason(state_block)
    assert reason is not None
    assert "risk too high" in reason

    # Judge returns VETO
    state_veto = {
        "judge_results": [
            {
                "role": "judge_agent_1",
                "ok": True,
                "parsed": {"verdict": "VETO", "recommendation": "conflicting analysts"},
            }
        ]
    }
    reason = judge_block_reason(state_veto)
    assert reason is not None
    assert "conflicting analysts" in reason

    # Judge returns ALLOW / SUPPORT -> no block
    state_allow = {
        "judge_results": [{"role": "judge_agent_1", "ok": True, "parsed": {"verdict": "ALLOW"}}]
    }
    assert judge_block_reason(state_allow) is None

    # Empty judge results -> no block (arbitration was disabled)
    assert judge_block_reason({}) is None


def test_micro_capital_survival_allows_commission_free_etf():
    from core.trading.execution_policy import micro_capital_survival_block_reason

    # SPY is in TD 108 commission-free ETF list -> allowed.
    # The target is now part of the contract: 500/495/515 = 3:1 asymmetry.
    reason = micro_capital_survival_block_reason(
        {},
        "SPY",
        limit_price=500.0,
        stop_loss_price=495.0,
        take_profit_price=515.0,
        order_type="LIMIT",
    )
    assert reason is None


def test_micro_capital_survival_blocks_non_free_stock():
    from core.trading.execution_policy import micro_capital_survival_block_reason

    # Non-free ticker without confirmed free trade quota -> BLOCKED
    reason = micro_capital_survival_block_reason(
        {},
        "SOME_RANDOM_STOCK",
        limit_price=10.0,
        stop_loss_price=9.5,
        order_type="LIMIT",
    )
    assert reason is not None
    assert "zero_commission_violation" in reason


def test_micro_capital_survival_allows_non_free_stock_with_td_easy_trade_quota():
    from core.trading.execution_policy import micro_capital_survival_block_reason

    # Non-free ticker with confirmed TD Easy Trade 100 free trades quota -> ALLOWED
    state = {"td_easy_trade_free_quota": True}
    reason = micro_capital_survival_block_reason(
        state,
        "SOME_RANDOM_STOCK",
        limit_price=10.0,
        stop_loss_price=9.5,
        take_profit_price=11.5,  # 3:1
        order_type="LIMIT",
    )
    assert reason is None


def test_micro_capital_survival_allows_three_to_one_asymmetry():
    """3:1 passes the protocol's 2.5:1 minimum."""
    from core.trading.execution_policy import micro_capital_survival_block_reason

    assert (
        micro_capital_survival_block_reason(
            {},
            "SPY",
            limit_price=100.0,
            stop_loss_price=95.0,  # $5 stop
            take_profit_price=115.0,  # $15 target = 3:1
            order_type="LIMIT",
        )
        is None
    )


def test_micro_capital_survival_blocks_insufficient_asymmetry():
    """1.5:1 is exactly the 1:1-ish trade CLAUDE.md rule 7 forbids."""
    from core.trading.execution_policy import micro_capital_survival_block_reason

    reason = micro_capital_survival_block_reason(
        {},
        "SPY",
        limit_price=100.0,
        stop_loss_price=95.0,  # $5 stop
        take_profit_price=107.5,  # $7.50 target = 1.5:1
        order_type="LIMIT",
    )
    assert reason is not None
    assert "insufficient_asymmetry" in reason
    assert "1.50:1" in reason
    assert "2.5:1" in reason


def test_micro_capital_survival_fails_closed_without_take_profit():
    """A missing target is a missing proof, not a pass — trades 1:1 are banned."""
    from core.trading.execution_policy import micro_capital_survival_block_reason

    reason = micro_capital_survival_block_reason(
        {},
        "SPY",
        limit_price=100.0,
        stop_loss_price=95.0,
        order_type="LIMIT",
    )
    assert reason is not None
    assert "asymmetry_unknown" in reason


def test_micro_capital_survival_fails_closed_without_stop():
    """A missing stop leaves the ratio undefined — block, never assume."""
    from core.trading.execution_policy import micro_capital_survival_block_reason

    reason = micro_capital_survival_block_reason(
        {},
        "SPY",
        limit_price=100.0,
        take_profit_price=115.0,
        order_type="LIMIT",
    )
    assert reason is not None
    assert "asymmetry_unknown" in reason


def test_micro_capital_survival_blocks_market_order():
    from core.trading.execution_policy import micro_capital_survival_block_reason

    # Market orders are strictly forbidden under micro-capital protocol
    reason = micro_capital_survival_block_reason(
        {},
        "SPY",
        limit_price=500.0,
        stop_loss_price=495.0,
        order_type="MARKET",
    )
    assert reason is not None
    assert "market_orders_forbidden" in reason


def test_micro_capital_survival_blocks_excessive_risk_spread():
    from core.trading.execution_policy import micro_capital_survival_block_reason

    # Risk per share alone ($25) exceeds entire $15 max trade risk budget -> BLOCKED
    reason = micro_capital_survival_block_reason(
        {},
        "SPY",
        limit_price=500.0,
        stop_loss_price=475.0,  # $25 risk per share
        order_type="LIMIT",
    )
    assert reason is not None
    assert "risk_per_share_too_wide" in reason
