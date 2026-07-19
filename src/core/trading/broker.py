"""Broker adapter — abstract broker interface with Alpaca paper trading."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Protocol


logger = logging.getLogger(__name__)


class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"
    BRACKET = "bracket"


class OrderStatus(Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


@dataclass(frozen=True)
class Order:
    id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    qty: float
    status: OrderStatus
    limit_price: float | None = None
    stop_price: float | None = None
    take_profit_price: float | None = None
    filled_price: float | None = None
    submitted_at: str = ""
    perm_id: str | None = None
    tws_order_id: str | None = None
    client_id: str | None = None
    gate_metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Position:
    symbol: str
    qty: float
    side: str
    entry_price: float
    current_price: float
    unrealized_pnl: float
    market_value: float


class BrokerAdapter(Protocol):
    """Protocol for broker implementations."""

    def submit_order(self, order: Order) -> Order: ...
    def cancel_order(self, order_id: str) -> bool: ...
    def get_order(self, order_id: str) -> Order | None: ...
    def get_positions(self) -> list[Position]: ...
    def get_account_equity(self) -> float: ...


class AlpacaPaperAdapter:
    """Alpaca paper trading broker adapter.

    Requires: pip install alpaca-py
    Env vars: ALPACA_API_KEY, ALPACA_SECRET_KEY (paper trading keys)
    """

    def __init__(
        self,
        api_key: str | None = None,
        secret_key: str | None = None,
        paper: bool = True,
    ):
        self.api_key = api_key or os.getenv("ALPACA_API_KEY", "")
        self.secret_key = secret_key or os.getenv("ALPACA_SECRET_KEY", "")
        self.paper = paper
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from alpaca.trading.client import TradingClient

                self._client = TradingClient(
                    api_key=self.api_key,
                    secret_key=self.secret_key,
                    paper=self.paper,
                )
            except ImportError:
                raise ImportError("alpaca-py not installed. Run: pip install alpaca-py")
        return self._client

    def submit_order(self, order: Order) -> Order:
        from alpaca.trading.requests import (
            MarketOrderRequest,
            LimitOrderRequest,
            StopOrderRequest,
            StopLimitOrderRequest,
        )
        from alpaca.trading.enums import OrderSide as AlpacaSide, TimeInForce

        client = self._get_client()
        side = AlpacaSide.BUY if order.side == OrderSide.BUY else AlpacaSide.SELL

        if order.order_type == OrderType.MARKET:
            req = MarketOrderRequest(
                symbol=order.symbol,
                qty=order.qty,
                side=side,
                time_in_force=TimeInForce.DAY,
            )
        elif order.order_type == OrderType.LIMIT and order.limit_price:
            req = LimitOrderRequest(
                symbol=order.symbol,
                qty=order.qty,
                side=side,
                time_in_force=TimeInForce.DAY,
                limit_price=order.limit_price,
            )
        elif order.order_type == OrderType.STOP and order.stop_price:
            req = StopOrderRequest(
                symbol=order.symbol,
                qty=order.qty,
                side=side,
                time_in_force=TimeInForce.DAY,
                stop_price=order.stop_price,
            )
        elif order.order_type == OrderType.STOP_LIMIT and order.stop_price and order.limit_price:
            req = StopLimitOrderRequest(
                symbol=order.symbol,
                qty=order.qty,
                side=side,
                time_in_force=TimeInForce.DAY,
                stop_price=order.stop_price,
                limit_price=order.limit_price,
            )
        elif order.order_type == OrderType.BRACKET:
            req = MarketOrderRequest(
                symbol=order.symbol,
                qty=order.qty,
                side=side,
                time_in_force=TimeInForce.DAY,
                take_profit=(
                    {"limit_price": order.take_profit_price} if order.take_profit_price else None
                ),
                stop_loss=({"stop_price": order.stop_price} if order.stop_price else None),
            )
        else:
            raise ValueError(f"Unsupported order type: {order.order_type}")

        result = client.submit_order(req)
        return Order(
            id=result.id,
            symbol=result.symbol,
            side=order.side,
            order_type=order.order_type,
            qty=float(result.qty),
            status=OrderStatus.SUBMITTED,
            limit_price=order.limit_price,
            stop_price=order.stop_price,
            submitted_at=str(result.submitted_at) if result.submitted_at else "",
        )

    def cancel_order(self, order_id: str) -> bool:
        try:
            client = self._get_client()
            client.cancel_order_by_id(order_id)
            return True
        except Exception as exc:
            logger.warning("Cancel order %s failed: %s", order_id, exc)
            return False

    def get_order(self, order_id: str) -> Order | None:
        try:
            client = self._get_client()
            result = client.get_order_by_id(order_id)
            return _alpaca_to_order(result)
        except Exception as exc:
            logger.warning("Alpaca get_order(%s) failed: %s", order_id, exc)
            return None

    def get_positions(self) -> list[Position]:
        try:
            client = self._get_client()
            positions = client.get_all_positions()
            return [_alpaca_to_position(p) for p in positions]
        except Exception as exc:
            logger.warning("Alpaca get_positions failed: %s", exc)
            return []

    def get_account_equity(self) -> float:
        try:
            client = self._get_client()
            account = client.get_account()
            return float(account.equity)
        except Exception as exc:
            # IMPORTANT: returning 0.0 on broker failure is a sentinel, not real equity.
            # Callers MUST check for provider errors before sizing positions.
            logger.warning("Alpaca get_account_equity failed: %s (returning 0.0 sentinel)", exc)
            return 0.0


class SimulatedBroker:
    """In-memory broker for testing — no real API calls."""

    def __init__(self, initial_equity: float = 100000.0):
        self.equity = initial_equity
        self._orders: dict[str, Order] = {}
        self._positions: dict[str, Position] = {}
        self._next_id = 1

    def submit_order(self, order: Order) -> Order:
        order_id = f"sim-{self._next_id}"
        self._next_id += 1
        filled_price = order.limit_price or 100.0  # simplified
        filled = Order(
            id=order_id,
            symbol=order.symbol,
            side=order.side,
            order_type=order.order_type,
            qty=order.qty,
            status=OrderStatus.FILLED,
            limit_price=order.limit_price,
            stop_price=order.stop_price,
            filled_price=filled_price,
        )
        self._orders[order_id] = filled
        return filled

    def cancel_order(self, order_id: str) -> bool:
        if order_id in self._orders:
            self._orders[order_id] = Order(
                **{**self._orders[order_id].__dict__, "status": OrderStatus.CANCELLED}
            )
            return True
        return False

    def get_order(self, order_id: str) -> Order | None:
        return self._orders.get(order_id)

    def get_positions(self) -> list[Position]:
        return list(self._positions.values())

    def get_account_equity(self) -> float:
        return self.equity


def _alpaca_to_order(result: Any) -> Order:
    from alpaca.trading.enums import OrderSide as AlpacaSide

    side = OrderSide.BUY if result.side == AlpacaSide.BUY else OrderSide.SELL
    status_map = {
        "filled": OrderStatus.FILLED,
        "new": OrderStatus.SUBMITTED,
        "partially_filled": OrderStatus.PARTIALLY_FILLED,
        "canceled": OrderStatus.CANCELLED,
        "rejected": OrderStatus.REJECTED,
    }
    status = status_map.get(str(result.status).lower(), OrderStatus.PENDING)
    return Order(
        id=str(result.id),
        symbol=result.symbol,
        side=side,
        order_type=OrderType.MARKET,
        qty=float(result.qty),
        status=status,
        filled_price=float(result.filled_avg_price) if result.filled_avg_price else None,
        submitted_at=str(result.submitted_at) if result.submitted_at else "",
    )


def _alpaca_to_position(p: Any) -> Position:
    return Position(
        symbol=p.symbol,
        qty=float(p.qty),
        side=p.side,
        entry_price=float(p.avg_entry_price),
        current_price=float(p.current_price),
        unrealized_pnl=float(p.unrealized_pl),
        market_value=float(p.market_value),
    )
