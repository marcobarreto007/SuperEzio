"""Interactive Brokers adapter — implements BrokerAdapter protocol via ib_insync.

Requires: pip install ib-insync
Env vars: IBKR_HOST (default 127.0.0.1), IBKR_PORT (default 7497),
          IBKR_CLIENT_ID (default 1)
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


class InteractiveBrokersAdapter:
    """IBKR broker adapter using ib_insync.

    Implements the BrokerAdapter protocol: submit_order, cancel_order,
    get_order, get_positions, get_account_equity.

    Lazy-connects on first API call. Handles connection errors gracefully
    (returns zero/empty instead of crashing).
    """

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        client_id: int | None = None,
    ):
        self._host = host or os.getenv("IBKR_HOST", "127.0.0.1")
        self._port = port or int(os.getenv("IBKR_PORT", "7497"))
        self._client_id = client_id or int(os.getenv("IBKR_CLIENT_ID", "1"))
        self._ib: Any = None
        self._connected = False

    def _connect(self) -> bool:
        if self._connected and self._ib is not None:
            return True
        try:
            from ib_insync import IB  # type: ignore[import]

            self._ib = IB()
            self._ib.connect(self._host, self._port, clientId=self._client_id)
            self._connected = True
            logger.info(
                "IBKR connected: %s:%s (client %s)",
                self._host,
                self._port,
                self._client_id,
            )
            return True
        except ImportError:
            logger.warning("ib_insync not installed — IBKR adapter disabled")
            return False
        except Exception as exc:
            logger.warning("IBKR connection failed: %s", exc)
            self._connected = False
            return False

    def submit_order(self, order: Any) -> Any:
        from core.trading.broker import Order, OrderSide, OrderType, OrderStatus

        if not self._connect():
            return Order(
                id="ibkr-error",
                symbol=order.symbol,
                side=order.side,
                order_type=order.order_type,
                qty=order.qty,
                status=OrderStatus.REJECTED,
            )

        try:
            from ib_insync import Stock, MarketOrder, LimitOrder, StopOrder as IbStop  # type: ignore[import]

            contract = Stock(order.symbol, "SMART", "USD")

            if order.order_type == OrderType.MARKET:
                ib_order = MarketOrder(
                    "BUY" if order.side == OrderSide.BUY else "SELL",
                    order.qty,
                )
            elif order.order_type == OrderType.LIMIT and order.limit_price:
                ib_order = LimitOrder(
                    "BUY" if order.side == OrderSide.BUY else "SELL",
                    order.qty,
                    order.limit_price,
                )
            elif order.order_type == OrderType.STOP and order.stop_price:
                ib_order = IbStop(
                    "BUY" if order.side == OrderSide.BUY else "SELL",
                    order.qty,
                    order.stop_price,
                )
            else:
                return Order(
                    id="ibkr-unsupported",
                    symbol=order.symbol,
                    side=order.side,
                    order_type=order.order_type,
                    qty=order.qty,
                    status=OrderStatus.REJECTED,
                )

            trade = self._ib.placeOrder(contract, ib_order)
            trade_id = str(trade.order.orderId)

            return Order(
                id=trade_id,
                symbol=order.symbol,
                side=order.side,
                order_type=order.order_type,
                qty=order.qty,
                status=OrderStatus.SUBMITTED,
                limit_price=order.limit_price,
                stop_price=order.stop_price,
            )
        except Exception as exc:
            logger.warning("IBKR submit_order failed: %s", exc)
            return Order(
                id="ibkr-error",
                symbol=order.symbol,
                side=order.side,
                order_type=order.order_type,
                qty=order.qty,
                status=OrderStatus.REJECTED,
            )

    def cancel_order(self, order_id: str) -> bool:
        if not self._connect():
            return False
        try:
            for trade in self._ib.trades():
                if str(trade.order.orderId) == order_id:
                    self._ib.cancelOrder(trade.order)
                    return True
            return False
        except Exception as exc:
            logger.warning("IBKR cancel_order failed: %s", exc)
            return False

    def get_order(self, order_id: str) -> Any | None:
        if not self._connect():
            return None
        from core.trading.broker import Order, OrderSide, OrderType, OrderStatus

        try:
            for trade in self._ib.trades():
                if str(trade.order.orderId) == order_id:
                    return Order(
                        id=str(trade.order.orderId),
                        symbol=trade.contract.symbol,
                        side=(OrderSide.BUY if trade.order.action == "BUY" else OrderSide.SELL),
                        order_type=OrderType.MARKET,
                        qty=trade.order.totalQuantity,
                        status=OrderStatus.SUBMITTED,
                        filled_price=(
                            float(trade.orderStatus.avgFillPrice)
                            if trade.orderStatus.avgFillPrice
                            else None
                        ),
                    )
            return None
        except Exception:
            return None

    def get_positions(self) -> list[Any]:
        if not self._connect():
            return []
        from core.trading.broker import Position

        try:
            positions = self._ib.positions()
            result = []
            for p in positions:
                result.append(
                    Position(
                        symbol=p.contract.symbol,
                        qty=float(p.position),
                        side="LONG" if p.position > 0 else "SHORT",
                        entry_price=float(p.avgCost) if p.avgCost else 0.0,
                        current_price=0.0,
                        unrealized_pnl=0.0,
                        market_value=float(p.position) * (float(p.avgCost) if p.avgCost else 0.0),
                    )
                )
            return result
        except Exception as exc:
            logger.warning("IBKR get_positions failed: %s", exc)
            return []

    def get_account_equity(self) -> float:
        if not self._connect():
            return 0.0
        try:
            summary = self._ib.accountSummary()
            for item in summary:
                if item.tag == "NetLiquidation":
                    return float(item.value)
            return 0.0
        except Exception as exc:
            logger.warning("IBKR get_account_equity failed: %s", exc)
            return 0.0
