"""SCAN-RT-2 — price enrich must not storm the hub or count timeouts as exception.

Stub hub only (sleep / raise). No network.
"""

from __future__ import annotations

import sys
import threading
import time
import types

import pytest

TICKERS = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AMD"]


def _price_provider_counts(result: dict) -> dict[str, int]:
    for line in result.get("source_errors") or []:
        text = str(line)
        if text.startswith("price_provider:"):
            body = text.split(":", 1)[1]
            counts: dict[str, int] = {}
            for part in body.split(","):
                key, _, raw = part.strip().partition("=")
                if key and raw.isdigit():
                    counts[key] = int(raw)
            return counts
    return {}


def _assert_exception_not_dominant(counts: dict[str, int]) -> None:
    exception_n = counts.get("exception", 0)
    others = sum(v for k, v in counts.items() if k != "exception")
    assert exception_n == 0 or exception_n < others, counts


class _StubHub:
    def __init__(self, *, delay: float = 0.0, boom: bool = False) -> None:
        self.delay = delay
        self.boom = boom
        self.current = 0
        self.max_seen = 0
        self.calls = 0
        self._lock = threading.Lock()

    def get_price(self, ticker, market=None):
        with self._lock:
            self.calls += 1
            self.current += 1
            self.max_seen = max(self.max_seen, self.current)
        try:
            if self.boom:
                raise RuntimeError("hub_down")
            if self.delay:
                time.sleep(self.delay)
            return {"error": "no_quote"}
        finally:
            with self._lock:
                self.current -= 1

    def list_routes(self, capability=None):
        return [{"name": "stub", "configured": True}]


def _install_scan_stubs(monkeypatch, hub: _StubHub, tickers: list[str] | None = None) -> None:
    from src.core import scanner as scanner_module

    symbols = list(tickers or TICKERS)

    class StubScanner:
        def scan_equities(self, country=None, sector=None, industry=None, limit=10):
            return symbols[: int(limit or len(symbols))]

    monkeypatch.setattr(scanner_module, "MarketScanner", StubScanner)
    monkeypatch.setitem(sys.modules, "data.data_hub", types.SimpleNamespace(hub=hub))
    monkeypatch.setenv("SUPEREZIO_MANGALA_SEED_PATH", "tests/.no_seed.json")
    monkeypatch.setenv("SUPEREZIO_SCAN_ENRICH", "0")
    monkeypatch.setenv("SUPEREZIO_SCAN_LIMIT", "8")
    monkeypatch.setenv("SUPEREZIO_SCAN_MAX_TOTAL", "8")
    monkeypatch.setenv("SUPEREZIO_SCAN_PRICE_ENRICH", "8")
    try:
        import src.core.scanner.openbb_scanner as _obb_mod

        monkeypatch.setattr(_obb_mod, "_OPENBB_AVAILABLE", False)
    except ImportError:
        pass


@pytest.mark.asyncio
async def test_per_item_timeout_is_enrich_timeout_not_exception(monkeypatch):
    from src.core.pipeline.nodes.collector import _run_scan

    hub = _StubHub(delay=0.25)
    _install_scan_stubs(monkeypatch, hub)
    monkeypatch.setenv("SUPEREZIO_SCAN_ENRICH_TIMEOUT_MS", "50")
    monkeypatch.setenv("SUPEREZIO_SCAN_STAGE_DEADLINE_MS", "8000")
    monkeypatch.setenv("SUPEREZIO_SCAN_PRICE_CONCURRENCY", "2")

    result = await _run_scan(
        "What stock would you recommend if I want to profit within the next 2 weeks?",
        {"country": "United States"},
    )

    summary = result["rejection_summary"]
    counts = _price_provider_counts(result)
    assert "missing_price" in summary
    assert summary["missing_price"] >= 1
    assert counts.get("enrich_timeout", 0) >= 1
    _assert_exception_not_dominant(counts)
    assert any(r.get("price_error") == "enrich_timeout" for r in result["rejected"])


@pytest.mark.asyncio
async def test_hub_raise_is_price_error_key_not_exception_bucket(monkeypatch):
    from src.core.pipeline.nodes.collector import _run_scan

    hub = _StubHub(boom=True)
    _install_scan_stubs(monkeypatch, hub)
    monkeypatch.setenv("SUPEREZIO_SCAN_ENRICH_TIMEOUT_MS", "2000")
    monkeypatch.setenv("SUPEREZIO_SCAN_STAGE_DEADLINE_MS", "8000")
    monkeypatch.setenv("SUPEREZIO_SCAN_PRICE_CONCURRENCY", "2")

    result = await _run_scan(
        "What stock would you recommend if I want to profit within the next 2 weeks?",
        {"country": "United States"},
    )

    summary = result["rejection_summary"]
    counts = _price_provider_counts(result)
    assert "missing_price" in summary
    assert counts.get("hub_down", 0) >= 1
    _assert_exception_not_dominant(counts)
    assert counts.get("exception", 0) == 0


@pytest.mark.asyncio
async def test_stage_deadline_fail_closed_missing_price_no_crash(monkeypatch):
    from src.core.pipeline.nodes.collector import _run_scan

    hub = _StubHub(delay=0.6)
    _install_scan_stubs(monkeypatch, hub)
    monkeypatch.setenv("SUPEREZIO_SCAN_ENRICH_TIMEOUT_MS", "10000")
    monkeypatch.setenv("SUPEREZIO_SCAN_STAGE_DEADLINE_MS", "150")
    monkeypatch.setenv("SUPEREZIO_SCAN_PRICE_CONCURRENCY", "2")

    result = await _run_scan(
        "What stock would you recommend if I want to profit within the next 2 weeks?",
        {"country": "United States"},
    )

    assert isinstance(result, dict)
    summary = result["rejection_summary"]
    counts = _price_provider_counts(result)
    assert "missing_price" in summary
    assert summary["missing_price"] >= 1
    assert counts.get("stage_abandoned", 0) >= 1
    _assert_exception_not_dominant(counts)
    assert result.get("rejected_count", 0) >= 1
    assert any(r.get("price_error") == "stage_abandoned" for r in result["rejected"])


@pytest.mark.asyncio
async def test_price_stage_default_concurrency_stays_at_two(monkeypatch):
    from src.core.pipeline.nodes.collector import _run_scan

    hub = _StubHub(delay=0.08)
    _install_scan_stubs(monkeypatch, hub)
    monkeypatch.delenv("SUPEREZIO_SCAN_PRICE_CONCURRENCY", raising=False)
    # Profile/catalyst pool may be larger; price stage must not inherit it.
    monkeypatch.setenv("SUPEREZIO_SCAN_ENRICH_CONCURRENCY", "8")
    monkeypatch.setenv("SUPEREZIO_SCAN_ENRICH_TIMEOUT_MS", "5000")
    monkeypatch.setenv("SUPEREZIO_SCAN_STAGE_DEADLINE_MS", "8000")

    result = await _run_scan(
        "What stock would you recommend if I want to profit within the next 2 weeks?",
        {"country": "United States"},
    )

    assert hub.max_seen <= 2
    assert hub.calls >= 1
    summary = result["rejection_summary"]
    counts = _price_provider_counts(result)
    assert "missing_price" in summary or counts
    _assert_exception_not_dominant(counts)


@pytest.mark.asyncio
async def test_derived_deadline_lets_full_price_budget_finish(monkeypatch):
    from src.core.pipeline.nodes.collector import _run_scan

    class _PricedHub(_StubHub):
        def get_price(self, ticker, market=None):
            with self._lock:
                self.calls += 1
                self.current += 1
                self.max_seen = max(self.max_seen, self.current)
            try:
                if self.delay:
                    time.sleep(self.delay)
                return {"price": 12.5, "symbol": ticker, "provider": "stub", "currency": "USD"}
            finally:
                with self._lock:
                    self.current -= 1

    hub = _PricedHub(delay=0.02)
    _install_scan_stubs(monkeypatch, hub)
    monkeypatch.delenv("SUPEREZIO_SCAN_STAGE_DEADLINE_MS", raising=False)
    monkeypatch.setenv("SUPEREZIO_SCAN_ENRICH_TIMEOUT_MS", "2000")
    monkeypatch.setenv("SUPEREZIO_SCAN_PRICE_CONCURRENCY", "2")

    result = await _run_scan(
        "What stock would you recommend if I want to profit within the next 2 weeks?",
        {"country": "United States"},
    )

    counts = _price_provider_counts(result)
    assert hub.calls == 8
    assert counts.get("stage_abandoned", 0) == 0
    _assert_exception_not_dominant(counts)


def test_yfinance_sits_before_paced_price_routes():
    from data.data_hub import DataHub

    hub = DataHub(register_defaults=True)
    ordered = [r["name"] for r in sorted(hub.list_routes("price"), key=lambda x: x["priority"])]
    assert ordered.index("yfinance") < ordered.index("twelve_data")
    assert ordered.index("yfinance") < ordered.index("alpha_vantage")
