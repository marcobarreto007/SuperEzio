"""NewsAPI 429 must stop further HTTP calls instead of hammering the quota."""

from __future__ import annotations

from types import SimpleNamespace

from data import newsapi_provider as nap


def test_newsapi_429_trips_cooldown_and_skips_next_call(monkeypatch):
    nap.reset_newsapi_cooldown_for_tests()
    calls = {"n": 0}

    def fake_get(*_args, **_kwargs):
        calls["n"] += 1
        return SimpleNamespace(
            status_code=429,
            text="rate limited",
            json=lambda: {"message": "too many requests"},
        )

    monkeypatch.setattr(nap, "_HAS_REQUESTS", True)
    monkeypatch.setattr(nap, "_requests", SimpleNamespace(get=fake_get))
    provider = nap.NewsAPIProvider(api_key="test-key")

    assert provider.get_news("AAPL") == []
    assert calls["n"] == 1
    assert nap.newsapi_cooling_down() is True
    assert provider.healthy is False

    assert provider.get_news("MSFT") == []
    assert calls["n"] == 1  # cooldown skipped the second HTTP call
    nap.reset_newsapi_cooldown_for_tests()
