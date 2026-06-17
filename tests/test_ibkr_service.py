import asyncio
import sys
import threading
import types
from types import SimpleNamespace

from adapters.broker.ibkr_service import IBKRService


def test_ibkr_service_connect_creates_event_loop_in_worker_thread(monkeypatch):
    class FakeIB:
        def connect(self, *_args, **_kwargs):
            asyncio.get_event_loop()

        def disconnect(self):
            pass

    monkeypatch.setitem(sys.modules, "ib_insync", types.SimpleNamespace(IB=FakeIB))
    service = IBKRService(client_id=321)
    result = {}

    def run_connect():
        result["connected"] = service._connect()
        result["last_error"] = service._last_error

    thread = threading.Thread(target=run_connect, name="pytest-ibkr-worker")
    thread.start()
    thread.join(timeout=2)

    assert result == {"connected": True, "last_error": ""}


def test_ibkr_service_positions_wait_for_worker_cache_instead_of_refreshing_on_request_thread(monkeypatch):
    service = IBKRService(client_id=322)

    def fail_refresh():
        raise AssertionError("request thread must not refresh ib_insync directly")

    monkeypatch.setattr(service, "_refresh", fail_refresh)

    assert service.get_positions(force_refresh=False, wait_timeout=0.01) == []
    assert service.get_account_equity(force_refresh=False, wait_timeout=0.01) == 0.0


def test_ibkr_service_open_orders_uses_req_all_open_orders_and_open_trades(monkeypatch):
    def trade(
        order_id,
        symbol,
        action="BUY",
        qty=10,
        order_type="LMT",
        limit_price=1.23,
        perm_id=0,
        client_id=0,
    ):
        return SimpleNamespace(
            order=SimpleNamespace(
                orderId=order_id,
                permId=perm_id,
                clientId=client_id,
                action=action,
                totalQuantity=qty,
                orderType=order_type,
                lmtPrice=limit_price,
                auxPrice=0,
            ),
            contract=SimpleNamespace(symbol=symbol, localSymbol=symbol),
            orderStatus=SimpleNamespace(status="Submitted"),
        )

    class FakeIB:
        def reqAllOpenOrders(self):
            return [trade(11, "SPY", qty=5), trade(12, "NOK", qty=50, limit_price=4.73)]

        def reqOpenOrders(self):
            return [trade(11, "SPY", qty=5)]

        def sleep(self, _seconds):
            pass

        def openTrades(self):
            return [trade(13, "FCEL", qty=50, limit_price=3.36)]

        def trades(self):
            return [trade(12, "NOK", qty=50, limit_price=4.73)]

    service = IBKRService(client_id=323)
    service._ib = FakeIB()
    service._connected = True

    orders = service.get_open_orders()

    assert [order["ticker"] for order in orders] == ["SPY", "NOK", "FCEL"]
    assert [order["order_id"] for order in orders] == ["11", "12", "13"]
    assert service._open_orders_cache == orders


def test_ibkr_service_open_orders_dedupes_by_perm_id_when_tws_order_id_repeats():
    def trade(perm_id, symbol):
        return SimpleNamespace(
            order=SimpleNamespace(
                orderId=4,
                permId=perm_id,
                clientId=500 + perm_id,
                action="BUY",
                totalQuantity=10,
                orderType="LMT",
                lmtPrice=9.99,
                auxPrice=0,
            ),
            contract=SimpleNamespace(symbol=symbol, localSymbol=symbol),
            orderStatus=SimpleNamespace(status="Submitted"),
        )

    class FakeIB:
        def reqAllOpenOrders(self):
            return [trade(101, "INOD"), trade(102, "FCEL"), trade(103, "NOK")]

        def reqOpenOrders(self):
            return [trade(101, "INOD")]

        def sleep(self, _seconds):
            pass

        def openTrades(self):
            return [trade(102, "FCEL")]

        def trades(self):
            return []

    service = IBKRService(client_id=324)
    service._ib = FakeIB()
    service._connected = True

    orders = service.get_open_orders()

    assert [order["ticker"] for order in orders] == ["INOD", "FCEL", "NOK"]
    assert [order["order_id"] for order in orders] == ["101", "102", "103"]
    assert [order["tws_order_id"] for order in orders] == ["4", "4", "4"]
