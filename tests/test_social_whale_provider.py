"""Fail-closed regressions for specialized social-market semantics."""

from src.data.social_whale_provider import SocialWhaleProvider


def test_aggregate_sentiment_is_not_relabelled_as_specialized_signal(monkeypatch):
    provider = SocialWhaleProvider()
    provider._apewisdom = object()
    monkeypatch.setattr(provider, "_search", lambda *_args, **_kwargs: ([], "nitter_offline"))
    monkeypatch.setattr(
        provider,
        "_get_apewisdom",
        lambda: (_ for _ in ()).throw(AssertionError("specialized methods must not use sentiment")),
    )

    whale = provider.get_whale_signals("ZZZZ")
    pump = provider.get_pump_detection("ZZZZ")
    options = provider.get_unusual_options_flow("ZZZZ")

    for result in (whale, pump, options):
        assert result["signal"] == "UNKNOWN"
        assert result["data_status"] == "NO_DATA"
        assert result["source"] == "no_data"
        assert "CLEAN" not in result.values()

    assert whale["whale_score"] is None
    assert pump["pump_risk"] is None
    assert options["unusual_flow_score"] is None


def test_observed_specialized_keywords_keep_source_and_status(monkeypatch):
    provider = SocialWhaleProvider()
    monkeypatch.setattr(
        provider,
        "_search",
        lambda *_args, **_kwargs: (
            [{"text": "$ABC whale alert shows institutional accumulation"}],
            "nitter(test)",
        ),
    )

    result = provider.get_whale_signals("ABC")

    assert result["signal"] == "WHALE_DETECTED"
    assert result["source"] == "nitter(test)"
    assert result["data_status"] == "OBSERVED"
    assert result["whale_mentions"] == 1
