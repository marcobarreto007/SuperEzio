"""Isolated IBKR order transport used only after the adapter policy boundary."""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class BrokerTransportResult:
    returncode: int
    stdout: str


def cancel_open_order(order_id: str, *, host: str, port: int) -> bool:
    """Cancel a matching open IBKR order as a risk-reducing operation."""
    ib = None
    try:
        from ib_insync import IB

        try:
            asyncio.get_event_loop()
        except RuntimeError:
            asyncio.set_event_loop(asyncio.new_event_loop())

        ib = IB()
        client_id = int(time.time() * 1000) % 9000 + 100
        ib.connect(host, port, clientId=client_id, timeout=10)
        target = str(order_id or "").strip()
        if not target:
            return False
        for trade in ib.reqAllOpenOrders() or []:
            broker_order = getattr(trade, "order", None)
            if broker_order is None:
                continue
            identifiers = {
                str(getattr(broker_order, "permId", "") or ""),
                str(getattr(broker_order, "orderId", "") or ""),
            }
            if target in identifiers:
                ib.cancelOrder(broker_order)
                ib.sleep(1)
                return True
        return False
    except Exception:
        return False
    finally:
        if ib is not None:
            try:
                ib.disconnect()
            except Exception:
                pass


def run_prepared_order(order: Any, *, host: str, port: int) -> BrokerTransportResult:
    """Place an already-prepared order from the adapter's worker thread."""
    ib = None
    try:
        from ib_insync import IB, LimitOrder, MarketOrder, Stock

        try:
            asyncio.get_event_loop()
        except RuntimeError:
            asyncio.set_event_loop(asyncio.new_event_loop())

        ib = IB()
        client_id = int(time.time() * 1000) % 9000 + 100
        ib.connect(host, port, clientId=client_id, timeout=10)
        contract = Stock(str(order.symbol).upper(), "SMART", "USD")
        ib.qualifyContracts(contract)
        action = "BUY" if str(order.side.value).lower() == "buy" else "SELL"
        broker_order = (
            LimitOrder(action, order.qty, order.limit_price)
            if str(order.order_type.value).lower() == "limit"
            else MarketOrder(action, order.qty)
        )
        broker_order.tif = "GTC"
        trade = ib.placeOrder(contract, broker_order)
        ib.sleep(2)
        payload = {
            "order_id": getattr(trade.order, "permId", 0) or getattr(trade.order, "orderId", 0),
            "perm_id": getattr(trade.order, "permId", 0) or None,
            "tws_order_id": getattr(trade.order, "orderId", 0) or None,
            "client_id": getattr(trade.order, "clientId", client_id),
            "status": str(getattr(trade.orderStatus, "status", "Submitted")),
            "avg_price": float(getattr(trade.orderStatus, "avgFillPrice", 0) or 0),
        }
        return BrokerTransportResult(returncode=0, stdout=json.dumps(payload))
    except Exception as exc:
        return BrokerTransportResult(
            returncode=1,
            stdout=json.dumps({"error": str(exc)[:200]}),
        )
    finally:
        if ib is not None:
            try:
                ib.disconnect()
            except Exception:
                pass
