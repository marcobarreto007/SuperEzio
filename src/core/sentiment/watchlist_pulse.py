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
    origin: str = "watchlist"
    discovered: bool = False
    discovery: dict[str, Any] = field(default_factory=dict)
    analyst_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


from core.utils.datetime import parse_iso_datetime as _parse_time


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
        meta = self._ticker_meta(symbol, snapshot)

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
            origin=str(meta.get("origin") or "watchlist"),
            discovered=bool(meta.get("discovered")),
            discovery=dict(meta) if meta.get("discovered") else {},
            analyst_score=self._analyst_score(curated, raw_sources, alerts, meta),
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

    def _ticker_meta(self, symbol: str, snapshot: Mapping[str, Any]) -> dict[str, Any]:
        getter = getattr(self.monitor, "get_ticker_meta", None)
        if callable(getter):
            try:
                meta = getter(symbol)
                if isinstance(meta, Mapping):
                    return dict(meta)
            except Exception:
                pass
        discovery = snapshot.get("discovery")
        if isinstance(discovery, Mapping) and discovery:
            meta = dict(discovery)
            meta.setdefault("origin", snapshot.get("origin") or "discovered")
            meta.setdefault("discovered", True)
            return meta
        return {
            "ticker": symbol,
            "origin": snapshot.get("origin") or "watchlist",
            "discovered": bool(snapshot.get("discovered")),
        }

    @staticmethod
    def _analyst_score(
        curated: CuratedSentiment,
        sources: Mapping[str, Any],
        alerts: list[dict[str, Any]],
        meta: Mapping[str, Any],
    ) -> float:
        reddit = sources.get("reddit_pulse") or sources.get("reddit")
        mentions = _source_count(reddit) if isinstance(reddit, Mapping) else 0
        news_articles = WatchlistPulse._news_summary(sources)["articles"]
        value = (
            abs(curated.composite_score) * 0.35
            + curated.confidence * 0.30
            + min(news_articles / 10, 1.0) * 0.15
            + min(mentions / 50, 1.0) * 0.10
            + min(len(curated.flags) * 0.08, 0.16)
            + min(len(alerts) * 0.06, 0.12)
        )
        if meta.get("discovered"):
            value += 0.12
        return round(max(0.0, min(1.0, value)), 4)

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
