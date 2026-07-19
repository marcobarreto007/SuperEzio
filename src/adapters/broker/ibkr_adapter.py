"""Interactive Brokers adapter — implements BrokerAdapter protocol via IBKRService.

Requires: pip install ib-insync
Env vars: IBKR_HOST (default 127.0.0.1), IBKR_PORT (default 7497),
          IBKR_SERVICE_CLIENT_ID (default 100, managed by IBKRService)

This adapter now delegates to the IBKRService singleton, which runs ib_insync
in its own daemon thread to avoid event-loop conflicts on Windows.
"""

from __future__ import annotations

import os
from typing import Any

from core.config.logging_config import get_logger

logger = get_logger(__name__)


def _low_level_gate_check(order: Any) -> bool:
    """F51 LOW-LEVEL INVARIANT — Last line of defense before IBKR.

    EVERY order reaching this adapter MUST carry proof of gate passage.
    If ANY field is missing, the order is REJECTED with BLOCKED_LOW_LEVEL_UNGATED_ORDER.

    Required fields on the order object or its metadata:
      - gate_status == "ALLOW"
      - gate_trace_id (non-empty string)
      - validated_ticker (non-empty, matches order.symbol)
      - journal_ready == True
      - execution_freeze == False
      - pipeline_prepared == True
      - adaptive_policy_applied == True
      - approval_id (non-empty)
      - consensus_decision in {SUPPORT, NEUTRAL}
      - neural_gate_status == ALLOW
      - neural_model_id (non-empty)
    """
    import socket

    # ── Check order metadata for gate passage proof ──
    order_meta = getattr(order, "gate_metadata", None) or {}
    gate_status = order_meta.get("gate_status", "")
    gate_trace_id = order_meta.get("gate_trace_id", "")
    validated_ticker = order_meta.get("validated_ticker", "")
    journal_ready = order_meta.get("journal_ready", False)
    execution_freeze = order_meta.get("execution_freeze", True)  # default SAFE
    pipeline_prepared = order_meta.get("pipeline_prepared", False)
    adaptive_policy_applied = order_meta.get("adaptive_policy_applied", False)
    approval_id = str(order_meta.get("approval_id") or "")
    consensus_decision = str(order_meta.get("consensus_decision") or "").upper()
    neural_gate_status = str(order_meta.get("neural_gate_status") or "").upper()
    neural_model_id = str(order_meta.get("neural_model_id") or "").strip()

    # 1. gate_status MUST be ALLOW
    if gate_status != "ALLOW":
        logger.error(
            "BLOCKED_LOW_LEVEL_UNGATED_ORDER:missing_gate_status symbol=%s gate_status=%s",
            getattr(order, "symbol", "?"),
            gate_status or "MISSING",
        )
        return False

    # 2. gate_trace_id MUST be present
    if not gate_trace_id:
        logger.error(
            "BLOCKED_LOW_LEVEL_UNGATED_ORDER:missing_gate_trace_id symbol=%s",
            getattr(order, "symbol", "?"),
        )
        return False

    # 3. validated_ticker MUST match order symbol
    order_symbol = str(getattr(order, "symbol", "")).upper()
    if not validated_ticker or validated_ticker.upper() != order_symbol:
        logger.error(
            "BLOCKED_LOW_LEVEL_UNGATED_ORDER:ticker_mismatch symbol=%s validated=%s",
            order_symbol,
            validated_ticker or "MISSING",
        )
        return False

    # 4. journal_ready MUST be True
    if not journal_ready:
        logger.error(
            "BLOCKED_LOW_LEVEL_UNGATED_ORDER:journal_not_ready symbol=%s",
            getattr(order, "symbol", "?"),
        )
        return False

    # 5. execution_freeze MUST be False
    if execution_freeze:
        logger.error(
            "BLOCKED_LOW_LEVEL_UNGATED_ORDER:execution_frozen symbol=%s",
            getattr(order, "symbol", "?"),
        )
        return False

    if not pipeline_prepared or not adaptive_policy_applied:
        logger.error(
            "BLOCKED_LOW_LEVEL_UNGATED_ORDER:pipeline_policy_missing symbol=%s",
            getattr(order, "symbol", "?"),
        )
        return False
    if not approval_id:
        logger.error(
            "BLOCKED_LOW_LEVEL_UNGATED_ORDER:approval_missing symbol=%s",
            getattr(order, "symbol", "?"),
        )
        return False
    if consensus_decision not in {"SUPPORT", "NEUTRAL"}:
        logger.error(
            "BLOCKED_LOW_LEVEL_UNGATED_ORDER:consensus_missing symbol=%s decision=%s",
            getattr(order, "symbol", "?"),
            consensus_decision or "MISSING",
        )
        return False
    if neural_gate_status != "ALLOW" or not neural_model_id:
        logger.error(
            "BLOCKED_LOW_LEVEL_UNGATED_ORDER:neural_gate_missing symbol=%s status=%s model=%s",
            getattr(order, "symbol", "?"),
            neural_gate_status or "MISSING",
            neural_model_id or "MISSING",
        )
        return False

    # ── Environmental checks (defense in depth) ──

    # 6. Env-level freeze (catches cases where metadata is forged)
    env_freeze = os.getenv("F51_TRADING_EXECUTION_FREEZE", "true").strip().lower()
    if env_freeze not in ("0", "false", "no", "off"):
        logger.error("low_level_gate_blocked_env_freeze")
        return False

    # 7. IBKR connectivity
    ibkr_host = os.getenv("IBKR_HOST", "127.0.0.1")
    ibkr_port = int(os.getenv("IBKR_PORT", "7497"))
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2.0)
        s.connect((ibkr_host, ibkr_port))
        s.close()
    except Exception as exc:
        logger.error("low_level_gate_blocked_ibkr_offline: %s:%s — %s", ibkr_host, ibkr_port, exc)
        return False

    # 8. Journal health
    try:
        from core.pipeline.f51_trade_gate import is_journal_healthy

        if not is_journal_healthy():
            logger.error("low_level_gate_blocked_journal_unhealthy")
            return False
    except Exception:
        logger.error("low_level_gate_blocked_journal_unhealthy")
        return False

    return True


class InteractiveBrokersAdapter:
    """IBKR broker adapter using IBKRService.

    Implements the BrokerAdapter protocol: submit_order, cancel_order,
    get_order, get_positions, get_account_equity.

    Delegates to IBKRService singleton for positions/equity (cached).
    Uses a worker-owned IB connection for prepared orders.

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
        """Submit only an F51-gated, approved, adaptively prepared order.

        The isolated worker owns its IB connection, while this adapter remains
        the sole validation boundary for prepared submissions.
        """
        from core.trading.broker import Order, OrderType, OrderStatus
        import json

        # ═══════════════════════════════════════════════════════
        # F51 LOW-LEVEL GATE — Last line of defense
        # ═══════════════════════════════════════════════════════
        if not _low_level_gate_check(order):
            return Order(
                id="ibkr-blocked-ungated-order",
                symbol=order.symbol,
                side=order.side,
                order_type=order.order_type,
                qty=order.qty,
                status=OrderStatus.REJECTED,
            )

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
            from .ibkr_order_worker import run_prepared_order

            result = run_prepared_order(order, host=self._host, port=self._port)

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
                    tws_order_id=str(data.get("tws_order_id"))
                    if data.get("tws_order_id")
                    else None,
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
        """Cancel an open order through the isolated risk-reduction worker."""
        from .ibkr_order_worker import cancel_open_order

        return cancel_open_order(order_id, host=self._host, port=self._port)

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
