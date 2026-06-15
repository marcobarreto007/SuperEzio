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
