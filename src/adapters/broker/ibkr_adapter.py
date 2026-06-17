"""Interactive Brokers adapter — implements BrokerAdapter protocol via IBKRService.

Requires: pip install ib-insync
Env vars: IBKR_HOST (default 127.0.0.1), IBKR_PORT (default 7497),
          IBKR_SERVICE_CLIENT_ID (default 100, managed by IBKRService)

This adapter now delegates to the IBKRService singleton, which runs ib_insync
in its own daemon thread to avoid event-loop conflicts on Windows.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


class InteractiveBrokersAdapter:
    """IBKR broker adapter using IBKRService.

    Implements the BrokerAdapter protocol: submit_order, cancel_order,
    get_order, get_positions, get_account_equity.

    Delegates to IBKRService singleton for positions/equity (cached).
    Uses subprocess for orders (via scripts/_ibkr_order.py) to maintain
    isolation.

    Handles connection errors gracefully (returns zero/empty instead of crashing).
    """

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        client_id: int | None = None,
    ):
        # Config is now managed by IBKRService, but we keep params for compatibility
        self._host = host or os.getenv("IBKR_HOST", "127.0.0.1")
        self._port = port or int(os.getenv("IBKR_PORT", "7497"))
        # client_id is ignored — IBKRService manages its own stable clientId
        self._client_id = client_id or int(os.getenv("IBKR_CLIENT_ID", "1"))

    def _get_service(self):
        """Get the IBKRService singleton."""
        try:
            from .ibkr_service import get_ibkr_service

            return get_ibkr_service()
        except ImportError:
            logger.warning("IBKRService not available")
            return None

    def _connect(self) -> bool:
        """Compatibility method — checks if service is available and connected."""
        service = self._get_service()
        if service is None:
            return False
        status = service.get_status()
        return status.get("connected", False) and status.get("can_read", False)

    def submit_order(self, order: Any) -> Any:
        """Submit order via subprocess (scripts/_ibkr_order.py) for isolation.

        This maintains the existing behavior — orders go through a subprocess
        to avoid event-loop conflicts. The adapter does not use in-process IB().
        """
        from core.trading.broker import Order, OrderSide, OrderType, OrderStatus
        import subprocess
        import sys
        import json
        from pathlib import Path

        # Order submission uses subprocess for isolation (existing pattern)
        order_script = Path(__file__).resolve().parent.parent.parent.parent / "scripts" / "_ibkr_order.py"

        if order.order_type == OrderType.MARKET and os.getenv(
            "SUPEREZIO_IBKR_ALLOW_MARKET_ORDER", "0"
        ).strip().lower() not in {"1", "true", "yes", "on"}:
            logger.warning("IBKR market order blocked by policy: %s", order.symbol)
            return Order(
                id="ibkr-blocked-market-order",
                symbol=order.symbol,
                side=order.side,
                order_type=order.order_type,
                qty=order.qty,
                status=OrderStatus.REJECTED,
            )

        if order.order_type == OrderType.LIMIT and not order.limit_price:
            logger.warning("IBKR limit order rejected without limit_price: %s", order.symbol)
            return Order(
                id="ibkr-missing-limit-price",
                symbol=order.symbol,
                side=order.side,
                order_type=order.order_type,
                qty=order.qty,
                status=OrderStatus.REJECTED,
            )

        try:
            result = subprocess.run(
                [
                    sys.executable,
                    str(order_script),
                    "BUY" if order.side == OrderSide.BUY else "SELL",
                    order.symbol.upper(),
                    str(int(order.qty)),
                    str(order.limit_price or 0),
                ],
                capture_output=True,
                text=True,
                timeout=20,
            )

            if result.returncode == 0 and result.stdout:
                data = json.loads(result.stdout.strip())
                if "error" in data:
                    return Order(
                        id=f"ibkr-error-{data.get('error', '')[:20]}",
                        symbol=order.symbol,
                        side=order.side,
                        order_type=order.order_type,
                        qty=order.qty,
                        status=OrderStatus.REJECTED,
                    )
                status_map = {
                    "submitted": OrderStatus.SUBMITTED,
                    "presubmitted": OrderStatus.SUBMITTED,
                    "pendingsubmit": OrderStatus.SUBMITTED,
                    "filled": OrderStatus.FILLED,
                    "partiallyfilled": OrderStatus.PARTIALLY_FILLED,
                    "cancelled": OrderStatus.CANCELLED,
                    "canceled": OrderStatus.CANCELLED,
                    "rejected": OrderStatus.REJECTED,
                }
                status_key = str(data.get("status") or "").replace(" ", "").lower()
                broker_order_id = str(
                    data.get("perm_id") or data.get("order_id") or "ibkr-submitted"
                )
                return Order(
                    id=broker_order_id,
                    symbol=order.symbol,
                    side=order.side,
                    order_type=order.order_type,
                    qty=order.qty,
                    status=status_map.get(status_key, OrderStatus.SUBMITTED),
                    limit_price=order.limit_price,
                    stop_price=order.stop_price,
                    filled_price=data.get("avg_price") or None,
                    perm_id=str(data.get("perm_id")) if data.get("perm_id") else None,
                    tws_order_id=str(data.get("tws_order_id")) if data.get("tws_order_id") else None,
                    client_id=str(data.get("client_id")) if data.get("client_id") else None,
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
        """Cancel order via subprocess (existing pattern)."""
        import subprocess
        import sys
        from pathlib import Path

        order_script = Path(__file__).resolve().parent.parent.parent.parent / "scripts" / "_ibkr_order.py"
        try:
            result = subprocess.run(
                [sys.executable, str(order_script), "cancel", order_id],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.returncode == 0
        except Exception as exc:
            logger.warning("IBKR cancel_order failed: %s", exc)
            return False

    def get_order(self, order_id: str) -> Any | None:
        """Get order status from IBKRService (cached open orders)."""
        service = self._get_service()
        if service is None:
            return None

        from core.trading.broker import Order, OrderSide, OrderType, OrderStatus

        try:
            for order_dict in service.get_open_orders():
                if order_dict.get("order_id") == order_id:
                    action_str = order_dict.get("action", "BUY").upper()
                    return Order(
                        id=order_id,
                        symbol=order_dict.get("ticker", ""),
                        side=OrderSide.BUY if action_str == "BUY" else OrderSide.SELL,
                        order_type=OrderType.MARKET,  # Simplified
                        qty=int(order_dict.get("qty", 0)),
                        status=OrderStatus.SUBMITTED,
                        filled_price=None,
                    )
        except Exception as exc:
            logger.warning("IBKR get_order failed: %s", exc)
        return None

    def get_market_price(self, symbol: str) -> float:
        """Get market price from IBKRService cached positions."""
        service = self._get_service()
        if service is None:
            return 0.0

        try:
            for pos in service.get_positions():
                if pos.get("symbol") == symbol.upper():
                    return float(pos.get("current_price", 0))
        except Exception as exc:
            logger.warning("IBKR get_market_price failed for %s: %s", symbol, exc)
        return 0.0

    def get_positions(self) -> list[Any]:
        """Get positions from IBKRService (cached)."""
        service = self._get_service()
        if service is None:
            return []

        from core.trading.broker import Position

        try:
            positions = []
            for pos_dict in service.get_positions():
                symbol = pos_dict.get("symbol", "")
                qty = float(pos_dict.get("quantity", 0))
                entry_price = float(pos_dict.get("avg_cost", 0))
                current_price = float(pos_dict.get("current_price", entry_price))
                market_value = float(pos_dict.get("market_value", 0))

                if qty > 0:
                    unrealized_pnl = (current_price - entry_price) * qty
                else:
                    unrealized_pnl = (entry_price - current_price) * qty

                positions.append(
                    Position(
                        symbol=symbol,
                        qty=qty,
                        side="LONG" if qty > 0 else "SHORT",
                        entry_price=entry_price,
                        current_price=current_price,
                        unrealized_pnl=unrealized_pnl,
                        market_value=market_value,
                    )
                )
            return positions
        except Exception as exc:
            logger.warning("IBKR get_positions failed: %s", exc)
            return []

    def get_account_equity(self) -> float:
        """Get account equity from IBKRService (cached)."""
        service = self._get_service()
        if service is None:
            return 0.0

        try:
            return service.get_account_equity()
        except Exception as exc:
            logger.warning("IBKR get_account_equity failed: %s", exc)
            return 0.0
