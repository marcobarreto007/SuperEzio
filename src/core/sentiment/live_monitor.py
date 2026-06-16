"""Background sentiment monitor for watchlist tickers."""

from __future__ import annotations

import logging
import math
import threading
from collections import Counter, deque
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _number(value: Any) -> float | None:
    if value in (None, "", [], {}):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _label_polarity(value: Any) -> int:
    label = str(value or "").upper()
    if any(token in label for token in ("BEARISH", "FEAR", "NEGATIVE", "SELL")):
        return -1
    if any(token in label for token in ("BULLISH", "EUPHORIC", "POSITIVE", "BUY")):
        return 1
    return 0


def _source_score(source: Mapping[str, Any]) -> float | None:
    return _number(source.get("sentiment_score") or source.get("score"))


def _source_label(source: Mapping[str, Any]) -> str:
    return str(source.get("sentiment_label") or source.get("signal_label") or source.get("label") or "")


def _reddit_count(reddit: Mapping[str, Any]) -> int:
    for key in ("mentions", "mention_count", "total_posts", "post_count", "qualified_count"):
        value = reddit.get(key)
        if value not in (None, "", [], {}):
            try:
                return int(float(value))
            except (TypeError, ValueError):
                return 0
    return 0


def _article_summary_from_list(items: Any) -> dict[str, Any]:
    if not isinstance(items, list):
        return {}
    if not items:
        return {"source": "finnhub", "news_count": 0, "sentiment_label": "NO_DATA"}
    first = items[0] if isinstance(items[0], Mapping) else {}
    return {
        "source": "finnhub",
        "provider": "finnhub",
        "news_count": len(items),
        "articles": items,
        "top_headline": first.get("title") or first.get("headline"),
        "sentiment_label": "NEUTRAL",
        "sentiment_score": 0.0,
    }


class LiveMonitor:
    """Daemon sentiment monitor for a watchlist.

    Data is intentionally kept in memory. The monitor is a telemetry surface for
    the running API process, not a trade ledger.
    """

    def __init__(
        self,
        watchlist: list[str],
        interval_minutes: int = 15,
        *,
        data_hub: Any | None = None,
    ):
        self.watchlist = [str(ticker).strip().upper() for ticker in watchlist if str(ticker).strip()]
        self.interval = max(1, int(interval_minutes or 15))
        self.running = False
        self.alerts: list[dict[str, Any]] = []
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.RLock()
        self._snapshots: dict[str, dict[str, Any]] = {}
        self._history: dict[str, deque[dict[str, Any]]] = {
            ticker: deque(maxlen=288) for ticker in self.watchlist
        }
        self._data_hub = data_hub

    def start(self) -> None:
        """Start the daemon monitor thread once."""

        with self._lock:
            if self.running:
                return
            self.running = True
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run_loop,
                name="superezio-sentiment-live-monitor",
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        """Stop the monitor thread and wait briefly for shutdown."""

        with self._lock:
            self.running = False
            self._stop_event.set()
            thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=2.0)

    def get_alerts(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return newest alerts first."""

        with self._lock:
            return list(reversed(self.alerts[-max(0, int(limit)) :]))

    def get_sentiment_snapshot(self, ticker: str) -> dict[str, Any]:
        """Return latest snapshot plus 24h in-memory history for one ticker."""

        symbol = str(ticker or "").strip().upper()
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        with self._lock:
            snapshot = dict(self._snapshots.get(symbol) or {})
            history = [
                dict(item)
                for item in self._history.get(symbol, [])
                if (_parse_time(item.get("collected_at")) or cutoff) >= cutoff
            ]
        if not snapshot:
            snapshot = {"ticker": symbol, "status": "NO_DATA"}
        snapshot["history_24h"] = history
        return snapshot

    def collect_once(self) -> list[dict[str, Any]]:
        """Run one full watchlist collection cycle."""

        generated: list[dict[str, Any]] = []
        for ticker in list(self.watchlist):
            try:
                snapshot = self._collect_ticker(ticker)
            except Exception as exc:
                logger.warning("[sentiment.monitor] collection failed for %s: %s", ticker, exc)
                continue
            with self._lock:
                previous = list(self._history.setdefault(ticker, deque(maxlen=288)))
                alerts = self._detect_alerts(snapshot, previous)
                self._snapshots[ticker] = snapshot
                self._history[ticker].append(snapshot)
                self._persist_to_db(ticker, snapshot)
                for alert in alerts:
                    self._append_alert_locked(alert)
                generated.extend(alerts)
        return generated

    def _persist_to_db(self, ticker: str, snapshot: dict[str, Any]) -> None:
        """Persist sentiment snapshot to SQLite for historical trending."""
        try:
            import sqlite3
            db_path = self._db_path or (
                Path(__file__).resolve().parent.parent.parent.parent / "data" / "investor.db"
            )
            conn = sqlite3.connect(str(db_path))
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sentiment_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker TEXT NOT NULL,
                    collected_at TEXT NOT NULL,
                    score REAL,
                    label TEXT,
                    reddit_mentions INTEGER,
                    news_count INTEGER,
                    flags TEXT,
                    snapshot_json TEXT
                )
            """)
            conn.execute(
                """INSERT INTO sentiment_history
                   (ticker, collected_at, score, label, reddit_mentions, news_count, flags, snapshot_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    ticker,
                    _now_iso(),
                    _number(snapshot.get("sentiment_score")),
                    str(snapshot.get("sentiment_label", "")),
                    _reddit_count(snapshot.get("reddit", {})),
                    int(snapshot.get("news_count") or 0),
                    ",".join(snapshot.get("flags", [])),
                    json.dumps(snapshot, default=str)[:4000],
                ),
            )
            conn.commit()
            conn.close()
        except Exception:
            pass  # Non-critical — don't crash the monitor thread

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            self.collect_once()
            self._stop_event.wait(self.interval * 60)
        with self._lock:
            self.running = False

    def _datahub(self):
        if self._data_hub is not None:
            return self._data_hub
        from data.data_hub import hub

        return hub

    def _collect_ticker(self, ticker: str) -> dict[str, Any]:
        data_hub = self._datahub()
        sources: dict[str, Any] = {}

        for provider_name, method_name, target_name in (
            ("newsapi", "get_sentiment_summary", "newsapi"),
            ("news_scout", "get_sentiment_summary", "news_scout"),
            ("reddit_pulse", "get_signal", "reddit_pulse"),
            ("finnhub", "get_news", "finnhub"),
        ):
            provider = getattr(data_hub, "get_provider", lambda _name: None)(provider_name)
            method = getattr(provider, method_name, None) if provider is not None else None
            if not callable(method):
                continue
            try:
                result = method(ticker)
            except Exception as exc:
                logger.warning(
                    "[sentiment.monitor] provider %s failed for %s: %s",
                    provider_name,
                    ticker,
                    exc,
                )
                continue
            if isinstance(result, dict) and result.get("error"):
                continue
            if provider_name == "finnhub" and isinstance(result, list):
                result = _article_summary_from_list(result)
            if result:
                sources[target_name] = result

        if not sources:
            try:
                sentiment = data_hub.get_sentiment_summary(ticker)
                if isinstance(sentiment, dict) and "error" not in sentiment:
                    source = str(sentiment.get("provider") or sentiment.get("source") or "sentiment")
                    sources[source] = sentiment
                reddit = data_hub.get_reddit_signal(ticker)
                if isinstance(reddit, dict) and "error" not in reddit:
                    sources["reddit_pulse"] = reddit
            except Exception as exc:
                logger.warning("[sentiment.monitor] DataHub fallback failed for %s: %s", ticker, exc)

        collected_at = _now_iso()
        institutional = [
            source
            for name, source in sources.items()
            if name in {"newsapi", "news_scout", "finnhub"} and isinstance(source, Mapping)
        ]
        scores = [score for score in (_source_score(source) for source in institutional) if score is not None]
        reddit = sources.get("reddit_pulse") if isinstance(sources.get("reddit_pulse"), Mapping) else {}
        snapshot = {
            "ticker": ticker,
            "status": "ok" if sources else "NO_DATA",
            "collected_at": collected_at,
            "sources": sources,
            "sentiment_score": round(sum(scores) / len(scores), 4) if scores else None,
            "reddit_count": _reddit_count(reddit),
        }
        return snapshot

    def _detect_alerts(
        self,
        snapshot: Mapping[str, Any],
        previous: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        ticker = str(snapshot.get("ticker") or "").upper()
        now = _parse_time(snapshot.get("collected_at")) or datetime.now(timezone.utc)
        alerts: list[dict[str, Any]] = []

        current_score = _number(snapshot.get("sentiment_score"))
        if current_score is not None:
            for item in reversed(previous):
                ts = _parse_time(item.get("collected_at"))
                prior_score = _number(item.get("sentiment_score"))
                if ts is None or prior_score is None:
                    continue
                if now - ts <= timedelta(hours=1):
                    delta = current_score - prior_score
                    if abs(delta) >= 0.3:
                        alerts.append(
                            {
                                "type": "SWING",
                                "ticker": ticker,
                                "from": round(prior_score, 4),
                                "to": round(current_score, 4),
                                "delta": round(delta, 4),
                                "detected_at": snapshot.get("collected_at"),
                            }
                        )
                    break

        reddit = snapshot.get("sources", {}).get("reddit_pulse")
        if isinstance(reddit, Mapping):
            current_count = _reddit_count(reddit)
            historical_counts = [
                int(item.get("reddit_count") or 0) for item in previous if int(item.get("reddit_count") or 0) > 0
            ]
            explicit_avg = _number(
                reddit.get("avg_mentions")
                or reddit.get("average_mentions")
                or reddit.get("normal_mentions")
                or reddit.get("baseline_mentions")
            )
            avg = explicit_avg or (
                sum(historical_counts) / len(historical_counts) if historical_counts else None
            )
            if avg and current_count >= avg * 3:
                alerts.append(
                    {
                        "type": "SPIKE",
                        "ticker": ticker,
                        "count": current_count,
                        "avg": round(avg, 2),
                        "detected_at": snapshot.get("collected_at"),
                    }
                )

            coord_accounts = self._coordinated_account_count(reddit)
            if coord_accounts >= 3:
                alerts.append(
                    {
                        "type": "COORD",
                        "ticker": ticker,
                        "accounts": coord_accounts,
                        "detected_at": snapshot.get("collected_at"),
                    }
                )

        divergence = self._divergence_alert(snapshot)
        if divergence:
            alerts.append(divergence)

        return alerts

    def _append_alert_locked(self, alert: dict[str, Any]) -> None:
        self.alerts.append(alert)
        if len(self.alerts) > 100:
            del self.alerts[: len(self.alerts) - 100]

    @staticmethod
    def _coordinated_account_count(reddit: Mapping[str, Any]) -> int:
        for key in (
            "new_accounts_same_text",
            "identical_language_accounts",
            "coordinated_accounts",
            "suspicious_accounts_count",
        ):
            value = reddit.get(key)
            if isinstance(value, list):
                return len(value)
            if value not in (None, "", [], {}):
                try:
                    return int(value)
                except (TypeError, ValueError):
                    return 0

        posts = reddit.get("top_posts")
        if not isinstance(posts, list):
            return 0
        normalized: list[str] = []
        for post in posts:
            if not isinstance(post, Mapping):
                continue
            age = _number(post.get("account_age_days") or post.get("author_age_days"))
            if age is not None and age > 30:
                continue
            text = str(post.get("title") or post.get("text") or post.get("selftext") or "").lower()
            clean = " ".join(text.split())
            if clean:
                normalized.append(clean)
        counts = Counter(normalized)
        return max(counts.values(), default=0)

    @staticmethod
    def _divergence_alert(snapshot: Mapping[str, Any]) -> dict[str, Any] | None:
        ticker = str(snapshot.get("ticker") or "").upper()
        sources = snapshot.get("sources") if isinstance(snapshot.get("sources"), Mapping) else {}
        institutional: dict[str, str] = {}
        for name in ("newsapi", "news_scout", "finnhub"):
            source = sources.get(name)
            if isinstance(source, Mapping):
                label = _source_label(source)
                if _label_polarity(label) != 0:
                    institutional[name] = label
        reddit = sources.get("reddit_pulse")
        if not institutional or not isinstance(reddit, Mapping):
            return None
        social_label = _source_label(reddit)
        social_polarity = _label_polarity(social_label)
        if social_polarity == 0:
            return None
        institutional_polarities = {_label_polarity(label) for label in institutional.values()}
        institutional_polarities.discard(0)
        if institutional_polarities and social_polarity not in institutional_polarities:
            return {
                "type": "DIVERGENCE",
                "ticker": ticker,
                "institutional": institutional,
                "social": social_label,
                "detected_at": snapshot.get("collected_at"),
            }
        return None


__all__ = ["LiveMonitor"]
