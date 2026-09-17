"""IBKR socket stays off the FastAPI loop and keeps a usable error string."""

from __future__ import annotations

from adapters.broker.ibkr_service import IBKRService


def test_connect_refused_on_running_asyncio_loop(monkeypatch):
    service = IBKRService()
    monkeypatch.setattr(IBKRService, "_running_asyncio_loop", staticmethod(lambda: True))
    assert service._connect() is False
    assert "asyncio" in service._last_error
    assert service._ib is None


def test_open_orders_from_request_thread_returns_cache_without_connect(monkeypatch):
    service = IBKRService()
    service._open_orders_cache = [{"ticker": "SPY", "qty": 1}]

    called = {"connect": False}

    def boom() -> bool:
        called["connect"] = True
        raise AssertionError("must not connect off the daemon thread")

    monkeypatch.setattr(service, "_connect_unlocked", boom)
    orders = service.get_open_orders()
    assert called["connect"] is False
    assert orders == [{"ticker": "SPY", "qty": 1}]


def test_format_error_includes_type_when_message_empty():
    class Quiet(Exception):
        def __str__(self) -> str:
            return ""

    text = IBKRService._format_error(Quiet())
    assert text == "Quiet"
