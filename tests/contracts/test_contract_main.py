"""Contract tests: agent_server.main â€” FastAPI app creation & startup helpers."""

import os

import pytest
from fastapi import FastAPI


@pytest.fixture(autouse=True)
def _skip_gateway():
    """Prevent edge gateway from trying to connect during tests."""
    os.environ["UNIVERSAL_SKIP_GATEWAY"] = "1"
    yield


def test_fastapi_app_creation():
    from agent_server.main import app

    assert app is not None
    assert app.title is not None
    assert "SuperEzio" in app.title or "A2A" in app.title


def test_fastapi_app_routes():
    from agent_server.main import app

    # Collect all route paths recursively
    paths = set()
    for route in app.routes:
        if hasattr(route, "path"):
            paths.add(route.path)
        if hasattr(route, "routes"):
            for sub_route in route.routes:
                if hasattr(sub_route, "path"):
                    paths.add(sub_route.path)

    assert "/" in paths or any("/api" in p for p in paths)
    assert any("health" in p for p in paths)  # /health always in app routes


def test_env_bool():
    from agent_server.main import _env_bool

    assert _env_bool("NONEXISTENT_VAR_XYZ_123", default=True) is True
    assert _env_bool("NONEXISTENT_VAR_XYZ_123", default=False) is False


def test_app_has_middleware():
    from agent_server.main import app

    # FastAPI middleware is stored in user_middleware list
    assert len(app.user_middleware) >= 1


def test_run_function_exists():
    from agent_server.main import run

    assert callable(run)


def test_sentiment_watchlist_prefers_env(monkeypatch):
    from agent_server.main import _load_sentiment_watchlist

    monkeypatch.setenv("SUPEREZIO_SENTIMENT_WATCHLIST", " tlry, GME,TLRY,brk.b ")

    assert _load_sentiment_watchlist(storage=object()) == ["TLRY", "GME", "BRK.B"]


def test_sentiment_watchlist_loads_from_storage(monkeypatch):
    from agent_server.main import _load_sentiment_watchlist

    class FakeStorage:
        def get_watchlist(self):
            return [{"ticker": "nvda"}, {"ticker": "TSLA"}, {"ticker": "nvda"}]

    monkeypatch.delenv("SUPEREZIO_SENTIMENT_WATCHLIST", raising=False)

    assert _load_sentiment_watchlist(storage=FakeStorage()) == ["NVDA", "TSLA"]


def test_sentiment_services_start_and_stop(monkeypatch):
    import agent_server.main as main

    started = []
    stopped = []

    class FakeMonitor:
        def __init__(self, watchlist, interval_minutes=15, db_path=None):
            self.watchlist = watchlist
            self.interval_minutes = interval_minutes
            self.db_path = db_path

        def start(self):
            started.append((self.watchlist, self.interval_minutes))

        def stop(self):
            stopped.append(self.watchlist)

    class FakeCurator:
        pass

    class FakePulse:
        def __init__(self, monitor, curator):
            self.monitor = monitor
            self.curator = curator

    monkeypatch.setenv("SUPEREZIO_SENTIMENT_WATCHLIST", "TLRY,GME")
    monkeypatch.setenv("SUPEREZIO_SENTIMENT_INTERVAL_MINUTES", "3")
    monkeypatch.setattr(main, "LiveMonitor", FakeMonitor)
    monkeypatch.setattr(main, "SentimentCurator", FakeCurator)
    monkeypatch.setattr(main, "WatchlistPulse", FakePulse)
    app = FastAPI()

    main._start_sentiment_services(app)

    assert started == [(["TLRY", "GME"], 3)]
    assert app.state.sentiment_monitor.watchlist == ["TLRY", "GME"]
    assert app.state.sentiment_pulse.monitor is app.state.sentiment_monitor

    main._stop_sentiment_services(app)

    assert stopped == [["TLRY", "GME"]]
