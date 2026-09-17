"""As-traded Yahoo chart → Heart OHLCV CSV. Close is quote.close, never adjclose."""

from __future__ import annotations

from pathlib import Path

import httpx

from core.heart.yahoo_chart import (
    bars_from_chart_payload,
    write_as_traded_csv,
)

CHART_TWO_DAYS = {
    "chart": {
        "result": [
            {
                "meta": {"symbol": "GDX", "exchangeName": "NYSEArca"},
                "timestamp": [1584316800, 1584403200],
                "indicators": {
                    "quote": [
                        {
                            "open": [20.0, 21.0],
                            "high": [21.0, 22.0],
                            "low": [19.0, 20.0],
                            "close": [20.5, 18.0],
                            "volume": [1000, 2000],
                        }
                    ],
                    "adjclose": [{"adjclose": [10.25, 9.0]}],
                },
            }
        ],
        "error": None,
    }
}


def test_bars_use_raw_close_not_adjclose():
    bars = bars_from_chart_payload(CHART_TWO_DAYS)
    assert [b["close"] for b in bars] == [20.5, 18.0]
    assert all("adjclose" not in b for b in bars)
    assert bars[0]["session_date"] == "2020-03-16"


def test_write_csv_close_column_is_as_traded(tmp_path: Path):
    path = tmp_path / "GDX.csv"
    bars = bars_from_chart_payload(CHART_TWO_DAYS)
    write_as_traded_csv(path, bars)
    text = path.read_text(encoding="utf-8")
    assert "20.5" in text
    assert "10.25" not in text
    assert text.splitlines()[0] == "Date,Open,High,Low,Close,Volume"


def test_fetch_writes_csv_via_injected_client(tmp_path: Path, monkeypatch):
    from core.heart.yahoo_chart import fetch_and_store

    monkeypatch.setenv("SUPEREZIO_HEART_USER_AGENT", "SuperEzioHeart/1.0 (test@example.com)")

    def handler(request: httpx.Request) -> httpx.Response:
        assert "GDX" in str(request.url)
        assert "events=split%7Cdiv" in str(request.url) or "events=split|div" in str(request.url)
        return httpx.Response(200, json=CHART_TWO_DAYS)

    client = httpx.Client(transport=httpx.MockTransport(handler), timeout=30.0)
    dest = tmp_path / "ohlcv"
    written = fetch_and_store("GDX", dest, client=client)
    assert written == dest / "GDX.csv"
    assert "20.5" in written.read_text(encoding="utf-8")


def test_fetch_missing_user_agent_raises_403(monkeypatch):
    from core.heart.http import HeartHttpError
    from core.heart.yahoo_chart import fetch_chart_payload

    monkeypatch.delenv("SUPEREZIO_HEART_USER_AGENT", raising=False)
    client = httpx.Client(timeout=30.0)
    try:
        fetch_chart_payload("SPY", client)
        raise AssertionError("expected HeartHttpError")
    except HeartHttpError as exc:
        assert exc.status == 403


def test_fetch_empty_bars_raises_422(tmp_path: Path, monkeypatch):
    from core.heart.http import HeartHttpError
    from core.heart.yahoo_chart import fetch_and_store

    monkeypatch.setenv("SUPEREZIO_HEART_USER_AGENT", "SuperEzioHeart/1.0 (test@example.com)")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"chart": {"result": []}})

    client = httpx.Client(transport=httpx.MockTransport(handler), timeout=30.0)
    try:
        fetch_and_store("EMPTY", tmp_path, client=client)
        raise AssertionError("expected HeartHttpError")
    except HeartHttpError as exc:
        assert exc.status == 422


def test_seed_from_events_counts_failures_without_inventing_bars(tmp_path: Path, monkeypatch):
    from datetime import UTC, datetime

    from core.heart.event_book import MarketEvent
    from core.heart.yahoo_chart import seed_from_events

    monkeypatch.setenv("SUPEREZIO_HEART_USER_AGENT", "SuperEzioHeart/1.0 (test@example.com)")

    events = [
        MarketEvent(
            identity="nyse-halt:GOOD:2026-09-16T15:00:00-04:00",
            source="nyse_halts",
            event_type="nyse.luld_pause",
            occurred_at=datetime(2026, 9, 16, 19, 0, tzinfo=UTC),
            timestamp_precision="second",
            symbol="GOOD",
            mic_code="XNAS",
        ),
        MarketEvent(
            identity="nyse-halt:BAD:2026-09-16T15:01:00-04:00",
            source="nyse_halts",
            event_type="nyse.luld_pause",
            occurred_at=datetime(2026, 9, 16, 19, 1, tzinfo=UTC),
            timestamp_precision="second",
            symbol="BAD",
            mic_code="XNAS",
        ),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        if "GOOD" in str(request.url):
            return httpx.Response(200, json=CHART_TWO_DAYS)
        return httpx.Response(404, content=b"missing")

    client = httpx.Client(transport=httpx.MockTransport(handler), timeout=30.0)
    result = seed_from_events(events, tmp_path, client=client, limit=3)
    assert result["stored"] == [{"symbol": "GOOD", "mic_code": "XNAS"}]
    assert len(result["failed"]) == 1
    assert result["failed"][0]["symbol"] == "BAD"
    assert result["failed"][0]["mic_code"] == "XNAS"
    assert result["skipped"] == []
    assert result["rate_limited"] is False
    assert (tmp_path / "GOOD.csv").exists()
    assert not (tmp_path / "BAD.csv").exists()


def test_seed_from_events_skips_existing_csv(tmp_path: Path, monkeypatch):
    from datetime import UTC, datetime

    from core.heart.event_book import MarketEvent
    from core.heart.yahoo_chart import seed_from_events, write_as_traded_csv

    monkeypatch.setenv("SUPEREZIO_HEART_USER_AGENT", "SuperEzioHeart/1.0 (test@example.com)")

    write_as_traded_csv(
        tmp_path / "HAVE.csv",
        bars_from_chart_payload(CHART_TWO_DAYS),
    )

    events = [
        MarketEvent(
            identity="nyse-halt:HAVE:2026-09-16T15:00:00-04:00",
            source="nyse_halts",
            event_type="nyse.luld_pause",
            occurred_at=datetime(2026, 9, 16, 19, 0, tzinfo=UTC),
            timestamp_precision="second",
            symbol="HAVE",
            mic_code="XNAS",
        ),
        MarketEvent(
            identity="nyse-halt:NEW:2026-09-16T15:01:00-04:00",
            source="nyse_halts",
            event_type="nyse.luld_pause",
            occurred_at=datetime(2026, 9, 16, 19, 1, tzinfo=UTC),
            timestamp_precision="second",
            symbol="NEW",
            mic_code="XNAS",
        ),
    ]

    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, json=CHART_TWO_DAYS)

    client = httpx.Client(transport=httpx.MockTransport(handler), timeout=30.0)
    result = seed_from_events(events, tmp_path, client=client, limit=3)
    assert result["skipped"] == [{"symbol": "HAVE", "mic_code": "XNAS"}]
    assert result["stored"] == [{"symbol": "NEW", "mic_code": "XNAS"}]
    assert result["failed"] == []
    assert len(calls) == 1
    assert "NEW" in calls[0]
    assert "HAVE" not in calls[0]


def test_seed_from_events_stops_on_rate_limit(tmp_path: Path, monkeypatch):
    from datetime import UTC, datetime

    from core.heart.event_book import MarketEvent
    from core.heart.yahoo_chart import seed_from_events

    monkeypatch.setenv("SUPEREZIO_HEART_USER_AGENT", "SuperEzioHeart/1.0 (test@example.com)")

    events = [
        MarketEvent(
            identity=f"nyse-halt:SYM{i}:2026-09-16T15:00:00-04:00",
            source="nyse_halts",
            event_type="nyse.luld_pause",
            occurred_at=datetime(2026, 9, 16, 19, i, tzinfo=UTC),
            timestamp_precision="second",
            symbol=f"SYM{i}",
            mic_code="XNAS",
        )
        for i in range(3)
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, content=b"rate limited")

    client = httpx.Client(transport=httpx.MockTransport(handler), timeout=30.0)
    result = seed_from_events(events, tmp_path, client=client, limit=5)
    assert result["rate_limited"] is True
    assert len(result["failed"]) == 1
    assert result["stored"] == []
    assert not any(tmp_path.glob("*.csv"))
