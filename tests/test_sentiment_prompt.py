from core.pipeline.prompts.sentiment_prompt import format_sentiment_context


def test_format_sentiment_context_uses_structured_sources():
    prompt = format_sentiment_context(
        {
            "ticker": "TLRY",
            "data": {
                "sentiment": {
                    "source": "news_scout_multisource",
                    "sentiment_label": "bullish",
                    "sentiment_score": 0.3,
                    "news_count": 8,
                    "top_headline": "TLRY Joins European Cannabis Talks",
                },
                "reddit": {
                    "signal_label": "spike 12x normal",
                    "qualified_count": 5,
                    "total_posts": 340,
                    "suspicious_accounts": ["acct1", "acct2", "acct3"],
                    "top_posts": [{"title": "TLRY getting coordinated attention"}],
                },
                "finnhub_news": {
                    "sentiment_label": "neutral",
                    "sentiment_score": 0.0,
                    "news_count": 3,
                },
                "curator": {
                    "agreement_count": 2,
                    "disagreement_count": 1,
                    "label": "bullish",
                    "composite_confidence": 0.65,
                },
            },
        }
    )

    assert "[SENTIMENT_CONTEXT]" in prompt
    assert "Ticker: TLRY" in prompt
    assert "NewsScout: 8 artigos | sentimento BULLISH (+0.3)" in prompt
    assert '"TLRY Joins European Cannabis Talks"' in prompt
    assert "RedditPulse: 340 mencoes" in prompt
    assert "sinal SPIKE 12X NORMAL" in prompt
    assert "5 posts qualificados" in prompt
    assert "3 contas suspeitas" in prompt
    assert "Finnhub: 3 company announcements | sentimento NEUTRAL (0.0)" in prompt
    assert "CURATOR: 2 fontes concordam (BULLISH) | 1 fonte discorda" in prompt
    assert "confianca composta=0.65" in prompt
    assert "[/SENTIMENT_CONTEXT]" in prompt


def test_format_sentiment_context_reports_no_data_without_fabricating_sources():
    prompt = format_sentiment_context(
        {
            "ticker": "AAPL",
            "data": {
                "sentiment": {"source": "newsapi", "sentiment_label": "NO_DATA"},
            },
        }
    )

    assert "NewsAPI: sem dados" in prompt
    assert "RedditPulse" not in prompt
    assert "Finnhub" not in prompt


def test_format_sentiment_context_handles_news_list():
    prompt = format_sentiment_context(
        {
            "ticker": "MSFT",
            "data": {
                "news": [
                    {"title": "Microsoft announces product update"},
                    {"title": "Analysts react"},
                ],
            },
        }
    )

    assert "NewsAPI: 2 artigos" in prompt
    assert '"Microsoft announces product update"' in prompt
