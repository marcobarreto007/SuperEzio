"""Contract tests for Trading Engine — kill switch, position sizer, order builder, approval gate."""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Kill Switch
# ---------------------------------------------------------------------------


def test_kill_switch_import():
    from core.trading.kill_switch import KillSwitch

    assert KillSwitch is not None


def test_kill_switch_default_not_active():
    from core.trading.kill_switch import KillSwitch

    ks = KillSwitch()
    # A fresh kill switch must not be active (is_active is a @property)
    assert ks.is_active is False


def test_kill_switch_activate():
    from core.trading.kill_switch import KillSwitch, KillSwitchReason

    ks = KillSwitch()
    ks.activate(reason=KillSwitchReason.MANUAL)
    assert ks.is_active is True


def test_kill_switch_deactivate():
    from core.trading.kill_switch import KillSwitch, KillSwitchReason

    ks = KillSwitch()
    ks.activate(reason=KillSwitchReason.MANUAL)
    ks.deactivate()
    assert ks.is_active is False


# ---------------------------------------------------------------------------
# Position Sizer
# ---------------------------------------------------------------------------


def test_position_sizer_import():
    from core.trading.position_sizer import PositionSizer

    assert PositionSizer is not None


def test_position_sizer_size():
    from core.trading.position_sizer import PositionSizer

    ps = PositionSizer(equity=100000.0, max_risk_pct=0.02)
    result = ps.size(entry_price=100.0, stop_loss_price=95.0)
    assert result is not None
    assert hasattr(result, "shares")
    assert result.shares >= 0
    assert result.notional_value >= 0


def test_position_sizer_zero_equity_raises():
    from core.trading.position_sizer import PositionSizer

    with pytest.raises(ValueError):
        PositionSizer(equity=0.0)


# ---------------------------------------------------------------------------
# Order Builder
# ---------------------------------------------------------------------------


def test_order_builder_import():
    from core.trading.order_builder import OrderBuilder

    assert OrderBuilder is not None


def test_order_builder_build_market_order():
    from core.trading.order_builder import OrderBuilder
    from core.trading.position_sizer import PositionSize
    from core.trading.broker import OrderSide

    builder = OrderBuilder()
    size = PositionSize(
        shares=100,
        notional_value=19500.0,
        risk_per_share=5.0,
        stop_loss_price=190.0,
        size_reason="test",
    )
    order = builder.build_market_order(symbol="AAPL", side=OrderSide.BUY, size=size)
    assert order is not None
    assert hasattr(order, "symbol")
    assert order.symbol == "AAPL"
    assert order.qty == 100


# ---------------------------------------------------------------------------
# Approval Gate
# ---------------------------------------------------------------------------


def test_approval_gate_import():
    from core.trading.approval_gate import ApprovalGate

    assert ApprovalGate is not None


def test_approval_gate_default():
    from core.trading.approval_gate import ApprovalGate

    gate = ApprovalGate()
    assert hasattr(gate, "submit")
    assert hasattr(gate, "approve")
    assert hasattr(gate, "reject")
    assert gate.pending_count == 0  # @property


def test_approval_gate_submit():
    from core.trading.approval_gate import ApprovalGate

    gate = ApprovalGate()
    request = gate.submit(
        symbol="AAPL",
        side="buy",
        qty=10,
        entry_price=195.0,
        stop_loss_price=190.0,
        risk_amount=50.0,
        reason="momentum",
    )
    assert request is not None
    assert hasattr(request, "id")
    assert request.status.value == "pending"
    assert gate.pending_count == 1  # @property


# ---------------------------------------------------------------------------
# Alerter
# ---------------------------------------------------------------------------


def test_alerter_import():
    from core.trading.alerter import LogAlerter

    assert LogAlerter is not None


def test_alerter_instantiation():
    from core.trading.alerter import LogAlerter

    alerter = LogAlerter()
    assert alerter is not None
    assert hasattr(alerter, "send_trade_alert")


# ---------------------------------------------------------------------------
# Reward Model
# ---------------------------------------------------------------------------


def test_reward_model_import():
    from core.trading.reward import RewardFunction

    assert RewardFunction is not None


# ---------------------------------------------------------------------------
# Expert Weights
# ---------------------------------------------------------------------------


def test_expert_weights_import():
    from core.trading.expert_weights import ExpertWeightRouter

    assert ExpertWeightRouter is not None


# ---------------------------------------------------------------------------
# Broker Adapter (IBKR)
# ---------------------------------------------------------------------------


def test_ibkr_adapter_import():
    from adapters.broker.ibkr_adapter import InteractiveBrokersAdapter

    assert InteractiveBrokersAdapter is not None
