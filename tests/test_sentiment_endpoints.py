from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from agent_server.main import app


# ── Autouse fixture: clear JWT_SECRET so tests use dev mode ──
@pytest.fixture(autouse=True)
def _clear_jwt_secret(monkeypatch):
    monkeypatch.setenv("SUPEREZIO_JWT_SECRET", "")


class FakeReport:
    def __init__(self, ticker):
        self.ticker = ticker

    def to_dict(self):
        return {
            "ticker": self.ticker,
            "sentiment": "NEUTRAL",
            "score": 0.0,
            "confidence": 0.5,
        }


class FakePulse:
    def get_all_pulses(self):
        return [FakeReport("TLRY"), FakeReport("AAPL")]

    def get_pulse(self, ticker):
        return FakeReport(ticker)


class FakeMonitor:
    def get_alerts(self, limit=20):
        return [{"type": "SPIKE", "ticker": "TLRY"}][:limit]

    def get_sentiment_snapshot(self, ticker):
        return {
            "ticker": ticker,
            "history_24h": [
                {
                    "ticker": ticker,
                    "sentiment_score": 0.2,
                    "collected_at": datetime.now(UTC).isoformat(),
                }
            ],
        }


def _install_state():
    original_pulse = getattr(app.state, "sentiment_pulse", None)
    original_monitor = getattr(app.state, "sentiment_monitor", None)
    app.state.sentiment_pulse = FakePulse()
    app.state.sentiment_monitor = FakeMonitor()
    return original_pulse, original_monitor


def _restore_state(original_pulse, original_monitor):
    if original_pulse is None:
        delattr(app.state, "sentiment_pulse")
    else:
        app.state.sentiment_pulse = original_pulse
    if original_monitor is None:
        delattr(app.state, "sentiment_monitor")
    else:
        app.state.sentiment_monitor = original_monitor


def test_sentiment_pulse_endpoints():
    original_pulse, original_monitor = _install_state()
    try:
        client = TestClient(app)
        all_response = client.get("/sentiment/pulse")
        one_response = client.get("/sentiment/pulse/TLRY")

        assert all_response.status_code == 200
        assert all_response.json()["count"] == 2
        assert one_response.status_code == 200
        assert one_response.json()["pulse"]["ticker"] == "TLRY"
    finally:
        _restore_state(original_pulse, original_monitor)


def test_sentiment_alerts_and_history_endpoints():
    original_pulse, original_monitor = _install_state()
    try:
        client = TestClient(app)
        alerts = client.get("/sentiment/alerts")
        history = client.get("/sentiment/history/TLRY?hours=24")

        assert alerts.status_code == 200
        assert alerts.json()["alerts"][0]["type"] == "SPIKE"
        assert history.status_code == 200
        assert history.json()["ticker"] == "TLRY"
        assert history.json()["count"] == 1
    finally:
        _restore_state(original_pulse, original_monitor)


def test_sentiment_endpoints_return_503_without_startup_state():
    original_pulse = getattr(app.state, "sentiment_pulse", None)
    original_monitor = getattr(app.state, "sentiment_monitor", None)
    if hasattr(app.state, "sentiment_pulse"):
        delattr(app.state, "sentiment_pulse")
    if hasattr(app.state, "sentiment_monitor"):
        delattr(app.state, "sentiment_monitor")
    try:
        client = TestClient(app)
        response = client.get("/sentiment/pulse")

        assert response.status_code == 503
        assert response.json()["detail"] == "sentiment pulse unavailable"
    finally:
        if original_pulse is not None:
            app.state.sentiment_pulse = original_pulse
        if original_monitor is not None:
            app.state.sentiment_monitor = original_monitor
