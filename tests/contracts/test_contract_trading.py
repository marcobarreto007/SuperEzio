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
    # A fresh kill switch must not be active
    assert ks.is_active() is False


def test_kill_switch_activate():
    from core.trading.kill_switch import KillSwitch, KillSwitchReason

    ks = KillSwitch()
    ks.activate(reason=KillSwitchReason.MANUAL)
    assert ks.is_active() is True


def test_kill_switch_deactivate():
    from core.trading.kill_switch import KillSwitch, KillSwitchReason

    ks = KillSwitch()
    ks.activate(reason=KillSwitchReason.MANUAL)
    ks.deactivate()
    assert ks.is_active() is False


# ---------------------------------------------------------------------------
# Position Sizer
# ---------------------------------------------------------------------------


def test_position_sizer_import():
    from core.trading.position_sizer import PositionSizer

    assert PositionSizer is not None


def test_position_sizer_calculate():
    from core.trading.position_sizer import PositionSizer

    ps = PositionSizer(max_position_pct=0.05)
    size = ps.calculate(portfolio_value=100000.0, risk_per_share=5.0, stop_loss_pct=0.02)
    assert size >= 0
    # Must not exceed 5% of portfolio
    max_position = 100000.0 * 0.05
    assert size * risk_per_share <= max_position


def test_position_sizer_zero_portfolio():
    from core.trading.position_sizer import PositionSizer

    ps = PositionSizer()
    size = ps.calculate(portfolio_value=0.0, risk_per_share=5.0, stop_loss_pct=0.02)
    assert size == 0


# ---------------------------------------------------------------------------
# Order Builder
# ---------------------------------------------------------------------------


def test_order_builder_import():
    from core.trading.order_builder import OrderBuilder

    assert OrderBuilder is not None


def test_order_builder_build():
    from core.trading.order_builder import OrderBuilder

    builder = OrderBuilder()
    order = builder.build(ticker="AAPL", quantity=100, side="buy", order_type="market")
    assert order is not None
    assert order.get("ticker") == "AAPL" or order.get("symbol") == "AAPL"
    assert order.get("quantity") == 100 or order.get("shares") == 100


# ---------------------------------------------------------------------------
# Approval Gate
# ---------------------------------------------------------------------------


def test_approval_gate_import():
    from core.trading.approval_gate import ApprovalGate

    assert ApprovalGate is not None


def test_approval_gate_default():
    from core.trading.approval_gate import ApprovalGate

    gate = ApprovalGate()
    assert hasattr(gate, "evaluate")


def test_approval_gate_evaluate_basic():
    from core.trading.approval_gate import ApprovalGate

    gate = ApprovalGate()
    result = gate.evaluate(
        ticker="AAPL",
        quantity=10,
        side="buy",
        risk_score=0.2,
        kill_switch_triggered=False,
    )
    assert isinstance(result, dict)
    assert "passed" in result


# ---------------------------------------------------------------------------
# Alerter
# ---------------------------------------------------------------------------


def test_alerter_import():
    from core.trading.alerter import Alerter

    assert Alerter is not None


def test_alerter_instantiation():
    from core.trading.alerter import Alerter

    alerter = Alerter()
    assert alerter is not None
    assert hasattr(alerter, "send")


# ---------------------------------------------------------------------------
# Reward Model
# ---------------------------------------------------------------------------


def test_reward_model_import():
    from core.trading.reward import RewardModel

    assert RewardModel is not None


# ---------------------------------------------------------------------------
# Trade Weights
# ---------------------------------------------------------------------------


def test_trade_weights_import():
    from core.trading.weights import TradeWeights

    assert TradeWeights is not None


# ---------------------------------------------------------------------------
# Broker Adapter (IBKR)
# ---------------------------------------------------------------------------


def test_ibkr_adapter_import():
    from adapters.broker.ibkr_adapter import IBKRAdapter

    assert IBKRAdapter is not None
