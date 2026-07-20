"""
PROVIDER SENTIMENT TEST — Live API test for all DataHub sentiment/news providers.

Tests:
  1. NewsAPI      — via newsapi_provider.NewsAPIProvider
  2. ApeWisdom    — via apewisdom_provider.ApeWisdomProvider
  3. Reddit Pulse — via reddit_provider.RedditPulse
  4. NewsScout    — via news_feed.NewsScout
  5. AlphaSMO     — via alphasmo_provider.AlphaSMOProvider
  6. Form4API     — via form4api_provider.Form4APIProvider (if key set)

Tickers tested: AAPL, TSLA, GME

Output: JSON report with latency, article count, sentiment scores, and ranking.
"""

from __future__ import annotations

import json
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

# Ensure src is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

TICKERS = ["AAPL", "TSLA", "GME"]

# ── Helpers ──────────────────────────────────────────────────────────────


def _elapsed(start: float) -> float:
    return round(time.perf_counter() - start, 3)


def _load_env():
    """Minimal dotenv loader for .env.local (key=value pairs, # comments)."""
    for dotenv_path in [".env.local", ".env"]:
        path = os.path.join(os.path.dirname(__file__), "..", dotenv_path)
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key and not os.getenv(key):
                    os.environ[key] = val


# ── Test functions ───────────────────────────────────────────────────────


def test_newsapi() -> List[Dict[str, Any]]:
    """Test NewsAPI with the provided key 42e779eb1af94b17a2f10e4aaaea11e3."""
    print("\n" + "=" * 60)
    print("NEWSAPI PROVIDER")
    print("=" * 60)

    from data.newsapi_provider import NewsAPIProvider

    api_key = os.getenv("NEWSAPI_KEY")
    if not api_key:
        print("  [SKIP] NEWSAPI_KEY not set in environment")
        return [{"provider": "newsapi", "error": "NEWSAPI_KEY not set"}]

    provider = NewsAPIProvider(api_key=api_key)
    results = []

    for ticker in TICKERS:
        start = time.perf_counter()
        try:
            summary = provider.get_sentiment_summary(ticker)
            lat = _elapsed(start)
            summary["latency_s"] = lat
            news = provider.get_news(ticker, limit=5)
            print(f"\n  [{ticker}] latency={lat}s | count={summary['news_count']} | "
                  f"score={summary['sentiment_score']} | label={summary['sentiment_label']}")
            if news:
                for i, n in enumerate(news[:3]):
                    print(f"    {i+1}. [{n['sentiment_label']}] {n['title'][:80]}")
            results.append(summary)
        except Exception as e:
            lat = _elapsed(start)
            print(f"  [{ticker}] ERROR: {e}")
            results.append({"ticker": ticker, "provider": "newsapi", "error": str(e), "latency_s": lat})

    return results


def test_apewisdom() -> List[Dict[str, Any]]:
    """Test ApeWisdom FREE tier API live."""
    print("\n" + "=" * 60)
    print("APEWISDOM PROVIDER")
    print("=" * 60)

    from data.apewisdom_provider import ApeWisdomProvider

    provider = ApeWisdomProvider()
    results = []

    # 1) Test trending stocks (market-wide retail buzz)
    start = time.perf_counter()
    try:
        trending = provider.get_trending_stocks(page=1)
        lat = _elapsed(start)
        print(f"\n  [TRENDING] latency={lat}s | total_stocks={len(trending)}")

        if trending:
            print(f"  Top 10 stocks by mentions:")
            top_10_sorted = sorted(trending, key=lambda x: x.get("mentions", 0), reverse=True)[:10]
            for i, s in enumerate(top_10_sorted):
                tick = s.get("ticker", "???")
                ment = s.get("mentions", 0)
                score = s.get("sentiment_score", "?")
                rank = s.get("rank", "?")
                print(f"    {i+1}. {tick} | mentions={ment} | sentiment={score} | rank={rank}")

            # Check for target tickers
            found_tickers = [s.get("ticker", "").upper() for s in trending]
            for t in TICKERS:
                if t in found_tickers:
                    print(f"  [OK] {t} IS in trending list")
                else:
                    print(f"  [WARN] {t} NOT found in trending page 1")

        results.append({
            "provider": "apewisdom",
            "test": "trending",
            "total_stocks": len(trending),
            "top_10": [{"ticker": s.get("ticker"), "mentions": s.get("mentions"),
                        "sentiment_score": s.get("sentiment_score")} for s in top_10_sorted] if trending else [],
            "latency_s": lat,
        })
    except Exception as e:
        lat = _elapsed(start)
        print(f"  [TRENDING] ERROR: {e}")
        results.append({"provider": "apewisdom", "test": "trending", "error": str(e), "latency_s": lat})

    # 2) Test per-ticker sentiment
    for ticker in TICKERS:
        start = time.perf_counter()
        try:
            sent = provider.get_sentiment(ticker)
            lat = _elapsed(start)
            mentions = sent.get("mentions", 0)
            score = sent.get("sentiment_score", 0)
            note = sent.get("note", "")
            print(f"\n  [{ticker}] latency={lat}s | mentions={mentions} | sentiment_score={score} | note={note}")
            sent["latency_s"] = lat
            results.append(sent)
        except Exception as e:
            lat = _elapsed(start)
            print(f"  [{ticker}] ERROR: {e}")
            results.append({"ticker": ticker, "provider": "apewisdom", "error": str(e), "latency_s": lat})

    return results


def test_reddit_pulse() -> List[Dict[str, Any]]:
    """Test RedditPulse — public Reddit JSON API, no key needed."""
    print("\n" + "=" * 60)
    print("REDDIT PULSE PROVIDER")
    print("=" * 60)

    from data.reddit_provider import RedditPulse

    provider = RedditPulse()
    results = []

    for ticker in TICKERS:
        start = time.perf_counter()
        try:
            signal = provider.get_signal(ticker, limit=5, per_subreddit=5, sort="top", time_filter="month")
            lat = _elapsed(start)
            print(f"\n  [{ticker}] latency={lat}s | posts={signal['post_count']} | "
                  f"qualified={signal['qualified_count']} | score={signal['sentiment_score']} | "
                  f"label={signal['signal_label']}")
            if signal.get("top_posts"):
                for i, p in enumerate(signal["top_posts"][:3]):
                    print(f"    {i+1}. r/{p['subreddit']} | score={p['score']} | {p['title'][:80]}")
            signal["latency_s"] = lat
            results.append(signal)
        except Exception as e:
            lat = _elapsed(start)
            print(f"  [{ticker}] ERROR: {e}")
            traceback.print_exc()
            results.append({"ticker": ticker, "provider": "reddit_pulse", "error": str(e), "latency_s": lat})

    return results


def test_news_scout() -> List[Dict[str, Any]]:
    """Test NewsScout — multi-source cascade (NewsAPI, DDG, RSS)."""
    print("\n" + "=" * 60)
    print("NEWSSCOUT PROVIDER")
    print("=" * 60)

    from data.news_feed import NewsScout

    provider = NewsScout()
    results = []

    for ticker in TICKERS:
        start = time.perf_counter()
        try:
            news = provider.get_news(ticker, limit=8)
            news_lat = _elapsed(start)

            # Sentiment summary
            sent_start = time.perf_counter()
            summary = provider.get_sentiment_summary(ticker)
            sent_lat = _elapsed(sent_start)

            total_lat = round(news_lat + sent_lat, 3)
            print(f"\n  [{ticker}] latency={total_lat}s (news={news_lat}s, sent={sent_lat}s) | "
                  f"articles={summary['news_count']} | score={summary['sentiment_score']} | "
                  f"label={summary['sentiment_label']}")
            if news:
                for i, n in enumerate(news[:4]):
                    src = n.get("source", "?")
                    score = n.get("sentiment_score", "?")
                    print(f"    {i+1}. [{src}] score={score} | {n['title'][:80]}")

            summary["latency_s"] = total_lat
            results.append(summary)
        except Exception as e:
            lat = _elapsed(start)
            print(f"  [{ticker}] ERROR: {e}")
            traceback.print_exc()
            results.append({"ticker": ticker, "provider": "news_scout", "error": str(e), "latency_s": lat})

    return results


def test_alphasmo() -> List[Dict[str, Any]]:
    """Test AlphaSMO — CLI-based insider trading + smart-money convergence."""
    print("\n" + "=" * 60)
    print("ALPHASMO PROVIDER")
    print("=" * 60)

    from data.alphasmo_provider import AlphaSMOProvider

    provider = AlphaSMOProvider()
    results = []

    # Check availability
    if not provider._available:
        print("  [SKIP] AlphaSMO CLI not available (npx alphasmo not found)")
        return [{"provider": "alphasmo", "error": "CLI not available"}]

    print("  [OK] AlphaSMO CLI is available")

    # 1) Insider trades per ticker
    for ticker in TICKERS:
        start = time.perf_counter()
        try:
            trades = provider.get_insider_trades(ticker)
            lat = _elapsed(start)
            buys = trades.get("insider_buys", 0)
            sells = trades.get("insider_sells", 0)
            total = trades.get("total_trades", 0)
            error = trades.get("error")
            print(f"\n  [{ticker}] latency={lat}s | buys={buys} | sells={sells} | total={total}")
            if error:
                print(f"    WARN: {error}")
            trades["latency_s"] = lat
            results.append(trades)
        except Exception as e:
            lat = _elapsed(start)
            print(f"  [{ticker}] ERROR: {e}")
            results.append({"ticker": ticker, "provider": "alphasmo", "error": str(e), "latency_s": lat})

    # 2) Insider summary for AAPL
    start = time.perf_counter()
    try:
        summary = provider.get_insider_summary("AAPL")
        lat = _elapsed(start)
        print(f"\n  [AAPL SUMMARY] latency={lat}s | confidence_30d={summary.get('confidence_30d')} | "
              f"confidence_90d={summary.get('confidence_90d')} | cluster_buy={summary.get('cluster_buy')}")
        summary["latency_s"] = lat
        results.append(summary)
    except Exception as e:
        print(f"  [AAPL SUMMARY] ERROR: {e}")
        results.append({"provider": "alphasmo", "test": "insider_summary", "error": str(e)})

    # 3) Smart-money convergence
    start = time.perf_counter()
    try:
        convergence = provider.get_smart_money_convergence(limit=10, min_confidence=60)
        lat = _elapsed(start)
        score = convergence.get("convergence_score", 0)
        count = convergence.get("ticker_count", 0)
        error = convergence.get("error")
        print(f"\n  [CONVERGENCE] latency={lat}s | convergence_score={score} | ticker_count={count}")
        if error:
            print(f"    WARN: {error}")
        if convergence.get("tickers"):
            for i, t in enumerate(convergence["tickers"][:5]):
                tick = t.get("ticker", t.get("symbol", "?"))
                sc = t.get("score", t.get("convergenceScore", "?"))
                print(f"    {i+1}. {tick} | score={sc}")
        convergence["latency_s"] = lat
        results.append(convergence)
    except Exception as e:
        print(f"  [CONVERGENCE] ERROR: {e}")
        results.append({"provider": "alphasmo", "test": "convergence", "error": str(e)})

    # 4) Combined insider data
    start = time.perf_counter()
    try:
        combined = provider.get_insider_data("AAPL")
        lat = _elapsed(start)
        print(f"\n  [AAPL COMBINED] latency={lat}s | buys={combined.get('insider_buys')} | "
              f"sells={combined.get('insider_sells')} | cluster={combined.get('cluster_buy')} | "
              f"confidence_90d={combined.get('confidence_90d')}")
        combined["latency_s"] = lat
        results.append(combined)
    except Exception as e:
        print(f"  [AAPL COMBINED] ERROR: {e}")
        results.append({"provider": "alphasmo", "test": "insider_combined", "error": str(e)})

    return results


def test_form4api() -> List[Dict[str, Any]]:
    """Test Form4API (if FORM4API_KEY is set)."""
    print("\n" + "=" * 60)
    print("FORM4API PROVIDER")
    print("=" * 60)

    api_key = os.getenv("FORM4API_KEY")
    if not api_key:
        print("  [SKIP] FORM4API_KEY not set in environment — provider uses free tier default")
        print("  No key found in .env.local or .env either. Skipping Form4API test.")

    from data.form4api_provider import Form4APIProvider

    provider = Form4APIProvider(api_key=api_key)
    results = []

    if not provider.healthy:
        print("  [SKIP] Form4API not healthy (no API key configured)")
        return [{"provider": "form4api", "error": "API key not set", "healthy": False}]

    print("  [OK] Form4API has API key configured")

    for ticker in TICKERS:
        start = time.perf_counter()
        try:
            trades = provider.get_insider_trades(ticker, limit=10)
            lat = _elapsed(start)
            buys = len(trades.get("insider_buys", []))
            sells = len(trades.get("insider_sells", []))
            total = trades.get("transaction_count", 0)
            error = trades.get("error")
            print(f"\n  [{ticker}] latency={lat}s | buys={buys} | sells={sells} | total={total}")
            if error:
                print(f"    WARN: {error}")
            trades["latency_s"] = lat
            results.append(trades)
        except Exception as e:
            lat = _elapsed(start)
            print(f"  [{ticker}] ERROR: {e}")
            results.append({"ticker": ticker, "provider": "form4api", "error": str(e), "latency_s": lat})

    return results


def compute_ranking(all_results: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    """Compute final ranking of providers based on reliability, speed, and data quality."""
    print("\n" + "=" * 60)
    print("RANKING SUMMARY")
    print("=" * 60)

    rankings = []

    for provider_name, results in all_results.items():
        if not results:
            rankings.append({
                "provider": provider_name,
                "status": "NO_DATA",
                "avg_latency_s": 999,
                "data_quality": 0,
                "score": 0,
                "notes": "No results returned",
            })
            continue

        # Check errors
        errors = [r for r in results if r.get("error")]
        successes = [r for r in results if not r.get("error")]

        # Average latency
        latencies = [r.get("latency_s", 999) for r in results if r.get("latency_s") is not None]
        avg_latency = round(sum(latencies) / len(latencies), 3) if latencies else 999

        # Data quality: how many tickers returned real data?
        ticker_results = [r for r in successes if r.get("ticker") or r.get("symbol")]
        data_quality = 0
        for r in ticker_results:
            if provider_name in ("newsapi", "news_scout", "reddit_pulse"):
                count = r.get("news_count", r.get("post_count", r.get("qualified_count", 0)))
                if count > 0:
                    data_quality += 2
                elif count == 0:
                    data_quality += 0.5
            elif provider_name == "apewisdom":
                mentions = r.get("mentions", 0) or r.get("total_stocks", 0)
                if mentions > 0:
                    data_quality += 2
                else:
                    data_quality += 0.5
            elif provider_name in ("alphasmo", "form4api"):
                total = r.get("total_trades", r.get("ticker_count", 0))
                if total and total > 0:
                    data_quality += 2
                elif r.get("insider_buys") or r.get("insider_sells"):
                    data_quality += 2
                else:
                    data_quality += 0.5

        reliability = len(successes) / max(len(results), 1) * 10
        latency_score = max(0, 10 - avg_latency) if avg_latency < 10 else 1
        total_score = round(reliability * 0.4 + latency_score * 0.3 + data_quality * 0.3, 1)

        rankings.append({
            "provider": provider_name,
            "status": "OK" if not errors else f"{len(errors)}/{len(results)} errors",
            "avg_latency_s": avg_latency,
            "reliability": round(reliability, 1),
            "data_quality_score": data_quality,
            "total_score": total_score,
            "notes": "All tickers responded" if not errors else f"Errors: {[r.get('error') for r in errors[:2]]}",
        })

    rankings.sort(key=lambda r: r["total_score"], reverse=True)

    print(f"\n{'Rank':<6} {'Provider':<16} {'Score':<8} {'Avg Latency':<12} {'Status':<20}")
    print("-" * 62)
    for i, r in enumerate(rankings, 1):
        lat_str = f"{r['avg_latency_s']}s" if r['avg_latency_s'] != 999 else "N/A"
        print(f"{i:<6} {r['provider']:<16} {r['total_score']:<8} {lat_str:<12} {r['status']:<20}")

    return {"rankings": rankings, "generated_at": datetime.now(timezone.utc).isoformat()}


# ── Main ─────────────────────────────────────────────────────────────────


def main():
    print("=" * 60)
    print("  PROVIDER SENTIMENT TEST — LIVE API TESTS")
    print(f"  Tickers: {', '.join(TICKERS)}")
    print(f"  Started at: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    _load_env()

    all_results: Dict[str, List[Dict[str, Any]]] = {}

    # Run tests
    all_results["newsapi"] = test_newsapi()
    all_results["apewisdom"] = test_apewisdom()
    all_results["reddit_pulse"] = test_reddit_pulse()
    all_results["news_scout"] = test_news_scout()
    all_results["alphasmo"] = test_alphasmo()
    all_results["form4api"] = test_form4api()

    # Compute ranking
    ranking = compute_ranking(all_results)

    # Export report
    report = {
        "test_tickers": TICKERS,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "results": all_results,
        "ranking": ranking,
    }

    report_path = os.path.join(
        os.path.dirname(__file__), "..", "runtime", "provider_sentiment_report.json"
    )
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)

    print(f"\n{'=' * 60}")
    print(f"  REPORT EXPORTED: {report_path}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
