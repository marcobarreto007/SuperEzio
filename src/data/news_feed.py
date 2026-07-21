"""
NewsScout — Agente de coleta de notícias financeiras multi-source
=================================================================
Fontes (em cascata, da mais rápida para a mais lenta):

  1. Brave Search API (se BRAVE_SEARCH_API_KEY configurada)
  2. DuckDuckGo News (ddgs >= 9.x — query posicional)
  3. Bing News RSS (sem chave, gratuito)
  4. Google News RSS (sem chave, gratuito)
  5. Yahoo Finance RSS (sem chave, gratuito)
  6. Reuters RSS — mercados (sem chave, gratuito)
  7. Scraping leve via requests + regex (MarketWatch headlines)
  8. DDG Text search (último fallback)

Sentimento: TextBlob (fallback: contagem de palavras positivas/negativas).
Todas as fontes retornam o mesmo schema de Dict.
"""

from __future__ import annotations

import concurrent.futures
import datetime
import logging
import os
import re
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ── DuckDuckGo (ddgs >= 9.x — API: query posicional, sem keywords=) ────────
try:
    from ddgs import DDGS as _DDGS
except ImportError:
    _DDGS = None  # type: ignore  — instale: pip install ddgs

# ── TextBlob (sentimento) ───────────────────────────────────────────────────
try:
    from textblob import TextBlob as _TextBlob

    _HAS_TEXTBLOB = True
except ImportError:
    _HAS_TEXTBLOB = False

# ── requests (RSS + scraping) ───────────────────────────────────────────────
try:
    import requests as _requests

    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False


# ── Constantes ──────────────────────────────────────────────────────────────
_MAX_CRAWL_SECONDS = 30  # timeout total para um ciclo de crawl multi-source
_SUPEREZIO_NEWSSCOUT_ASYNC = os.getenv("SUPEREZIO_NEWSSCOUT_ASYNC") == "1"

_POS_WORDS = {
    "surges",
    "rallies",
    "gains",
    "rises",
    "beats",
    "record",
    "growth",
    "profit",
    "upgrade",
    "buy",
    "bullish",
    "strong",
    "soars",
    "optimism",
    "dividend",
    "outperforms",
    "milestone",
    "opportunity",
    "positive",
    "sobe",
    "alta",
    "lucro",
    "crescimento",
    "recorde",
    "compra",
}
_NEG_WORDS = {
    "falls",
    "drops",
    "plunges",
    "misses",
    "loss",
    "cut",
    "sell",
    "bearish",
    "weak",
    "decline",
    "lawsuit",
    "fraud",
    "risk",
    "downgrade",
    "concern",
    "crisis",
    "crash",
    "layoffs",
    "warning",
    "debt",
    "recall",
    "probe",
    "cai",
    "queda",
    "perda",
    "risco",
    "fraude",
    "corte",
    "vende",
}


def _sentiment(text: str) -> tuple[float, str]:
    """Retorna (score -1..1, label POSITIVE/NEUTRAL/NEGATIVE)."""
    if _HAS_TEXTBLOB:
        score = round(_TextBlob(text).sentiment.polarity, 2)
    else:
        words = set(text.lower().split())
        pos = len(words & _POS_WORDS)
        neg = len(words & _NEG_WORDS)
        total = pos + neg
        score = round((pos - neg) / total, 2) if total else 0.0
    label = "POSITIVE" if score > 0.1 else ("NEGATIVE" if score < -0.1 else "NEUTRAL")
    return score, label


def _make_item(
    title: str,
    snippet: str,
    url: str,
    source: str,
    published_date: str = "",
) -> Dict:
    score, label = _sentiment(f"{title} {snippet}")
    return {
        "title": title,
        "snippet": snippet[:300],
        "source": source,
        "url": url,
        "published_date": published_date or datetime.datetime.now(datetime.UTC).isoformat(),
        "sentiment_score": score,
        "sentiment_label": label,
    }


# ── Fontes individuais ───────────────────────────────────────────────────────


def _fetch_ddg_news(query: str, limit: int) -> List[Dict]:
    """DuckDuckGo News — argumento posicional correto para ddgs >= 7.x."""
    if _DDGS is None:
        return []
    try:
        with _DDGS() as ddgs:
            # nova API: primeiro arg posicional = query
            raw = ddgs.news(f"{query} stock news finance", max_results=limit)
        items = []
        for r in raw or []:
            items.append(
                _make_item(
                    title=r.get("title", ""),
                    snippet=r.get("body", "") or r.get("excerpt", ""),
                    url=r.get("url", "") or r.get("href", ""),
                    source=r.get("source", "DuckDuckGo"),
                    published_date=r.get("date", ""),
                )
            )
        return items
    except Exception as e:
        if "No results found" not in str(e):
            logger.warning("[NEWS] DDG News falhou: %s", e)
        return []


def _fetch_ddg_text(query: str, limit: int) -> List[Dict]:
    """DuckDuckGo Text search como fallback para news."""
    if _DDGS is None:
        return []
    try:
        with _DDGS() as ddgs:
            raw = ddgs.text(f"{query} stock news", max_results=limit)
        items = []
        for r in raw or []:
            items.append(
                _make_item(
                    title=r.get("title", ""),
                    snippet=r.get("body", ""),
                    url=r.get("href", ""),
                    source="DuckDuckGo",
                )
            )
        return items
    except Exception as e:
        logger.warning("[NEWS] DDG Text falhou: %s", e)
        return []


def _fetch_google_news_rss(query: str, limit: int) -> List[Dict]:
    """Google News RSS — gratuito, sem chave."""
    if not _HAS_REQUESTS:
        return []
    try:
        q = query.replace(" ", "+")
        url = f"https://news.google.com/rss/search?q={q}+stock+finance&hl=en-US&gl=US&ceid=US:en"
        resp = _requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code != 200:
            return []
        # Parse RSS manualmente (sem lxml)
        items = []
        entries = re.findall(r"<item>(.*?)</item>", resp.text, re.DOTALL)
        for entry in entries[:limit]:
            title = re.search(r"<title>(.*?)</title>", entry, re.DOTALL)
            link = re.search(r"<link/?>([^<]+)", entry)
            desc = re.search(r"<description>(.*?)</description>", entry, re.DOTALL)
            pub = re.search(r"<pubDate>(.*?)</pubDate>", entry)
            t = re.sub(r"<[^>]+>", "", title.group(1) if title else "").strip()
            d = re.sub(r"<[^>]+>", "", desc.group(1) if desc else "").strip()
            lnk = (link.group(1) if link else "").strip()
            p = (pub.group(1) if pub else "").strip()
            if t:
                items.append(_make_item(t, d, lnk, "Google News", p))
        return items
    except Exception as e:
        logger.warning("[NEWS] Google News RSS falhou: %s", e)
        return []


def _fetch_yahoo_finance_rss(query: str, limit: int) -> List[Dict]:
    """Yahoo Finance RSS — gratuito, sem chave."""
    if not _HAS_REQUESTS:
        return []
    try:
        # Yahoo Finance RSS para ticker ou query
        ticker_clean = query.replace(".SA", "").replace(".TO", "").replace(".V", "")
        url = f"https://finance.yahoo.com/rss/headline?s={ticker_clean}"
        resp = _requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code != 200:
            # fallback genérico
            query.replace(" ", "+")
            url2 = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker_clean}&region=US&lang=en-US"
            resp = _requests.get(url2, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code != 200:
                return []
        items = []
        entries = re.findall(r"<item>(.*?)</item>", resp.text, re.DOTALL)
        for entry in entries[:limit]:
            title = re.search(r"<title>(.*?)</title>", entry, re.DOTALL)
            link = re.search(r"<link>(.*?)</link>", entry, re.DOTALL)
            desc = re.search(r"<description>(.*?)</description>", entry, re.DOTALL)
            pub = re.search(r"<pubDate>(.*?)</pubDate>", entry)
            t = re.sub(r"<[^>]+>|&#\d+;|&\w+;", "", title.group(1) if title else "").strip()
            d = re.sub(r"<[^>]+>|&#\d+;|&\w+;", "", desc.group(1) if desc else "").strip()
            lnk = re.sub(r"\s+", "", link.group(1) if link else "")
            p = (pub.group(1) if pub else "").strip()
            if t:
                items.append(_make_item(t, d, lnk, "Yahoo Finance", p))
        return items
    except Exception as e:
        logger.warning("[NEWS] Yahoo Finance RSS falhou: %s", e)
        return []


def _fetch_reuters_rss(limit: int) -> List[Dict]:
    """Reuters Business/Markets RSS — desativado (feeds.reuters.com está offline)."""
    return []


def _fetch_marketwatch_scrape(query: str, limit: int) -> List[Dict]:
    """MarketWatch search scraping leve via requests + regex."""
    if not _HAS_REQUESTS:
        return []
    try:
        q = query.replace(" ", "%20")
        url = f"https://www.marketwatch.com/search?q={q}&m=Keyword&rpp=10&mp=0&bd=false&rs=true"
        resp = _requests.get(
            url,
            timeout=8,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml",
            },
        )
        if resp.status_code != 200:
            return []
        # Extrai headlines de resultados
        items = []
        matches = re.findall(
            r'<a[^>]+class="[^"]*headline[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            resp.text,
            re.DOTALL,
        )
        for href, title_raw in matches[:limit]:
            t = re.sub(r"<[^>]+>", "", title_raw).strip()
            if t:
                items.append(_make_item(t, "", href, "MarketWatch"))
        return items
    except Exception as e:
        logger.warning("[NEWS] MarketWatch scrape falhou: %s", e)
        return []


def _fetch_brave(query: str, limit: int, api_key: str) -> List[Dict]:
    """Brave Search API — requer BRAVE_SEARCH_API_KEY."""
    if not _HAS_REQUESTS:
        return []
    try:
        headers = {"X-Subscription-Token": api_key, "Accept": "application/json"}
        url = "https://api.search.brave.com/res/v1/news/search"
        params = {"q": f"{query} stock news", "count": limit, "freshness": "pd"}
        resp = _requests.get(url, headers=headers, params=params, timeout=6)
        if resp.status_code != 200:
            return []
        items = []
        for r in resp.json().get("results", []):
            title = r.get("title", "")
            desc = r.get("description", "")
            items.append(
                _make_item(
                    title,
                    desc,
                    r.get("url", ""),
                    r.get("source", {}).get("name", "Brave"),
                    r.get("age", ""),
                )
            )
        return items
    except Exception as e:
        logger.warning("[NEWS] Brave falhou: %s", e)
        return []


def _fetch_bing_news_rss(query: str, limit: int) -> List[Dict]:
    """Bing News RSS — gratuito, sem chave, boa cobertura de mercados."""
    if not _HAS_REQUESTS:
        return []
    try:
        q = query.replace(" ", "+")
        url = f"https://www.bing.com/news/search?q={q}+stock+finance&format=RSS"
        resp = _requests.get(
            url,
            timeout=8,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "Accept": "application/rss+xml, text/xml",
            },
        )
        if resp.status_code != 200:
            return []
        items = []
        entries = re.findall(r"<item>(.*?)</item>", resp.text, re.DOTALL)
        for entry in entries[:limit]:
            title = re.search(r"<title>(.*?)</title>", entry, re.DOTALL)
            link = re.search(r"<link[^/]?/?>(.*?)</link>|<link>(.*?)<", entry, re.DOTALL)
            desc = re.search(r"<description>(.*?)</description>", entry, re.DOTALL)
            pub = re.search(r"<pubDate>(.*?)</pubDate>", entry)
            t = re.sub(
                r"<[^>]+>|&#\d+;|&\w+;|<!\[CDATA\[|\]\]>",
                "",
                title.group(1) if title else "",
            ).strip()
            d = re.sub(
                r"<[^>]+>|&#\d+;|&\w+;|<!\[CDATA\[|\]\]>",
                "",
                desc.group(1) if desc else "",
            ).strip()
            l_match = link.group(1) or link.group(2) if link else ""
            lnk = re.sub(r"\s+", "", l_match or "")
            p = (pub.group(1) if pub else "").strip()
            if t:
                items.append(_make_item(t, d, lnk, "Bing News", p))
        return items
    except Exception as e:
        logger.warning("[NEWS] Bing News RSS falhou: %s", e)
        return []


# ── NewsScout (classe pública) ───────────────────────────────────────────────


class NewsScout:
    """
    Agente de notícias financeiras multi-source.

    Cascata:
      Brave (se chave) → DDG News → Bing News RSS → Google News RSS
      → Yahoo Finance RSS → Reuters RSS → MarketWatch scrape → DDG Text

    Todas as fontes retornam o mesmo schema.
    """

    def __init__(self) -> None:
        self.brave_key: Optional[str] = os.getenv("BRAVE_SEARCH_API_KEY")
        self.newsapi_key: Optional[str] = os.getenv("NEWSAPI_KEY")
        self._crawl_done: bool = False
        sources = [
            "DDG",
            "Bing News RSS",
            "Google News RSS",
            "Yahoo Finance RSS",
            "Reuters RSS",
            "MarketWatch",
        ]
        if self.brave_key:
            sources.insert(0, "Brave")
        if self.newsapi_key:
            sources.insert(1, "NewsAPI")
        logger.info("[NEWS] NewsScout iniciado | fontes: %s", ", ".join(sources))

    def _fetch_newsapi(self, query: str, limit: int) -> List[Dict]:
        """NewsAPI — fonte premium com chave."""
        if not self.newsapi_key or not _HAS_REQUESTS:
            return []
        try:
            url = "https://newsapi.org/v2/everything"
            params = {
                "q": f"{query} finance",
                "apiKey": self.newsapi_key,
                "language": "en",
                "sortBy": "relevancy",
                "pageSize": limit,
            }
            resp = _requests.get(url, params=params, timeout=8)
            if resp.status_code != 200:
                return []
            items = []
            for r in resp.json().get("articles", []):
                items.append(
                    _make_item(
                        title=r.get("title", ""),
                        snippet=r.get("description", "") or r.get("content", ""),
                        url=r.get("url", ""),
                        source=r.get("source", {}).get("name", "NewsAPI"),
                        published_date=r.get("publishedAt", ""),
                    )
                )
            return items
        except Exception as e:
            logger.warning("[NEWS] NewsAPI falhou: %s", e)
            return []

    def get_news(self, query: str, limit: int = 5) -> List[Dict]:
        """
        Busca notícias em cascata até atingir `limit` resultados.
        Combina e de-duplica por título.

        SUPEREZIO_NEWSSCOUT_ASYNC=1:
          - Skip crawl na primeira chamada (evita bloqueio no startup).
          - O crawl real acontece na segunda chamada (sob demanda).
        """
        # ── ASYNC MODE: skip initial crawl, return empty ─────────────────
        if _SUPEREZIO_NEWSSCOUT_ASYNC and not self._crawl_done:
            logger.info(
                "[NEWS] Skipping initial crawl for '%s' (SUPEREZIO_NEWSSCOUT_ASYNC=1)",
                query,
            )
            self._crawl_done = True
            return []

        # ── Normal mode: run full crawl with total timeout ───────────────
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(self._crawl_all_sources, query, limit)
                return future.result(timeout=_MAX_CRAWL_SECONDS)
        except concurrent.futures.TimeoutError:
            logger.warning(
                "[NEWS] Crawl timed out after %ds for '%s'",
                _MAX_CRAWL_SECONDS,
                query,
            )
            return []
        except Exception as exc:
            logger.warning("[NEWS] Crawl error for '%s': %s", query, exc)
            return []

    def _crawl_all_sources(self, query: str, limit: int) -> List[Dict]:
        """
        Executa o crawl multi-source em cascata.
        Extraída para ser chamada via ThreadPoolExecutor com timeout.
        """
        collected: List[Dict] = []
        seen_titles: set = set()

        def _add(items: List[Dict]) -> None:
            for item in items:
                key = item["title"].lower()[:60]
                if key not in seen_titles and item["title"]:
                    seen_titles.add(key)
                    collected.append(item)

        # 1. Brave (paid, best quality)
        if self.brave_key:
            _add(_fetch_brave(query, limit, self.brave_key))
            if len(collected) >= limit:
                return collected[:limit]

        # 2. NewsAPI (premium key provided)
        if self.newsapi_key:
            _add(self._fetch_newsapi(query, limit))
            if len(collected) >= limit:
                return collected[:limit]

        # 3. DDG News
        _add(_fetch_ddg_news(query, limit))
        if len(collected) >= limit:
            return collected[:limit]

        # 3. Bing News RSS (sem chave, boa cobertura)
        _add(_fetch_bing_news_rss(query, limit))
        if len(collected) >= limit:
            return collected[:limit]

        # 4. Google News RSS
        _add(_fetch_google_news_rss(query, limit))
        if len(collected) >= limit:
            return collected[:limit]

        # 5. Yahoo Finance RSS
        _add(_fetch_yahoo_finance_rss(query, limit))
        if len(collected) >= limit:
            return collected[:limit]

        # 6. Reuters RSS (contexto macro geral)
        _add(_fetch_reuters_rss(limit))
        if len(collected) >= limit:
            return collected[:limit]

        # 7. MarketWatch scrape
        _add(_fetch_marketwatch_scrape(query, limit))

        # 8. Último fallback: DDG text search
        if not collected:
            _add(_fetch_ddg_text(query, limit))

        return collected[:limit]

    def get_sentiment_summary(self, symbol: str) -> Dict:
        """Retorna resumo de sentimento para um ativo."""
        news = self.get_news(symbol, limit=10)
        if not news:
            return {
                "symbol": symbol,
                "sentiment_score": 0,
                "sentiment_label": "NO_DATA",
                "news_count": 0,
                "top_headline": "",
            }
        avg = round(sum(n["sentiment_score"] for n in news) / len(news), 2)
        label = "BULLISH" if avg > 0.15 else ("BEARISH" if avg < -0.15 else "NEUTRAL")
        return {
            "symbol": symbol,
            "sentiment_score": avg,
            "sentiment_label": label,
            "news_count": len(news),
            "top_headline": news[0]["title"],
        }
