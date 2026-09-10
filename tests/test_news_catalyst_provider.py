"""Catalisador keyless via news (incidente 2026-09-10: gate sem provedor)."""

from datetime import UTC, datetime, timedelta

from core.pipeline.trade_order import _is_actionable_evidence
from data.news_catalyst_provider import NewsCatalystProvider


def _news(title, days_ago=1, source="google_news_ca"):
    when = (datetime.now(UTC) - timedelta(days=days_ago)).isoformat()
    return {"title": title, "published_date": when, "source": source}


def test_recent_headline_with_concrete_term_becomes_catalyst():
    provider = NewsCatalystProvider(
        lambda symbol: [_news("ACME reports earnings beat and raises guidance")]
    )
    out = provider.get_short_term_catalyst("ACME")
    assert out["catalyst"].startswith("earnings")
    assert _is_actionable_evidence(out["catalyst"], "catalyst") is True
    assert out["event_date"]


def test_headline_without_concrete_term_is_rejected():
    provider = NewsCatalystProvider(lambda symbol: [_news("ACME stock trends on social media")])
    assert provider.get_short_term_catalyst("ACME") == {}


def test_old_headline_is_out_of_window():
    provider = NewsCatalystProvider(lambda symbol: [_news("ACME reports earnings", days_ago=30)])
    assert provider.get_short_term_catalyst("ACME") == {}


def test_loader_failure_is_soft():
    def boom(symbol):
        raise RuntimeError("news down")

    assert NewsCatalystProvider(boom).get_short_term_catalyst("ACME") == {}


def test_picks_the_newest_matching_headline():
    provider = NewsCatalystProvider(
        lambda symbol: [
            _news("ACME wins contract with city", days_ago=6),
            _news("ACME announces acquisition of rival", days_ago=2),
        ]
    )
    out = provider.get_short_term_catalyst("ACME")
    assert out["catalyst"].startswith("acquisition")
