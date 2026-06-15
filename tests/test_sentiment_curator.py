from datetime import datetime, timedelta, timezone

from core.sentiment.curator import CuratedSentiment, SentimentCurator


def test_sentiment_curator_dedupes_and_prefers_reliable_source():
    curator = SentimentCurator()

    result = curator.curate(
        {
            "newsapi": {
                "ticker": "TLRY",
                "source": "newsapi",
                "sentiment_score": -0.3,
                "sentiment_label": "BEARISH",
                "top_headline": "TLRY Joins European Cannabis Talks",
            },
            "news_scout": {
                "ticker": "TLRY",
                "source": "news_scout",
                "sentiment_score": 0.5,
                "sentiment_label": "BULLISH",
                "top_headline": "TLRY joins European cannabis talks",
            },
        }
    )

    assert result.ticker == "TLRY"
    assert result.top_headline == "TLRY Joins European Cannabis Talks"
    assert result.sources_used == ["newsapi"]
    assert result.label == "BEARISH"


def test_sentiment_curator_applies_weights_expiry_and_reddit_flags():
    old = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    result = SentimentCurator().curate(
        {
            "newsapi": {
                "source": "newsapi",
                "sentiment_score": 0.6,
                "sentiment_label": "BULLISH",
                "top_headline": "Old bullish headline",
                "timestamp": old,
            },
            "finnhub": {
                "source": "finnhub",
                "sentiment_score": -0.4,
                "sentiment_label": "BEARISH",
                "top_headline": "Fresh company announcement",
            },
            "reddit_pulse": {
                "source": "reddit_pulse",
                "sentiment_score": 0.8,
                "signal_label": "SPIKE",
                "total_posts": 340,
                "avg_mentions": 28,
                "new_accounts_same_text": 3,
            },
        }
    )

    assert result.label in {"BEARISH", "NEUTRAL"}
    assert "SPIKE" in result.flags
    assert "POSSIBLE_PUMP" in result.flags
    assert result.top_headline == "Fresh company announcement"
    assert 0.0 <= result.confidence <= 1.0


def test_sentiment_curator_flags_fundamental_contradiction():
    result = SentimentCurator().curate(
        {
            "newsapi": {
                "source": "newsapi",
                "sentiment_score": 0.55,
                "sentiment_label": "BULLISH",
                "top_headline": "Company sentiment improves",
            },
            "fundamentals": {
                "verdict": "weak",
                "profit_margin": -0.2,
                "revenue_growth": -0.1,
            },
        }
    )

    assert result.label == "BULLISH"
    assert "CONTRADICTION" in result.flags
    assert "Institutional BULLISH" in result.summary


def test_curated_sentiment_to_dict():
    result = CuratedSentiment(
        ticker="AAPL",
        composite_score=0.1,
        label="NEUTRAL",
        confidence=0.7,
        agreement=0.5,
    )

    assert result.to_dict()["ticker"] == "AAPL"
