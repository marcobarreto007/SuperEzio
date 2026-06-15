"""Watchlist pulse aggregation for the Genie frontpage panel."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from .curator import CuratedSentiment, SentimentCurator
from .live_monitor import LiveMonitor


@dataclass
class PulseReport:
    ticker: str
    sentiment: str
    sentiment_display: str
    score: float
    confidence: float
    reddit: dict[str, Any] = field(default_factory=dict)
    news: dict[str, Any] = field(default_factory=dict)
    flags: list[str] = field(default_factory=list)
    curator: str = ""
    alerts_24h: list[dict[str, Any]] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        text = str(value)
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except (TypeError, ValueError):
        return None


def _score_label(score: float) -> str:
    if score >= 0.15:
        return "BULLISH"
    if score <= -0.15:
        return "BEARISH"
    return "NEUTRAL"


def _arrow(current: str, previous: str) -> str:
    ranks = {"BEARISH": -1, "NEUTRAL": 0, "NO_DATA": 0, "BULLISH": 1}
    delta = ranks.get(current, 0) - ranks.get(previous, 0)
    if delta > 0:
        return "up"
    if delta < 0:
        return "down"
    return "flat"


def _source_count(source: Mapping[str, Any]) -> int:
    for key in ("news_count", "article_count", "count", "total", "total_posts", "qualified_count"):
        value = source.get(key)
        if value not in (None, "", [], {}):
            try:
                return int(float(value))
            except (TypeError, ValueError):
                return 0
    articles = source.get("articles")
    return len(articles) if isinstance(articles, list) else 0


class WatchlistPulse:
    def __init__(self, monitor: LiveMonitor, curator: SentimentCurator):
        self.monitor = monitor
        self.curator = curator

    def get_pulse(self, ticker: str) -> PulseReport:
        """Snapshot completo de sentimento para um ticker."""

        symbol = str(ticker or "").strip().upper()
        snapshot = self.monitor.get_sentiment_snapshot(symbol)
        raw_sources = snapshot.get("sources") if isinstance(snapshot.get("sources"), Mapping) else {}
        sources = self._sources_with_ticker(symbol, raw_sources)
        curated = self.curator.curate(sources)
        previous = self._previous_label(snapshot, curated)
        display = self._display(curated, previous)
        alerts = self._alerts_24h(symbol)

        return PulseReport(
            ticker=symbol,
            sentiment=curated.label,
            sentiment_display=display,
            score=curated.composite_score,
            confidence=curated.confidence,
            reddit=self._reddit_summary(raw_sources.get("reddit_pulse") or raw_sources.get("reddit")),
            news=self._news_summary(raw_sources),
            flags=curated.flags,
            curator=curated.summary,
            alerts_24h=alerts,
            sources=curated.sources_used,
        )

    def get_all_pulses(self) -> list[PulseReport]:
        """Pulso de todos os tickers na watchlist."""

        return [self.get_pulse(ticker) for ticker in list(self.monitor.watchlist)]

    @staticmethod
    def _sources_with_ticker(symbol: str, sources: Mapping[str, Any]) -> dict[str, Any]:
        normalized: dict[str, Any] = {}
        for name, value in sources.items():
            if isinstance(value, Mapping):
                item = dict(value)
                item.setdefault("ticker", symbol)
                normalized[name] = item
            else:
                normalized[name] = value
        return normalized

    @staticmethod
    def _previous_label(snapshot: Mapping[str, Any], curated: CuratedSentiment) -> str:
        history = snapshot.get("history_24h") if isinstance(snapshot.get("history_24h"), list) else []
        if len(history) < 2:
            return curated.label
        for item in reversed(history[:-1]):
            score = item.get("sentiment_score")
            if isinstance(score, (int, float)):
                return _score_label(float(score))
        return curated.label

    @staticmethod
    def _display(curated: CuratedSentiment, previous: str) -> str:
        direction = _arrow(curated.label, previous)
        if previous and previous != curated.label:
            return f"{curated.label} {direction} (was {previous})"
        return f"{curated.label} {direction}"

    def _alerts_24h(self, symbol: str) -> list[dict[str, Any]]:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        alerts = []
        for alert in self.monitor.get_alerts(limit=100):
            if str(alert.get("ticker") or "").upper() != symbol:
                continue
            ts = _parse_time(alert.get("detected_at"))
            if ts is None or ts >= cutoff:
                alerts.append(alert)
        return alerts

    @staticmethod
    def _reddit_summary(source: Any) -> dict[str, Any]:
        if not isinstance(source, Mapping):
            return {"mentions": 0, "signal": "NO_DATA", "spike": False}
        mentions = _source_count(source)
        avg = source.get("avg_mentions") or source.get("average_mentions") or source.get("normal_mentions")
        try:
            avg_number = float(avg) if avg not in (None, "", [], {}) else None
        except (TypeError, ValueError):
            avg_number = None
        spike = bool(avg_number and mentions >= avg_number * 3) or "SPIKE" in str(
            source.get("signal_label") or ""
        ).upper()
        return {
            "mentions": mentions,
            "average": avg_number,
            "signal": source.get("signal_label") or source.get("sentiment_label") or "NEUTRAL",
            "spike": spike,
            "qualified_count": source.get("qualified_count", 0),
        }

    @staticmethod
    def _news_summary(sources: Mapping[str, Any]) -> dict[str, Any]:
        total = 0
        labels: list[str] = []
        for name in ("newsapi", "news_scout", "finnhub"):
            source = sources.get(name)
            if not isinstance(source, Mapping):
                continue
            total += _source_count(source)
            label = source.get("sentiment_label") or source.get("label")
            if label:
                labels.append(str(label).upper())
        label = max(set(labels), key=labels.count) if labels else "NO_DATA"
        return {"articles": total, "label": label}


__all__ = ["PulseReport", "WatchlistPulse"]
