"""Fail-closed regressions for specialized social-market semantics."""

from pathlib import Path

from src.data.social_whale_provider import SocialWhaleProvider

# Captured verbatim (bytes) from the live shutdown page served by
# https://nitter.net/search?f=tweets&q=$RIG on 2026-09-10: HTTP 200, no tweet
# container, but 11 prose blocks longer than 40 chars — the exact input that
# used to be parsed as ten "observed" tweets, identical for every ticker.
NITTER_SHUTDOWN_PAGE = (
    Path(__file__).resolve().parent / "fixtures" / "nitter_shutdown_page.html"
).read_text(encoding="utf-8")

_REAL_TIMELINE_SNIPPET = (
    '<div class="timeline-item">'
    '<div class="tweet-content media-body">$RIG whale alert shows institutional accumulation</div>'
    "</div>"
)


class _FakeResponse:
    status_code = 200

    def __init__(self, text: str) -> None:
        self.text = text


class _FakeSession:
    """Stand-in for requests.Session that always answers 200 + *text*."""

    def __init__(self, text: str) -> None:
        self._text = text

    def get(self, *_args, **_kwargs) -> _FakeResponse:
        return _FakeResponse(self._text)


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


# ── Nitter offline (shutdown page served with HTTP 200) ────────────────────


def test_shutdown_page_without_tweet_container_parses_to_zero_tweets():
    assert SocialWhaleProvider._parse_nitter_tweets(NITTER_SHUTDOWN_PAGE, 10) == []


def test_parser_still_extracts_real_tweet_containers():
    tweets = SocialWhaleProvider._parse_nitter_tweets(
        f"<html><body>{_REAL_TIMELINE_SNIPPET}</body></html>", 10
    )
    assert len(tweets) == 1
    assert "institutional accumulation" in tweets[0]["text"]


def test_search_rejects_http_200_without_tweet_container():
    provider = SocialWhaleProvider()
    provider._session = _FakeSession(NITTER_SHUTDOWN_PAGE)  # type: ignore[assignment]

    assert provider._search("$RIG pump") == ([], "nitter_offline")

    pump = provider.get_pump_detection("RIG")
    whale = provider.get_whale_signals("RIG")

    for result in (pump, whale):
        assert result["signal"] == "UNKNOWN"
        assert result["data_status"] == "NO_DATA"
        assert result["source"] == "no_data"
    assert pump["pump_risk"] is None
    assert whale["whale_score"] is None
