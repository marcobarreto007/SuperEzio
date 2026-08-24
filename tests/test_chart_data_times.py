"""Regression: chart OHLCV candles and indicator series must carry real epoch times.

History: the 2026-08-20 checkpoint recorded a critical defect — every candle
returned by /api/chart-data had time=0, collapsing every chart. The provider
shapes the timestamp as an ISO-8601 string under the "datetime" key; the
endpoint normalizes it via _parse_candle_time. These tests pin that contract.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient


def _make_candles(n: int = 30) -> list[dict]:
    base = datetime(2026, 8, 1, tzinfo=timezone.utc)
    return [
        {
            "datetime": (base + timedelta(days=i)).isoformat(),
            "open": 10.0 + i * 0.1,
            "high": 11.0 + i * 0.1,
            "low": 9.5 + i * 0.1,
            "close": 10.5 + i * 0.1,
            "volume": 1000 + i,
        }
        for i in range(n)
    ]


def test_chart_data_candles_have_epoch_times(monkeypatch):
    import agent_server.endpoints as ep

    # This test owns the candle-time contract, not auth: importing
    # agent_server.main runs load_local_env() and leaks the operator's
    # PUBLIC_MODE=1 + secret into the process env (the endpoint would 401).
    # Pin dev-anon mode for the TestClient.
    monkeypatch.delenv("SUPEREZIO_JWT_SECRET", raising=False)
    monkeypatch.setenv("SUPEREZIO_PUBLIC_MODE", "0")
    monkeypatch.setenv("SUPEREZIO_OPEN_ACCESS", "0")

    monkeypatch.setattr(
        ep.hub, "get_candles", lambda ticker, timeframe="6M": {"candles": _make_candles()}
    )
    monkeypatch.setattr(ep.hub, "get_profile", lambda ticker: {"name": "Test Co"})

    from agent_server.main import app

    client = TestClient(app)
    resp = client.get("/api/chart-data/TEST?timeframe=1M")
    assert resp.status_code == 200, resp.text

    body = resp.json()
    times = [candle["time"] for candle in body["ohlcv"]]
    assert len(times) > 0
    assert all(t > 0 for t in times), f"candles with time=0 found: {times[:5]}"

    sma20 = (body.get("indicators") or {}).get("sma20", [])
    sma_times = [point["time"] for point in sma20]
    assert all(t > 0 for t in sma_times), f"sma20 with time=0 found: {sma_times[:5]}"


def test_ohlcv_builder_parses_iso_datetime_and_epoch(monkeypatch):
    from agent_server.endpoints import _build_ohlcv

    candles = [
        {
            "datetime": "2026-08-21T04:00:00+00:00",
            "open": 1,
            "high": 2,
            "low": 0.5,
            "close": 1.5,
            "volume": 10,
        },
        {"time": 1787284800, "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10},
        {"date": "2026-08-19", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10},
    ]
    ohlcv = _build_ohlcv(candles)
    date_epoch = int(
        datetime.strptime("2026-08-19", "%Y-%m-%d").timestamp()
    )  # naive date -> local tz, matches endpoint behavior
    assert [c["time"] for c in ohlcv] == [1787284800, 1787284800, date_epoch]
