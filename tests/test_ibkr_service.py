import asyncio
import sys
import threading
import types

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
