from datetime import datetime, timezone

from core.sentiment.curator import SentimentCurator
from core.sentiment.watchlist_pulse import PulseReport, WatchlistPulse


class FakeMonitor:
    watchlist = ["TLRY", "AAPL"]

    def get_sentiment_snapshot(self, ticker):
        if ticker == "AAPL":
            return {"ticker": "AAPL", "sources": {}, "history_24h": []}
        return {
            "ticker": "TLRY",
            "sources": {
                "newsapi": {
                    "source": "newsapi",
                    "sentiment_score": -0.3,
                    "sentiment_label": "BEARISH",
                    "news_count": 8,
                    "top_headline": "TLRY institutional caution rises",
                },
                "reddit_pulse": {
                    "source": "reddit_pulse",
                    "sentiment_score": 0.7,
                    "signal_label": "SPIKE",
                    "total_posts": 340,
                    "avg_mentions": 28,
                    "qualified_count": 5,
                },
            },
            "history_24h": [
                {
                    "ticker": "TLRY",
                    "sentiment_score": 0.3,
                    "collected_at": datetime.now(timezone.utc).isoformat(),
                },
                {
                    "ticker": "TLRY",
                    "sentiment_score": -0.3,
                    "collected_at": datetime.now(timezone.utc).isoformat(),
                },
            ],
        }

    def get_alerts(self, limit=100):
        return [
            {
                "type": "SPIKE",
                "ticker": "TLRY",
                "detected_at": datetime.now(timezone.utc).isoformat(),
            },
            {
                "type": "SWING",
                "ticker": "AAPL",
                "detected_at": datetime.now(timezone.utc).isoformat(),
            },
        ][:limit]


def test_watchlist_pulse_builds_ticker_report():
    pulse = WatchlistPulse(FakeMonitor(), SentimentCurator())

    report = pulse.get_pulse("TLRY")

    assert report.ticker == "TLRY"
    assert report.sentiment in {"BEARISH", "NEUTRAL"}
    assert "was BULLISH" in report.sentiment_display
    assert report.reddit["mentions"] == 340
    assert report.reddit["spike"] is True
    assert report.news["articles"] == 8
    assert "SPIKE" in report.flags
    assert len(report.alerts_24h) == 1
    assert report.alerts_24h[0]["type"] == "SPIKE"


def test_watchlist_pulse_all_pulses_uses_watchlist():
    pulse = WatchlistPulse(FakeMonitor(), SentimentCurator())

    reports = pulse.get_all_pulses()

    assert [report.ticker for report in reports] == ["TLRY", "AAPL"]


def test_pulse_report_to_dict():
    report = PulseReport(
        ticker="AAPL",
        sentiment="NEUTRAL",
        sentiment_display="NEUTRAL flat",
        score=0.0,
        confidence=0.5,
    )

    assert report.to_dict()["sentiment"] == "NEUTRAL"
