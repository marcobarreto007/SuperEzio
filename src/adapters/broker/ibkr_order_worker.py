"""Isolated IBKR order transport used only after the adapter policy boundary."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


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
    # Melhor esforco deliberado: transporte IBKR pode falhar (conexao/API);
    # o chamador recebe False com log, nunca excecao.
    except Exception as exc:  # noqa: BLE001
        # Um cancelamento que nao aconteceu precisa deixar rastro: sem log, este
        # False fica indistinguivel de "ordem nao encontrada" no caminho do dinheiro.
        logger.warning("cancel_open_order failed for %s: %s", order_id, exc)
        return False
    finally:
        if ib is not None:
            # Melhor esforco deliberado: desconexao falha nao pode mascarar o
            # resultado principal; loga em debug para rastreio.
            try:
                ib.disconnect()
            except Exception as exc:  # noqa: BLE001
                logger.debug("IBKR disconnect after cancel failed: %s", exc)


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
    # Melhor esforco deliberado: falha de execucao vira payload de erro para o
    # adapter classificar como REJECTED; nunca excecao.
    except Exception as exc:  # noqa: BLE001
        return BrokerTransportResult(
            returncode=1,
            stdout=json.dumps({"error": str(exc)[:200]}),
        )
    finally:
        if ib is not None:
            # Melhor esforco deliberado: desconexao falha nao pode mascarar o
            # resultado principal; loga em debug para rastreio.
            try:
                ib.disconnect()
            except Exception as exc:  # noqa: BLE001
                logger.debug("IBKR disconnect after order failed: %s", exc)
