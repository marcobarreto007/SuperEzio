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
    body = response.json()
    assert body["rows"] == []
    assert body["path_id"] == "nyse.luld_pause|same_session|gross_return"
    assert body["path_status"] == heart.EMPTY_OHLCV_STATUS


def test_get_ranking_calls_refresh_outside_pytest(monkeypatch):
    heart.reset_heart_view_for_test()
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    calls: list[tuple] = []

    def fake_refresh(view, *, heart_root, ohlcv_dir):
        calls.append((heart_root, ohlcv_dir))

    monkeypatch.setattr(heart, "refresh_heart_view", fake_refresh)
    app = FastAPI()
    app.router.routes.extend(heart.router.routes)
    response = TestClient(app).get("/api/heart/ranking")
    assert response.status_code == 200
    assert len(calls) == 1
    assert calls[0][0].name == "heart"
    assert calls[0][1].parts[-2:] == ("heart", "ohlcv")


def test_resolve_ohlcv_dir_honors_env(monkeypatch, tmp_path):
    monkeypatch.setenv("SUPEREZIO_HEART_OHLCV_DIR", str(tmp_path / "bars"))
    assert heart.resolve_ohlcv_dir() == tmp_path / "bars"


def test_get_ranking_skips_refresh_under_pytest(monkeypatch):
    heart.reset_heart_view_for_test()
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "tests/test_heart_panel_api.py::test")
    calls: list[tuple] = []

    def fake_refresh(view, *, heart_root, ohlcv_dir):
        calls.append((heart_root, ohlcv_dir))

    monkeypatch.setattr(heart, "refresh_heart_view", fake_refresh)
    app = FastAPI()
    app.router.routes.extend(heart.router.routes)
    TestClient(app).get("/api/heart/ranking")
    assert calls == []


def test_hydrated_empty_moves_returns_honest_empty(monkeypatch, tmp_path):
    heart.reset_heart_view_for_test()
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    def fake_refresh(view, *, heart_root, ohlcv_dir):
        view.moves = []
        view.events = []
        view.bars = []

    monkeypatch.setattr(heart, "refresh_heart_view", fake_refresh)
    app = FastAPI()
    app.router.routes.extend(heart.router.routes)
    body = TestClient(app).get("/api/heart/ranking").json()
    assert body["rows"] == []
    assert body["path_id"] == "nyse.luld_pause|same_session|gross_return"
    assert body["path_status"] == heart.EMPTY_OHLCV_STATUS


def test_ranking_empty_ohlcv_dir_honest_response(tmp_path, monkeypatch):
    heart.reset_heart_view_for_test()
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    heart_root = tmp_path / "heart"
    heart_root.mkdir()
    ohlcv = tmp_path / "ohlcv"
    ohlcv.mkdir()
    monkeypatch.setattr(heart, "DEFAULT_HEART_ROOT", heart_root)
    monkeypatch.setenv("SUPEREZIO_HEART_OHLCV_DIR", str(ohlcv))
    app = FastAPI()
    app.router.routes.extend(heart.router.routes)
    body = TestClient(app).get("/api/heart/ranking").json()
    assert body["rows"] == []
    assert body["path_id"] == "nyse.luld_pause|same_session|gross_return"
    assert body["path_status"] == heart.EMPTY_OHLCV_STATUS
