"""Tests for Broker Adapter + Order Builder — Loop 2."""

import os
import sys


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


# ── SimulatedBroker ─────────────────────────────────────────────────────────


class TestSimulatedBroker:
    def test_initial_equity(self):
        from core.trading.broker import SimulatedBroker

        broker = SimulatedBroker(initial_equity=50000)
        assert broker.get_account_equity() == 50000

    def test_submit_market_order(self):
        from core.trading.broker import (
            Order,
            OrderSide,
            OrderStatus,
            OrderType,
            SimulatedBroker,
        )

        broker = SimulatedBroker()
        order = Order(
            id="pending",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            qty=10,
            status=OrderStatus.PENDING,
        )
        result = broker.submit_order(order)
        assert result.status == OrderStatus.FILLED
        assert result.id.startswith("sim-")
        assert result.symbol == "AAPL"
        assert result.qty == 10

    def test_submit_multiple_orders_unique_ids(self):
        from core.trading.broker import (
            Order,
            OrderSide,
            OrderStatus,
            OrderType,
            SimulatedBroker,
        )

        broker = SimulatedBroker()
        order = Order(
            id="pending",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            qty=10,
            status=OrderStatus.PENDING,
        )
        r1 = broker.submit_order(order)
        r2 = broker.submit_order(order)
        assert r1.id != r2.id

    def test_cancel_order(self):
        from core.trading.broker import (
            Order,
            OrderSide,
            OrderStatus,
            OrderType,
            SimulatedBroker,
        )

        broker = SimulatedBroker()
        order = Order(
            id="pending",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            qty=10,
            status=OrderStatus.PENDING,
        )
        result = broker.submit_order(order)
        assert broker.cancel_order(result.id) is True
        fetched = broker.get_order(result.id)
        assert fetched is not None
        assert fetched.status == OrderStatus.CANCELLED

    def test_cancel_nonexistent_order(self):
        from core.trading.broker import SimulatedBroker

        broker = SimulatedBroker()
        assert broker.cancel_order("no-such-id") is False

    def test_get_order(self):
        from core.trading.broker import (
            Order,
            OrderSide,
            OrderStatus,
            OrderType,
            SimulatedBroker,
        )

        broker = SimulatedBroker()
        order = Order(
            id="pending",
            symbol="TSLA",
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            qty=5,
            status=OrderStatus.PENDING,
        )
        result = broker.submit_order(order)
        fetched = broker.get_order(result.id)
        assert fetched is not None
        assert fetched.symbol == "TSLA"
        assert fetched.side == OrderSide.SELL

    def test_get_order_not_found(self):
        from core.trading.broker import SimulatedBroker

        broker = SimulatedBroker()
        assert broker.get_order("nonexistent") is None

    def test_get_positions_empty(self):
        from core.trading.broker import SimulatedBroker

        broker = SimulatedBroker()
        assert broker.get_positions() == []


# ── OrderBuilder ─────────────────────────────────────────────────────────────


class TestOrderBuilderInit:
    def test_defaults(self):
        from core.trading.order_builder import OrderBuilder

        ob = OrderBuilder()
        assert ob.default_slippage_pct == 0.001
        assert ob.default_take_profit_ratio == 2.0

    def test_custom_params(self):
        from core.trading.order_builder import OrderBuilder

        ob = OrderBuilder(default_slippage_pct=0.005, default_take_profit_ratio=3.0)
        assert ob.default_slippage_pct == 0.005
        assert ob.default_take_profit_ratio == 3.0


class TestOrderBuilderMarket:
    def test_build_market_buy(self):
        from core.trading.broker import OrderSide, OrderStatus
        from core.trading.order_builder import OrderBuilder
        from core.trading.position_sizer import PositionSize

        ob = OrderBuilder()
        size = PositionSize(
            shares=40,
            notional_value=4000.0,
            risk_per_share=5.0,
            stop_loss_price=95.0,
            size_reason="test",
        )
        order = ob.build_market_order("AAPL", OrderSide.BUY, size)
        assert order is not None
        assert order.symbol == "AAPL"
        assert order.side == OrderSide.BUY
        assert order.qty == 40
        assert order.status == OrderStatus.PENDING

    def test_build_market_zero_shares_returns_none(self):
        from core.trading.broker import OrderSide
        from core.trading.order_builder import OrderBuilder
        from core.trading.position_sizer import PositionSize

        ob = OrderBuilder()
        size = PositionSize(
            shares=0,
            notional_value=0,
            risk_per_share=0,
            stop_loss_price=95.0,
            size_reason="blocked",
        )
        assert ob.build_market_order("AAPL", OrderSide.BUY, size) is None

    def test_build_market_with_reason_ignored(self):
        from core.trading.broker import OrderSide
        from core.trading.order_builder import OrderBuilder
        from core.trading.position_sizer import PositionSize

        ob = OrderBuilder()
        size = PositionSize(
            shares=10,
            notional_value=1000.0,
            risk_per_share=5.0,
            stop_loss_price=95.0,
            size_reason="sizer_reason",
        )
        order = ob.build_market_order("AAPL", OrderSide.BUY, size)
        assert order is not None
        assert order.qty == 10


class TestOrderBuilderBracket:
    def test_build_bracket_buy(self):
        from core.trading.broker import OrderSide, OrderType
        from core.trading.order_builder import OrderBuilder
        from core.trading.position_sizer import PositionSize

        ob = OrderBuilder()
        size = PositionSize(
            shares=40,
            notional_value=4000.0,
            risk_per_share=5.0,
            stop_loss_price=95.0,
            size_reason="test",
        )
        bracket = ob.build_bracket_order("AAPL", OrderSide.BUY, size)
        assert bracket is not None
        assert bracket.entry.symbol == "AAPL"
        assert bracket.entry.qty == 40
        assert bracket.stop_loss is not None
        assert bracket.stop_loss.side == OrderSide.SELL
        assert bracket.stop_loss.order_type == OrderType.STOP
        assert bracket.stop_loss.stop_price < 95.0  # slippage padding
        assert bracket.take_profit is not None
        assert bracket.take_profit.side == OrderSide.SELL
        assert bracket.take_profit.order_type == OrderType.LIMIT
        assert bracket.take_profit.limit_price > 100.0  # above entry

    def test_build_bracket_sell(self):
        from core.trading.broker import OrderSide
        from core.trading.order_builder import OrderBuilder
        from core.trading.position_sizer import PositionSize

        ob = OrderBuilder()
        size = PositionSize(
            shares=40,
            notional_value=4000.0,
            risk_per_share=5.0,
            stop_loss_price=105.0,
            size_reason="test",
        )
        bracket = ob.build_bracket_order("AAPL", OrderSide.SELL, size)
        assert bracket is not None
        assert bracket.entry.side == OrderSide.SELL
        assert bracket.stop_loss.side == OrderSide.BUY
        assert bracket.stop_loss.stop_price > 105.0
        assert bracket.take_profit.side == OrderSide.BUY
        assert bracket.take_profit.limit_price < 100.0

    def test_build_bracket_zero_shares_returns_none(self):
        from core.trading.broker import OrderSide
        from core.trading.order_builder import OrderBuilder
        from core.trading.position_sizer import PositionSize

        ob = OrderBuilder()
        size = PositionSize(
            shares=0,
            notional_value=0,
            risk_per_share=0,
            stop_loss_price=95.0,
            size_reason="blocked",
        )
        assert ob.build_bracket_order("AAPL", OrderSide.BUY, size) is None

    def test_build_bracket_custom_take_profit(self):
        from core.trading.order_builder import OrderBuilder
        from core.trading.broker import OrderSide
        from core.trading.position_sizer import PositionSize

        ob = OrderBuilder()
        size = PositionSize(
            shares=40,
            notional_value=4000.0,
            risk_per_share=5.0,
            stop_loss_price=95.0,
            size_reason="test",
        )
        bracket = ob.build_bracket_order(
            "AAPL",
            OrderSide.BUY,
            size,
            take_profit_price=120.0,
        )
        assert bracket is not None
        assert bracket.take_profit is not None
        assert bracket.take_profit.limit_price > 120.0  # slippage added

    def test_bracket_default_tp_is_2x_risk(self):
        from core.trading.broker import OrderSide
        from core.trading.order_builder import OrderBuilder
        from core.trading.position_sizer import PositionSize

        ob = OrderBuilder(default_take_profit_ratio=2.0)
        # entry=100, stop=95, risk=5, expected TP=100+5*2=110
        size = PositionSize(
            shares=40,
            notional_value=4000.0,
            risk_per_share=5.0,
            stop_loss_price=95.0,
            size_reason="test",
        )
        bracket = ob.build_bracket_order("AAPL", OrderSide.BUY, size)
        assert bracket is not None
        tp_price = bracket.take_profit.limit_price
        assert tp_price >= 110.0  # 110 + slippage


# ── Integration: OrderBuilder → SimulatedBroker ─────────────────────────────


class TestOrderBuilderBrokerIntegration:
    def test_build_and_submit_market(self):
        from core.trading.broker import OrderSide, OrderStatus, SimulatedBroker
        from core.trading.order_builder import OrderBuilder
        from core.trading.position_sizer import PositionSize

        broker = SimulatedBroker(initial_equity=100000)
        ob = OrderBuilder()
        size = PositionSize(
            shares=10,
            notional_value=1000.0,
            risk_per_share=5.0,
            stop_loss_price=95.0,
            size_reason="test",
        )
        order = ob.build_market_order("AAPL", OrderSide.BUY, size)
        assert order is not None
        filled = broker.submit_order(order)
        assert filled.status == OrderStatus.FILLED

    def test_build_bracket_submit_entry_only(self):
        from core.trading.broker import OrderSide, OrderStatus, SimulatedBroker
        from core.trading.order_builder import OrderBuilder
        from core.trading.position_sizer import PositionSize

        broker = SimulatedBroker(initial_equity=100000)
        ob = OrderBuilder()
        size = PositionSize(
            shares=10,
            notional_value=1000.0,
            risk_per_share=5.0,
            stop_loss_price=95.0,
            size_reason="test",
        )
        bracket = ob.build_bracket_order("AAPL", OrderSide.BUY, size)
        assert bracket is not None
        filled = broker.submit_order(bracket.entry)
        assert filled.status == OrderStatus.FILLED
