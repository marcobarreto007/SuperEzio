"""Tests for PositionSizer and KillSwitch — Loop 1."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


# ── PositionSizer ──────────────────────────────────────────────────────────


class TestPositionSizerInit:
    def test_defaults(self):
        from core.trading.position_sizer import PositionSizer

        s = PositionSizer(equity=10000)
        assert s.equity == 10000
        assert s.max_risk_pct == 0.02
        assert s.max_open_positions == 3
        assert s.min_notional == 50.0

    def test_custom_params(self):
        from core.trading.position_sizer import PositionSizer

        s = PositionSizer(equity=50000, max_risk_pct=0.01, max_open_positions=5)
        assert s.max_risk_amount == 500.0

    def test_zero_equity_raises(self):
        from core.trading.position_sizer import PositionSizer

        with pytest.raises(ValueError):
            PositionSizer(equity=0)

    def test_negative_equity_raises(self):
        from core.trading.position_sizer import PositionSizer

        with pytest.raises(ValueError):
            PositionSizer(equity=-100)

    def test_invalid_risk_pct_raises(self):
        from core.trading.position_sizer import PositionSizer

        with pytest.raises(ValueError):
            PositionSizer(equity=10000, max_risk_pct=0.5)


class TestPositionSizerSize:
    def test_basic_sizing(self):
        from core.trading.position_sizer import PositionSizer

        s = PositionSizer(equity=10000, max_risk_pct=0.02)
        result = s.size(entry_price=100.0, stop_loss_price=95.0)
        assert result.shares == 40  # R$200 risk / R$5 risk per share
        assert result.notional_value == 4000.0
        assert result.stop_loss_price == 95.0
        assert result.shares > 0

    def test_default_stop_loss(self):
        from core.trading.position_sizer import PositionSizer

        s = PositionSizer(equity=10000, default_stop_pct=0.05)
        result = s.size(entry_price=100.0)
        assert result.stop_loss_price == 95.0

    def test_max_positions_reached(self):
        from core.trading.position_sizer import PositionSizer

        s = PositionSizer(equity=10000, max_open_positions=3)
        result = s.size(entry_price=100.0, stop_loss_price=95.0, open_positions=3)
        assert result.shares == 0
        assert "max_open_positions" in result.size_reason

    def test_min_notional_filter(self):
        from core.trading.position_sizer import PositionSizer

        s = PositionSizer(equity=50, max_risk_pct=0.01, min_notional=100.0)
        result = s.size(entry_price=500.0, stop_loss_price=495.0)
        assert result.shares == 0
        assert "below min" in result.size_reason

    def test_stop_above_entry_raises(self):
        from core.trading.position_sizer import PositionSizer

        s = PositionSizer(equity=10000)
        with pytest.raises(ValueError, match="must be below"):
            s.size(entry_price=100.0, stop_loss_price=105.0)

    def test_zero_entry_raises(self):
        from core.trading.position_sizer import PositionSizer

        s = PositionSizer(equity=10000)
        with pytest.raises(ValueError):
            s.size(entry_price=0)

    def test_can_open(self):
        from core.trading.position_sizer import PositionSizer

        s = PositionSizer(equity=10000, max_open_positions=2)
        assert s.can_open(0) is True
        assert s.can_open(1) is True
        assert s.can_open(2) is False


# ── KillSwitch ──────────────────────────────────────────────────────────────


class TestKillSwitchInit:
    def test_starts_inactive(self):
        from core.trading.kill_switch import KillSwitch

        ks = KillSwitch()
        assert ks.is_active is False

    def test_custom_limits(self):
        from core.trading.kill_switch import KillSwitch

        ks = KillSwitch(daily_loss_limit=200, max_consecutive_losses=3)
        assert ks.daily_loss_limit == 200
        assert ks.max_consecutive_losses == 3


class TestKillSwitchDailyLoss:
    def test_triggers_on_daily_loss_limit(self):
        from core.trading.kill_switch import KillSwitch, KillSwitchReason

        ks = KillSwitch(daily_loss_limit=500)
        triggered = ks.record_trade(-300)
        assert not triggered
        triggered = ks.record_trade(-250)
        assert triggered
        assert ks.is_active
        assert ks.state.reason == KillSwitchReason.DAILY_LOSS_LIMIT

    def test_no_trigger_with_profit(self):
        from core.trading.kill_switch import KillSwitch

        ks = KillSwitch(daily_loss_limit=500)
        ks.record_trade(100)
        ks.record_trade(200)
        assert not ks.is_active

    def test_mixed_trades_trigger(self):
        from core.trading.kill_switch import KillSwitch

        ks = KillSwitch(daily_loss_limit=300)
        ks.record_trade(-200)
        ks.record_trade(100)
        triggered = ks.record_trade(-250)
        assert triggered


class TestKillSwitchDrawdown:
    def test_triggers_on_max_drawdown(self):
        from core.trading.kill_switch import KillSwitch, KillSwitchReason

        ks = KillSwitch(daily_loss_limit=99999, max_drawdown_pct=0.10, initial_equity=10000)
        ks.record_trade(500)  # peak = 10500
        triggered = ks.record_trade(-1200)  # pnl=-700, equity=9800, dd=6.7%
        assert not triggered
        triggered = ks.record_trade(-400)  # pnl=-1100, equity=9400, dd=10.5%
        assert triggered
        assert ks.state.reason == KillSwitchReason.MAX_DRAWDOWN


class TestKillSwitchConsecutiveLosses:
    def test_triggers_on_consecutive_losses(self):
        from core.trading.kill_switch import KillSwitch, KillSwitchReason

        ks = KillSwitch(max_consecutive_losses=3)
        ks.record_trade(-50)
        ks.record_trade(-30)
        triggered = ks.record_trade(-20)
        assert triggered
        assert ks.state.reason == KillSwitchReason.CONSECUTIVE_LOSSES

    def test_resets_on_win(self):
        from core.trading.kill_switch import KillSwitch

        ks = KillSwitch(max_consecutive_losses=3)
        ks.record_trade(-50)
        ks.record_trade(-30)
        ks.record_trade(100)  # reset consecutive
        assert ks.state.consecutive_losses == 0


class TestKillSwitchControl:
    def test_manual_activate(self):
        from core.trading.kill_switch import KillSwitch, KillSwitchReason

        ks = KillSwitch()
        ks.activate(KillSwitchReason.MANUAL)
        assert ks.is_active
        assert ks.state.reason == KillSwitchReason.MANUAL

    def test_deactivate(self):
        from core.trading.kill_switch import KillSwitch, KillSwitchReason

        ks = KillSwitch()
        ks.activate(KillSwitchReason.MANUAL)
        ks.deactivate()
        assert not ks.is_active

    def test_reset_day(self):
        from core.trading.kill_switch import KillSwitch

        ks = KillSwitch(daily_loss_limit=100)
        ks.record_trade(-80)
        ks.record_trade(-50)  # triggers
        assert ks.is_active
        ks.reset_day()
        assert not ks.is_active
        assert ks.state.daily_pnl == 0.0

    def test_history_recorded(self):
        from core.trading.kill_switch import KillSwitch, KillSwitchReason

        ks = KillSwitch(daily_loss_limit=100)
        ks.record_trade(-120)
        assert len(ks.history) == 1
        assert ks.history[0]["event"] == "activated"
