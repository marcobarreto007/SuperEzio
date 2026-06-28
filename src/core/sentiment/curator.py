"""Automatic curation for live sentiment sources."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from typing import Any, Mapping


SOURCE_WEIGHTS = {
    "newsapi": 1.0,
    "finnhub": 0.9,
    "news_scout": 0.7,
    "reddit_pulse": 0.5,
}


@dataclass
class CuratedSentiment:
    ticker: str
    composite_score: float
    label: str
    confidence: float
    agreement: float
    flags: list[str] = field(default_factory=list)
    top_headline: str = ""
    summary: str = ""
    sources_used: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _now() -> datetime:
    return datetime.now(timezone.utc)


from core.utils.datetime import parse_iso_datetime as _parse_time


def _number(value: Any) -> float | None:
    if value in (None, "", [], {}):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _label_from_score(score: float) -> str:
    if score >= 0.15:
        return "BULLISH"
    if score <= -0.15:
        return "BEARISH"
    return "NEUTRAL"


def _score_from_label(label: Any) -> float:
    text = str(label or "").upper()
    if any(token in text for token in ("BEARISH", "FEAR", "NEGATIVE", "SELL")):
        return -0.35
    if any(token in text for token in ("BULLISH", "EUPHORIC", "POSITIVE", "BUY")):
        return 0.35
    return 0.0


def _headline(source: Mapping[str, Any]) -> str:
    for key in ("top_headline", "headline", "title"):
        if source.get(key):
            return str(source[key])
    articles = source.get("articles") or source.get("items") or source.get("data")
    if isinstance(articles, list) and articles and isinstance(articles[0], Mapping):
        return str(articles[0].get("title") or articles[0].get("headline") or "")
    return ""


def _timestamp(source: Mapping[str, Any]) -> datetime | None:
    for key in ("timestamp", "published_at", "datetime", "collected_at"):
        parsed = _parse_time(source.get(key))
        if parsed:
            return parsed
    articles = source.get("articles")
    if isinstance(articles, list) and articles and isinstance(articles[0], Mapping):
        return _timestamp(articles[0])
    return None


def _similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left.lower(), right.lower()).ratio()


def _reddit_mentions(source: Mapping[str, Any]) -> int:
    for key in ("mentions", "mention_count", "total_posts", "post_count", "qualified_count"):
        value = source.get(key)
        if value not in (None, "", [], {}):
            try:
                return int(float(value))
            except (TypeError, ValueError):
                return 0
    return 0


def _reddit_average(source: Mapping[str, Any]) -> float | None:
    for key in ("avg_mentions", "average_mentions", "normal_mentions", "baseline_mentions"):
        number = _number(source.get(key))
        if number is not None:
            return number
    return None


def _fundamental_bias(source: Mapping[str, Any]) -> int:
    verdict = str(source.get("verdict") or source.get("trend") or source.get("label") or "").upper()
    if any(token in verdict for token in ("BEARISH", "WEAK", "NEGATIVE", "DETERIORATING")):
        return -1
    if any(token in verdict for token in ("BULLISH", "STRONG", "POSITIVE", "IMPROVING")):
        return 1
    margin = _number(source.get("profit_margin"))
    growth = _number(source.get("revenue_growth"))
    if margin is not None and growth is not None:
        if margin < 0 and growth < 0:
            return -1
        if margin > 0.08 and growth > 0:
            return 1
    return 0


class SentimentCurator:
    """Clean, rank, and score live sentiment sources."""

    def curate(self, sources: dict[str, Any]) -> CuratedSentiment:
        normalized = self._normalize_sources(sources or {})
        deduped = self._dedupe(normalized)
        ticker = self._ticker_from_sources(sources, deduped)

        if not deduped:
            return CuratedSentiment(
                ticker=ticker,
                composite_score=0.0,
                label="NO_DATA",
                confidence=0.0,
                agreement=0.0,
                flags=["NO_DATA"],
                summary="Sem fontes de sentimento utilizaveis.",
            )

        total_weight = sum(item["weight"] for item in deduped)
        composite = (
            sum(item["score"] * item["weight"] for item in deduped) / total_weight
            if total_weight
            else 0.0
        )
        label = _label_from_score(composite)
        agreement = self._agreement(deduped, label)
        confidence = self._confidence(deduped, composite, agreement)
        flags = self._flags(sources, deduped, composite)
        top = self._top_headline(deduped)

        return CuratedSentiment(
            ticker=ticker,
            composite_score=round(composite, 4),
            label=label,
            confidence=round(confidence, 4),
            agreement=round(agreement, 4),
            flags=flags,
            top_headline=top,
            summary=self._summary(label, flags, deduped),
            sources_used=[item["source"] for item in deduped],
        )

    def _normalize_sources(self, sources: Mapping[str, Any]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for name, raw in sources.items():
            if name == "fundamentals" or not raw:
                continue
            source = self._normalize_source(name, raw)
            if source:
                items.append(source)
        return items

    def _normalize_source(self, name: str, raw: Any) -> dict[str, Any] | None:
        if isinstance(raw, list):
            raw = {
                "source": name,
                "articles": raw,
                "news_count": len(raw),
                "sentiment_label": "NEUTRAL",
                "sentiment_score": 0.0,
            }
        if not isinstance(raw, Mapping) or raw.get("error"):
            return None
        source_name = self._canonical_name(str(raw.get("provider") or raw.get("source") or name))
        weight = SOURCE_WEIGHTS.get(source_name, SOURCE_WEIGHTS.get(name, 0.4))
        score = _number(raw.get("sentiment_score") or raw.get("score"))
        if score is None:
            score = _score_from_label(raw.get("sentiment_label") or raw.get("signal_label") or raw.get("label"))
        ts = _timestamp(raw)
        if ts and _now() - ts > timedelta(hours=48):
            weight *= 0.3
        return {
            "source": source_name,
            "weight": weight,
            "score": float(score),
            "label": str(raw.get("sentiment_label") or raw.get("signal_label") or raw.get("label") or _label_from_score(float(score))).upper(),
            "headline": _headline(raw),
            "raw": dict(raw),
            "institutional": source_name in {"newsapi", "news_scout", "finnhub"},
        }

    def _dedupe(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        deduped: list[dict[str, Any]] = []
        for item in items:
            duplicate_at = None
            for index, current in enumerate(deduped):
                if _similarity(item.get("headline", ""), current.get("headline", "")) > 0.8:
                    duplicate_at = index
                    break
            if duplicate_at is None:
                deduped.append(item)
            elif item["weight"] > deduped[duplicate_at]["weight"]:
                deduped[duplicate_at] = item
        return deduped

    @staticmethod
    def _canonical_name(name: str) -> str:
        clean = name.lower().replace("-", "_")
        if "newsapi" in clean:
            return "newsapi"
        if "finnhub" in clean:
            return "finnhub"
        if "reddit" in clean:
            return "reddit_pulse"
        if "scout" in clean:
            return "news_scout"
        return clean

    @staticmethod
    def _ticker_from_sources(sources: Mapping[str, Any], items: list[dict[str, Any]]) -> str:
        for source in sources.values():
            if isinstance(source, Mapping):
                ticker = source.get("ticker") or source.get("symbol") or source.get("requested_symbol")
                if ticker:
                    return str(ticker).upper()
        for item in items:
            raw = item.get("raw") or {}
            ticker = raw.get("ticker") or raw.get("symbol") if isinstance(raw, Mapping) else None
            if ticker:
                return str(ticker).upper()
        return ""

    @staticmethod
    def _agreement(items: list[dict[str, Any]], final_label: str) -> float:
        if not items:
            return 0.0
        final = _score_from_label(final_label)
        if final == 0:
            neutral = sum(1 for item in items if _score_from_label(item["label"]) == 0)
            return neutral / len(items)
        agree = sum(1 for item in items if _score_from_label(item["label"]) == final)
        return agree / len(items)

    @staticmethod
    def _confidence(items: list[dict[str, Any]], composite: float, agreement: float) -> float:
        coverage = min(len(items) / 4, 1.0)
        conviction = min(abs(composite) / 0.5, 1.0)
        return max(0.0, min(1.0, 0.2 + agreement * 0.45 + coverage * 0.25 + conviction * 0.10))

    def _flags(
        self,
        sources: Mapping[str, Any],
        items: list[dict[str, Any]],
        composite: float,
    ) -> list[str]:
        flags: list[str] = []
        reddit = sources.get("reddit_pulse") or sources.get("reddit")
        if isinstance(reddit, Mapping):
            mentions = _reddit_mentions(reddit)
            avg = _reddit_average(reddit)
            signal = str(reddit.get("signal_label") or "").upper()
            if "SPIKE" in signal or (avg and mentions >= avg * 3):
                flags.append("SPIKE")
            coordinated = reddit.get("new_accounts_same_text") or reddit.get("suspicious_accounts_count")
            if isinstance(coordinated, list) and len(coordinated) >= 3:
                flags.append("POSSIBLE_PUMP")
            elif _number(coordinated) is not None and float(coordinated) >= 3:
                flags.append("POSSIBLE_PUMP")
            institutional_scores = [
                item["score"] for item in items if item.get("institutional") and item["source"] != "reddit_pulse"
            ]
            reddit_score = _number(reddit.get("sentiment_score") or reddit.get("score"))
            if reddit_score is not None and reddit_score > 0.35 and institutional_scores:
                if sum(institutional_scores) / len(institutional_scores) <= 0.1:
                    flags.append("POSSIBLE_PUMP")

        fundamentals = sources.get("fundamentals")
        if isinstance(fundamentals, Mapping):
            bias = _fundamental_bias(fundamentals)
            if (bias < 0 and composite > 0.2) or (bias > 0 and composite < -0.2):
                flags.append("CONTRADICTION")

        return sorted(set(flags))

    @staticmethod
    def _top_headline(items: list[dict[str, Any]]) -> str:
        ranked = sorted(
            [item for item in items if item.get("headline")],
            key=lambda item: (not item.get("institutional"), -item["weight"]),
        )
        return ranked[0]["headline"] if ranked else ""

    @staticmethod
    def _summary(label: str, flags: list[str], items: list[dict[str, Any]]) -> str:
        institutional = [item for item in items if item.get("institutional")]
        social = [item for item in items if item["source"] == "reddit_pulse"]
        inst_label = _label_from_score(sum(item["score"] for item in institutional) / len(institutional)) if institutional else "NO_DATA"
        social_label = _label_from_score(sum(item["score"] for item in social) / len(social)) if social else "NO_DATA"
        flag_text = f" Flags: {', '.join(flags)}." if flags else ""
        return (
            f"Sentiment {label}. Institutional {inst_label}; social {social_label}."
            f"{flag_text}"
        )


__all__ = ["CuratedSentiment", "SentimentCurator"]
