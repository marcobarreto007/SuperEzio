from core.sentiment.live_monitor import LiveMonitor, _extract_tickers_from_article
from core.sentiment.curator import SentimentCurator
from core.sentiment.watchlist_pulse import WatchlistPulse


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


class FakeDiscoveryHub:
    def __init__(self):
        self.news_queries = []
        self.providers = {
            "newsapi": FakeProvider(
                {
                    "AAPL": {
                        "source": "newsapi",
                        "sentiment_label": "NEUTRAL",
                        "sentiment_score": 0.01,
                    },
                    "SNDL": {
                        "source": "newsapi",
                        "sentiment_label": "BULLISH",
                        "sentiment_score": 0.35,
                        "news_count": 2,
                    },
                }
            ),
            "news_scout": FakeProvider(
                {
                    "AAPL": {
                        "source": "news_scout",
                        "sentiment_label": "NEUTRAL",
                        "sentiment_score": 0.01,
                    },
                    "SNDL": {
                        "source": "news_scout",
                        "sentiment_label": "BULLISH",
                        "sentiment_score": 0.4,
                        "news_count": 2,
                    },
                }
            ),
            "reddit_pulse": FakeProvider(
                {
                    "AAPL": {"signal_label": "NO_DATA", "total_posts": 0},
                    "SNDL": {
                        "signal_label": "BULLISH",
                        "sentiment_score": 0.25,
                        "total_posts": 18,
                        "qualified_count": 4,
                    },
                }
            ),
            "finnhub": FakeProvider(
                {
                    "AAPL": [{"title": "AAPL market recap"}],
                    "SNDL": [{"title": "SNDL cannabis penny stock volume jumps"}],
                }
            ),
        }

    def get_provider(self, name):
        return self.providers.get(name)

    def get_news(self, query, limit=10):
        self.news_queries.append((query, limit))
        return [
            {
                "title": "SNDL rips higher as cannabis penny stock chatter spikes",
                "source": "Benzinga",
                "url": "https://example.test/sndl",
            }
        ]

    def get_sentiment_summary(self, ticker):
        return self.providers["news_scout"].get_sentiment_summary(ticker)

    def get_reddit_signal(self, ticker):
        return self.providers["reddit_pulse"].get_signal(ticker)


class FakeNewsScoutDiscoveryProvider(FakeProvider):
    def __init__(self, payloads):
        super().__init__(payloads)
        self.news_queries = []

    def get_news(self, query, limit=10):
        self.news_queries.append((query, limit))
        return [
            {
                "title": "SNDL gains on renewed retail cannabis chatter",
                "source": "NewsScout",
            }
        ]


class FakeProviderDiscoveryHub(FakeDiscoveryHub):
    def __init__(self):
        super().__init__()
        self.news_scout = FakeNewsScoutDiscoveryProvider(self.providers["news_scout"].payloads)
        self.providers["news_scout"] = self.news_scout
        self.route_news_called = False

    def get_news(self, query, limit=10):
        self.route_news_called = True
        raise AssertionError("broad discovery must not use paid DataHub news route first")


def test_live_monitor_discovers_market_tickers_and_exposes_origin(tmp_path):
    hub = FakeDiscoveryHub()
    monitor = LiveMonitor(
        ["AAPL"],
        data_hub=hub,
        db_path=tmp_path / "sentiment.db",
        discovery_enabled=True,
        discovery_queries=["penny stock chatter"],
        max_discovered=3,
    )

    monitor.collect_once()
    report = WatchlistPulse(monitor, SentimentCurator()).get_pulse("SNDL").to_dict()

    assert hub.news_queries == [("penny stock chatter", 10)]
    assert "SNDL" in monitor.watchlist
    assert report["origin"] == "discovered"
    assert report["discovered"] is True
    assert report["discovery"]["headline"] == "SNDL rips higher as cannabis penny stock chatter spikes"
    assert report["reddit"]["mentions"] == 18
    assert report["analyst_score"] > 0


def test_live_monitor_prefers_news_scout_for_broad_discovery(tmp_path):
    hub = FakeProviderDiscoveryHub()
    monitor = LiveMonitor(
        ["AAPL"],
        data_hub=hub,
        db_path=tmp_path / "sentiment.db",
        discovery_enabled=True,
        discovery_queries=["retail cannabis chatter"],
        max_discovered=3,
    )

    monitor.collect_once()

    assert hub.news_scout.news_queries == [("retail cannabis chatter", 10)]
    assert hub.route_news_called is False
    assert "SNDL" in monitor.watchlist


def test_discovery_ticker_extractor_filters_market_headline_noise():
    noisy = _extract_tickers_from_article(
        {
            "title": (
                "NRIX Q1 2026 Earnings: EPS Misses Estimates as Pre-Revenue "
                "Biotech Stock Declines After 3,568% EBITDA Jump"
            )
        }
    )
    small_cap = _extract_tickers_from_article(
        {"title": "SMALL-CAP MOVERS: AIM ends bruising quarter on the up"}
    )
    source_noise = _extract_tickers_from_article(
        {"title": "Investors Love Lam Research Stock - Shorting OTM Puts - WSJ"}
    )
    explicit_short = _extract_tickers_from_article({"title": "$SA surges after gold update"})

    assert noisy == ["NRIX"]
    assert small_cap == []
    assert source_noise == []
    assert explicit_short == ["SA"]


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
