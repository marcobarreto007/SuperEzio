"""Structured sentiment context for Gemini/Genie prompts."""

from __future__ import annotations

from typing import Any, Mapping, Sequence


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_sequence(value: Any) -> Sequence[Any]:
    return value if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) else []


def _number(value: Any) -> float | None:
    if value in (None, "", [], {}):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fmt_score(value: Any) -> str:
    number = _number(value)
    if number is None:
        return "N/A"
    if number > 0:
        return f"+{number:.1f}"
    return f"{number:.1f}"


def _label(value: Any) -> str:
    text = str(value or "").strip()
    return text.upper() if text else "NEUTRAL"


def _first_present(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return None


def _quote(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return f' | "{text[:140]}"'


def _count_articles(section: Mapping[str, Any]) -> int | None:
    for key in ("news_count", "article_count", "count", "total", "total_articles"):
        if section.get(key) not in (None, "", [], {}):
            try:
                return int(section[key])
            except (TypeError, ValueError):
                return None
    articles = _as_sequence(section.get("articles") or section.get("items") or section.get("data"))
    return len(articles) if articles else None


def _headline(section: Mapping[str, Any]) -> str:
    for key in ("top_headline", "headline", "title"):
        if section.get(key):
            return str(section[key])
    articles = _as_sequence(section.get("articles") or section.get("items") or section.get("data"))
    if articles and isinstance(articles[0], Mapping):
        return str(articles[0].get("title") or articles[0].get("headline") or "")
    return ""


def _source_name(section: Mapping[str, Any], fallback: str) -> str:
    source = str(section.get("source") or "").lower()
    if "newsapi" in source or "news_api" in source:
        return "NewsAPI"
    if "scout" in source:
        return "NewsScout"
    if "finnhub" in source:
        return "Finnhub"
    return fallback


def _format_sentiment_source(section: Mapping[str, Any], fallback: str) -> str:
    if not section:
        return ""
    name = _source_name(section, fallback)
    label = _label(section.get("sentiment_label") or section.get("label"))
    if label == "NO_DATA":
        return f"{name}: sem dados"

    count = _count_articles(section)
    count_text = f"{count} artigos" if count is not None else "artigos=N/A"
    score = _fmt_score(_first_present(section.get("sentiment_score"), section.get("score")))
    return f"{name}: {count_text} | sentimento {label} ({score}){_quote(_headline(section))}"


def _format_news_list(news: Any) -> str:
    if not news:
        return ""
    if isinstance(news, Mapping):
        return _format_sentiment_source(news, "NewsAPI")
    articles = _as_sequence(news)
    if not articles:
        return ""
    first_title = ""
    if isinstance(articles[0], Mapping):
        first_title = str(articles[0].get("title") or articles[0].get("headline") or "")
    return f"NewsAPI: {len(articles)} artigos{_quote(first_title)}"


def _format_finnhub(section: Any) -> str:
    if not section:
        return ""
    if isinstance(section, Mapping):
        if _label(section.get("sentiment_label") or section.get("label")) == "NO_DATA":
            return "Finnhub: sem dados"
        count = _count_articles(section)
        score = _fmt_score(_first_present(section.get("sentiment_score"), section.get("score")))
        label = _label(section.get("sentiment_label") or section.get("label"))
        item_text = f"{count} company announcements" if count is not None else "announcements=N/A"
        return f"Finnhub: {item_text} | sentimento {label} ({score}){_quote(_headline(section))}"
    items = _as_sequence(section)
    return f"Finnhub: {len(items)} company announcements" if items else ""


def _format_reddit(section: Mapping[str, Any]) -> str:
    if not section:
        return ""
    signal = _label(section.get("signal_label") or section.get("sentiment_label"))
    if signal == "NO_DATA":
        return "RedditPulse: sem dados"

    mentions = section.get("mentions") or section.get("mention_count") or section.get("total_posts")
    mention_text = f"{mentions} mencoes" if mentions not in (None, "", [], {}) else "mencoes=N/A"
    spike = section.get("spike_label") or section.get("spike") or section.get("spike_ratio")
    if spike not in (None, "", [], {}):
        mention_text += f" ({spike})"

    qualified = section.get("qualified_count")
    qualified_text = f"{qualified or 0} posts qualificados"
    suspicious = (
        section.get("suspicious_accounts_count")
        or section.get("suspect_accounts")
        or section.get("suspicious_accounts")
    )
    if isinstance(suspicious, Sequence) and not isinstance(suspicious, (str, bytes)):
        suspicious_count = len(suspicious)
    elif suspicious in (None, "", [], {}):
        suspicious_count = None
    else:
        try:
            suspicious_count = int(suspicious)
        except (TypeError, ValueError):
            suspicious_count = None

    parts = [f"RedditPulse: {mention_text}", f"sinal {signal}", qualified_text]
    if suspicious_count is not None:
        parts.append(f"{suspicious_count} contas suspeitas")

    top_posts = _as_sequence(section.get("top_posts"))
    if top_posts and isinstance(top_posts[0], Mapping):
        title = top_posts[0].get("title")
        if title:
            parts.append(f'"{str(title)[:140]}"')
    return " | ".join(parts)


def _format_curator(data: Mapping[str, Any], source_labels: list[str]) -> str:
    curator = _as_mapping(
        data.get("curator")
        or data.get("sentiment_curator")
        or _as_mapping(data.get("sentiment")).get("curator")
    )
    if curator:
        agreement = curator.get("agreement_count") or curator.get("sources_agree")
        disagreement = curator.get("disagreement_count") or curator.get("sources_disagree")
        label = _label(curator.get("label") or curator.get("consensus_label"))
        confidence = _number(curator.get("composite_confidence") or curator.get("confidence"))
        confidence_text = f"{confidence:.2f}" if confidence is not None else "N/A"
        return (
            f"CURATOR: {agreement or 0} fontes concordam ({label}) | "
            f"{disagreement or 0} fonte discorda | confianca composta={confidence_text}"
        )

    usable = [label for label in source_labels if label and label != "NO_DATA"]
    if len(usable) < 2:
        return ""
    consensus = max(set(usable), key=usable.count)
    agree = usable.count(consensus)
    disagree = len(usable) - agree
    return f"CURATOR: {agree} fontes concordam ({consensus}) | {disagree} fonte discorda"


def format_sentiment_context(state: Mapping[str, Any]) -> str:
    """Return structured sentiment context extracted from pipeline state."""

    data = _as_mapping(state.get("data") if isinstance(state, Mapping) else {})
    ticker = str(
        state.get("ticker") or data.get("ticker") or data.get("symbol") or "UNKNOWN"
    ).upper()

    sentiment = _as_mapping(data.get("sentiment"))
    reddit = _as_mapping(data.get("reddit"))
    news = data.get("news")
    finnhub_news = data.get("finnhub_news")

    lines = ["[SENTIMENT_CONTEXT]", f"Ticker: {ticker}"]
    source_labels: list[str] = []

    sentiment_line = _format_sentiment_source(sentiment, "NewsScout")
    if sentiment_line:
        lines.append(sentiment_line)
        source_labels.append(_label(sentiment.get("sentiment_label") or sentiment.get("label")))

    news_line = _format_news_list(news)
    if news_line:
        lines.append(news_line)
        if isinstance(news, Mapping):
            source_labels.append(_label(news.get("sentiment_label") or news.get("label")))

    reddit_line = _format_reddit(reddit)
    if reddit_line:
        lines.append(reddit_line)
        source_labels.append(_label(reddit.get("signal_label") or reddit.get("sentiment_label")))

    finnhub_line = _format_finnhub(finnhub_news)
    if finnhub_line:
        lines.append(finnhub_line)
        if isinstance(finnhub_news, Mapping):
            source_labels.append(
                _label(finnhub_news.get("sentiment_label") or finnhub_news.get("label"))
            )

    curator_line = _format_curator(data, source_labels)
    if curator_line:
        lines.append(curator_line)

    lines.append("[/SENTIMENT_CONTEXT]")
    return "\n".join(lines)


__all__ = ["format_sentiment_context"]
