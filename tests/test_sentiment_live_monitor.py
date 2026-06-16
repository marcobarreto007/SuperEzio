from core.sentiment.live_monitor import LiveMonitor


class FakeProvider:
    def __init__(self, payloads):
        self.payloads = payloads

    def get_sentiment_summary(self, ticker):
        return dict(self.payloads[ticker])

    def get_signal(self, ticker):
        return dict(self.payloads[ticker])

    def get_news(self, ticker):
        return list(self.payloads.get(ticker, []))


class FakeHub:
    def __init__(self):
        self.providers = {
            "newsapi": FakeProvider({"TLRY": {"source": "newsapi", "sentiment_label": "BULLISH", "sentiment_score": 0.2}}),
            "news_scout": FakeProvider({"TLRY": {"source": "news_scout", "sentiment_label": "BULLISH", "sentiment_score": 0.2}}),
            "reddit_pulse": FakeProvider({"TLRY": {"signal_label": "BULLISH", "total_posts": 20}}),
            "finnhub": FakeProvider({"TLRY": [{"title": "TLRY announces update"}]}),
        }

    def get_provider(self, name):
        return self.providers.get(name)

    def get_sentiment_summary(self, ticker):
        return self.providers["news_scout"].get_sentiment_summary(ticker)

    def get_reddit_signal(self, ticker):
        return self.providers["reddit_pulse"].get_signal(ticker)


def test_live_monitor_collects_snapshot_and_history():
    hub = FakeHub()
    monitor = LiveMonitor(["tlry"], interval_minutes=15, data_hub=hub)

    alerts = monitor.collect_once()
    snapshot = monitor.get_sentiment_snapshot("TLRY")

    assert alerts == []
    assert snapshot["ticker"] == "TLRY"
    assert snapshot["status"] == "ok"
    assert snapshot["sources"]["newsapi"]["sentiment_label"] == "BULLISH"
    assert snapshot["sources"]["finnhub"]["news_count"] == 1
    assert len(snapshot["history_24h"]) == 1


def test_live_monitor_detects_swing_spike_and_coord_alerts():
    hub = FakeHub()
    monitor = LiveMonitor(["TLRY"], data_hub=hub)
    monitor.collect_once()

    hub.providers["newsapi"].payloads["TLRY"] = {
        "source": "newsapi",
        "sentiment_label": "BEARISH",
        "sentiment_score": -0.2,
    }
    hub.providers["news_scout"].payloads["TLRY"] = {
        "source": "news_scout",
        "sentiment_label": "BEARISH",
        "sentiment_score": -0.2,
    }
    hub.providers["reddit_pulse"].payloads["TLRY"] = {
        "signal_label": "BEARISH",
        "total_posts": 90,
        "avg_mentions": 20,
        "new_accounts_same_text": 3,
    }

    alerts = monitor.collect_once()
    types = {alert["type"] for alert in alerts}

    assert {"SWING", "SPIKE", "COORD"}.issubset(types)
    assert monitor.get_alerts(limit=2)[0]["type"] in types


def test_live_monitor_detects_institutional_social_divergence():
    hub = FakeHub()
    hub.providers["newsapi"].payloads["TLRY"] = {
        "source": "newsapi",
        "sentiment_label": "BULLISH",
        "sentiment_score": 0.4,
    }
    hub.providers["reddit_pulse"].payloads["TLRY"] = {
        "signal_label": "BEARISH",
        "total_posts": 12,
    }
    monitor = LiveMonitor(["TLRY"], data_hub=hub)

    alerts = monitor.collect_once()

    divergence = [alert for alert in alerts if alert["type"] == "DIVERGENCE"]
    assert divergence
    assert divergence[0]["institutional"]["newsapi"] == "BULLISH"
    assert divergence[0]["social"] == "BEARISH"


def test_live_monitor_start_stop_uses_daemon_thread():
    monitor = LiveMonitor([], data_hub=FakeHub())

    monitor.start()
    thread = monitor._thread
    monitor.stop()

    assert thread is not None
    assert thread.daemon is True
    assert monitor.running is False


def test_persist_to_db_creates_table_and_inserts_row(tmp_path):
    """D3: Verifica que o snapshot é persistido em SQLite com todas as colunas."""
    import sqlite3

    db_path = tmp_path / "test_sentiment.db"
    monitor = LiveMonitor(watchlist=["AAPL"], interval_minutes=15, db_path=str(db_path))

    snapshot = {
        "ticker": "AAPL",
        "sentiment_score": 0.75,
        "sentiment_label": "BULLISH",
        "reddit": {"mentions": 42},
        "news_count": 5,
        "flags": ["SWING", "SPIKE"],
        "collected_at": "2026-06-16T12:00:00+00:00",
        "sources": {"newsapi": {"sentiment_score": 0.8}},
    }
    monitor._persist_to_db("AAPL", snapshot)

    conn = sqlite3.connect(str(db_path))
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    assert ("sentiment_history",) in tables

    rows = conn.execute(
        "SELECT ticker, score, label, reddit_mentions, news_count, flags "
        "FROM sentiment_history"
    ).fetchall()
    assert len(rows) == 1
    ticker, score, label, mentions, news, flags = rows[0]
    assert ticker == "AAPL"
    assert score == 0.75
    assert label == "BULLISH"
    assert mentions == 42
    assert news == 5
    assert "SWING" in flags

    # snapshot_json must be present and contain the original data
    blob = conn.execute(
        "SELECT snapshot_json FROM sentiment_history WHERE ticker='AAPL'"
    ).fetchone()
    assert blob is not None
    assert "newsapi" in blob[0]

    conn.close()


def test_persist_to_db_non_critical_failure_does_not_raise(tmp_path):
    """D3: Erro no DB não crasha a thread — comportamento non-blocking."""
    monitor = LiveMonitor(
        watchlist=["TSLA"],
        interval_minutes=15,
        db_path=str(tmp_path / "readonly" / "nope.db"),
    )
    # Directory doesn't exist — should fail silently
    monitor._persist_to_db("TSLA", {"ticker": "TSLA"})
    # If we got here without exception, the non-critical contract holds
