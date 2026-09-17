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
