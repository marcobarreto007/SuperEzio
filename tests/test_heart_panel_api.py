from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent_server import heart_endpoints as heart
from core.heart.event_book import MarketEvent

ET = ZoneInfo("America/New_York")


def test_killed_spine_row_is_present():
    heart.reset_heart_view_for_test()
    heart.VIEW.moves = [
        {
            "mic_code": "XNAS",
            "symbol": "FTFT",
            "first_seen": "2020-01-02",
            "session_date": "2026-09-14",
            "abnormal_ret": 0.0,
            "gross_ret": -0.23,
            "surprise_q": 0.0,
            "ewma_vol": 0.0,
        }
    ]
    heart.VIEW.events = [
        MarketEvent(
            identity="nyse-halt:FTFT:2026-09-14T14:44:20-04:00",
            source="nyse_halts",
            event_type="nyse.luld_pause",
            occurred_at=datetime(2026, 9, 14, 14, 44, 20, tzinfo=ET),
            timestamp_precision="second",
            symbol="FTFT",
            mic_code="XNAS",
        )
    ]
    heart.VIEW.bars = [
        {"session_date": "2026-09-09", "close": 10.0},
        {"session_date": "2026-09-10", "close": 10.2},
        {"session_date": "2026-09-11", "close": 10.1},
        {"session_date": "2026-09-14", "close": 8.0},
        {"session_date": "2026-09-15", "close": 8.2},
    ]
    app = FastAPI()
    app.router.routes.extend(heart.router.routes)
    client = TestClient(app)
    response = client.get("/api/heart/ranking")
    assert response.status_code == 200
    body = response.json()
    assert body["path_status"] == "killed"
    assert body["path_id"] == "nyse.luld_pause|same_session|gross_return"
    assert len(body["rows"]) == 1
    assert body["rows"][0]["symbol"] == "FTFT"


def test_empty_view_is_empty_rows_not_error():
    heart.reset_heart_view_for_test()
    app = FastAPI()
    app.router.routes.extend(heart.router.routes)
    response = TestClient(app).get("/api/heart/ranking")
    assert response.status_code == 200
    assert response.json()["rows"] == []
    assert response.json()["path_status"] is None
