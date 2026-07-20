#!/usr/bin/env python3
"""
Cross-Provider Discrepancy Test — SuperEzio F51

Tests 5 tickers against ALL available price providers:
  TwelveData, AlphaVantage, AKShare, yfinance, Stooq

Output: CROSS-PROVIDER DISCREPANCY TEST report with tables, outliers,
volume consistency, historical close comparison, and reliability ranking.
"""

from __future__ import annotations

import os
import sys
import json
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# Ensure project root is on sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# ── Tickers under test ────────────────────────────────────────────────
TICKERS = ["AAPL", "MSFT", "SNDL", "VALE", "PETR4.SA"]

PROVIDER_INFO = {
    "twelve_data": {"key_required": True,  "api_key_var": "TWELVE_DATA_API_KEY"},
    "alpha_vantage": {"key_required": True, "api_key_var": "ALPHA_VANTAGE_API_KEY"},
    "akshare":       {"key_required": False, "api_key_var": None},
    "yfinance":      {"key_required": False, "api_key_var": None},
    "stooq":         {"key_required": False, "api_key_var": None},
}

COL_RESET = "\033[0m"
COL_RED = "\033[91m"
COL_GREEN = "\033[92m"
COL_YELLOW = "\033[93m"
COL_CYAN = "\033[96m"
COL_BOLD = "\033[1m"

# ═══════════════════════════════════════════════════════════════════════
#  Helper: load .env.local
# ═══════════════════════════════════════════════════════════════════════


def _load_env(path: str) -> None:
    """Minimal dotenv loader — sets os.environ from KEY=VAL lines."""
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip().strip("\"'").strip()
                os.environ.setdefault(key, val)
    except FileNotFoundError:
        pass


# Load .env.local and .env
_load_env(os.path.join(PROJECT_ROOT, ".env.local"))
_load_env(os.path.join(PROJECT_ROOT, ".env"))

# ═══════════════════════════════════════════════════════════════════════
#  Provider factory
# ═══════════════════════════════════════════════════════════════════════


def _get_provider(name: str):
    """Lazy-import and instantiate a named provider. Returns None on failure."""
    try:
        if name == "twelve_data":
            from src.data.twelve_data import TwelveDataProvider
            return TwelveDataProvider()
        elif name == "alpha_vantage":
            from src.data.alpha_vantage import AlphaVantageProvider
            return AlphaVantageProvider()
        elif name == "akshare":
            from src.data.akshare_provider import AKShareProvider
            return AKShareProvider()
        elif name == "yfinance":
            from src.data.yfinance_provider import YFinanceProvider
            return YFinanceProvider()
        elif name == "stooq":
            from src.data.stooq_provider import StooqProvider
            return StooqProvider()
    except Exception as exc:
        return None


def _get_price_from(provider_name: str, provider, symbol: str) -> Dict[str, Any]:
    """Call the appropriate price/quote method for this provider."""
    try:
        if provider_name == "alpha_vantage":
            # AlphaVantage uses get_quote() instead of get_price()
            result = provider.get_quote(symbol)
            # Normalise: map 'price' from quote result
            if "error" not in result and result.get("price") is None:
                return {"error": "alpha_vantage_no_price_in_quote"}
            return result
        elif provider_name == "twelve_data":
            return provider.get_price(symbol)
        elif provider_name == "akshare":
            return provider.get_price(symbol, market="US")
        elif provider_name == "yfinance":
            return provider.get_price(symbol, market="US")
        elif provider_name == "stooq":
            return provider.get_price(symbol, market="US")
    except Exception as exc:
        return {"error": f"{provider_name}_exception: {exc}"}


def _get_candles_from(provider_name: str, provider, symbol: str, timeframe: str = "1M") -> Dict[str, Any]:
    """Fetch candles for historical close comparison."""
    try:
        if provider_name == "twelve_data":
            return provider.get_candles(symbol, timeframe=timeframe)
        elif provider_name == "alpha_vantage":
            return provider.get_ohlcv(symbol, timeframe=timeframe)
        elif provider_name == "akshare":
            return provider.get_candles(symbol, timeframe=timeframe, market="US")
        elif provider_name == "yfinance":
            return provider.get_candles(symbol, timeframe=timeframe, market="US")
        elif provider_name == "stooq":
            # Stooq only has get_price, no get_candles
            return {"error": "stooq_no_candles"}
    except Exception as exc:
        return {"error": f"{provider_name}_candles_exception: {exc}"}


# ═══════════════════════════════════════════════════════════════════════
#  Statistical helpers
# ═══════════════════════════════════════════════════════════════════════


def mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def std_dev(values: list[float], avg: float | None = None) -> float:
    if len(values) < 2:
        return 0.0
    avg = avg or mean(values)
    variance = sum((v - avg) ** 2 for v in values) / len(values)
    return math.sqrt(variance)


def z_score(value: float, avg: float, sd: float) -> float:
    if sd == 0:
        return 0.0
    return (value - avg) / sd


def pct_diff(a: float, b: float) -> float:
    """Percentage difference relative to the mean."""
    if a == 0 and b == 0:
        return 0.0
    avg = (abs(a) + abs(b)) / 2
    if avg == 0:
        return 0.0
    return abs(a - b) / avg * 100


# ═══════════════════════════════════════════════════════════════════════
#  Main test runner
# ═══════════════════════════════════════════════════════════════════════

results: Dict[str, Dict[str, Any]] = {}  # ticker -> {provider -> result}
candle_results: Dict[str, Dict[str, Any]] = {}  # ticker -> {provider -> candles}


def run_price_tests() -> None:
    """Phase 1: collect price from every provider for every ticker."""
    for ticker in TICKERS:
        results[ticker] = {}
        print(f"\n{COL_CYAN}{'='*70}{COL_RESET}")
        print(f"{COL_BOLD}  TICKER: {ticker}{COL_RESET}")
        print(f"{COL_CYAN}{'='*70}{COL_RESET}")

        for pname in PROVIDER_INFO:
            pinfo = PROVIDER_INFO[pname]
            # Check API key if required
            if pinfo["key_required"]:
                key_val = os.getenv(pinfo["api_key_var"])
                if not key_val:
                    print(f"  {COL_YELLOW}[SKIP] {pname}: no {pinfo['api_key_var']} set{COL_RESET}")
                    results[ticker][pname] = {"error": f"no_{pinfo['api_key_var']}_set"}
                    continue

            provider = _get_provider(pname)
            if provider is None:
                print(f"  {COL_YELLOW}[SKIP] {pname}: failed to instantiate{COL_RESET}")
                results[ticker][pname] = {"error": "instantiation_failed"}
                continue

            result = _get_price_from(pname, provider, ticker)
            results[ticker][pname] = result

            if "error" in result:
                print(f"  {COL_RED}[ERR]  {pname:16s}: {result['error']}{COL_RESET}")
            else:
                price = result.get("price", "N/A")
                volume = result.get("volume", "N/A")
                print(f"  {COL_GREEN}[OK]   {pname:16s}: price={price}  volume={volume}{COL_RESET}")


def run_candle_tests() -> None:
    """Phase 2: collect 1M candles from each provider for historical close comparison."""
    for ticker in TICKERS:
        candle_results[ticker] = {}
        for pname in PROVIDER_INFO:
            if pname == "stooq":
                # Stooq has no candle/OHLCV endpoint
                candle_results[ticker][pname] = {"error": "stooq_no_candles"}
                continue

            pinfo = PROVIDER_INFO[pname]
            if pinfo["key_required"]:
                key_val = os.getenv(pinfo["api_key_var"])
                if not key_val:
                    candle_results[ticker][pname] = {"error": f"no_{pinfo['api_key_var']}_set"}
                    continue

            provider = _get_provider(pname)
            if provider is None:
                candle_results[ticker][pname] = {"error": "instantiation_failed"}
                continue

            result = _get_candles_from(pname, provider, ticker, timeframe="1M")
            candle_results[ticker][pname] = result


def build_price_table() -> str:
    """Build the price comparison table."""
    lines = []
    header = f"{'TICKER':12s} {'Provider':16s} {'Price':>10s} {'Volume':>12s} {'Status':>10s}"
    lines.append(header)
    lines.append("-" * len(header))

    for ticker in TICKERS:
        for pname in PROVIDER_INFO:
            r = results[ticker].get(pname, {})
            if "error" in r:
                price_str = "---"
                vol_str = "---"
                status = r["error"][:10]
            else:
                price_val = r.get("price")
                price_str = f"{price_val:.2f}" if price_val is not None else "N/A"
                vol_val = r.get("volume")
                vol_str = f"{vol_val:,}" if vol_val is not None else "N/A"
                status = "OK"
            lines.append(f"{ticker:12s} {pname:16s} {price_str:>10s} {vol_str:>12s} {status:>10s}")
    return "\n".join(lines)


def detect_outliers() -> List[Dict[str, Any]]:
    """Detect price outliers per ticker using z-score."""
    outliers = []
    for ticker in TICKERS:
        prices: list[tuple[str, float]] = []
        for pname in PROVIDER_INFO:
            r = results[ticker].get(pname, {})
            if "error" not in r and r.get("price") is not None:
                prices.append((pname, float(r["price"])))

        if len(prices) < 3:
            continue

        vals = [p[1] for p in prices]
        avg = mean(vals)
        sd = std_dev(vals, avg)
        threshold = 2.0  # |z| > 2.0 = outlier

        for pname, pval in prices:
            zs = z_score(pval, avg, sd)
            if abs(zs) > threshold:
                outliers.append({
                    "ticker": ticker,
                    "provider": pname,
                    "value": pval,
                    "mean": round(avg, 2),
                    "z_score": round(zs, 2),
                    "pct_from_mean": round((pval - avg) / avg * 100, 2),
                })
    return outliers


def check_volume_consistency() -> List[Dict[str, Any]]:
    """Check if any provider's volume deviates >20% from median."""
    discrepancies = []
    for ticker in TICKERS:
        volumes: list[tuple[str, int]] = []
        for pname in PROVIDER_INFO:
            r = results[ticker].get(pname, {})
            if "error" not in r and r.get("volume") is not None:
                vol = int(r["volume"])
                if vol > 0:
                    volumes.append((pname, vol))

        if len(volumes) < 2:
            continue

        # Median volume
        sorted_vols = sorted(v[1] for v in volumes)
        mid = len(sorted_vols) // 2
        median_vol = sorted_vols[mid] if len(sorted_vols) % 2 else (
            sorted_vols[mid - 1] + sorted_vols[mid]) / 2

        for pname, vol in volumes:
            if median_vol == 0:
                continue
            deviation = abs(vol - median_vol) / median_vol * 100
            if deviation > 20:
                discrepancies.append({
                    "ticker": ticker,
                    "provider": pname,
                    "volume": vol,
                    "median_volume": int(median_vol),
                    "deviation_pct": round(deviation, 1),
                })
    return discrepancies


def compare_historical_close(days_ago: int = 15) -> List[Dict[str, Any]]:
    """Compare close price N days ago between providers for each ticker."""
    discrepancies = []
    from datetime import timedelta

    for ticker in TICKERS:
        closes: list[tuple[str, float, str]] = []  # (provider, close, date_str)

        for pname in PROVIDER_INFO:
            if pname == "stooq":
                continue
            cr = candle_results.get(ticker, {}).get(pname, {})
            if "error" in cr:
                continue
            candles = cr.get("candles", [])
            if not candles or not isinstance(candles, list):
                continue

            # Candles are sorted oldest-first typically. We need approx 15 trading days back.
            # If we have enough candles, pick one ~15 entries from end.
            if len(candles) < days_ago + 1:
                continue

            # Candles from yfinance/akshare are oldest-first; twelve_data/alpha_vantage
            # may be newest-first (twelve_data reverses).   Try to get the candle
            # at index -days_ago or days_ago depending on order.
            # Heuristic: check if first candle date < last candle date
            try:
                first_date = candles[0].get("datetime", candles[0].get("time", ""))
                last_date = candles[-1].get("datetime", candles[-1].get("time", ""))
                oldest_first = str(first_date) < str(last_date)
            except Exception:
                oldest_first = True

            if oldest_first:
                target_idx = max(0, len(candles) - days_ago - 1)
            else:
                target_idx = min(len(candles) - 1, days_ago)

            c = candles[target_idx]
            close_val = float(c.get("close", 0))
            dt_str = str(c.get("datetime", c.get("time", "?")))[:10]
            if close_val > 0:
                closes.append((pname, close_val, dt_str))

        if len(closes) < 2:
            continue

        vals = [c[1] for c in closes]
        avg = mean(vals)

        for pname, close_val, dt_str in closes:
            # Compare to average
            pd = pct_diff(close_val, avg) if avg > 0 else 0
            if pd > 2.0:  # >2% difference from average
                discrepancies.append({
                    "ticker": ticker,
                    "provider": pname,
                    "close_15d_ago": close_val,
                    "date": dt_str,
                    "avg_close": round(avg, 2),
                    "pct_diff_from_avg": round(pd, 2),
                })
    return discrepancies


def rank_reliability() -> Dict[str, Any]:
    """Rank providers by reliability: success rate and consistency."""
    stats: Dict[str, Dict[str, Any]] = {}
    for pname in PROVIDER_INFO:
        stats[pname] = {"attempts": 0, "successes": 0, "prices": [], "score": 0}

    for ticker in TICKERS:
        for pname in PROVIDER_INFO:
            stats[pname]["attempts"] += 1
            r = results[ticker].get(pname, {})
            if "error" not in r and r.get("price") is not None:
                stats[pname]["successes"] += 1
                stats[pname]["prices"].append(float(r["price"]))

    # Score: success_rate * 50 + consistency_score * 30 + coverage * 20
    for pname, s in stats.items():
        success_rate = s["successes"] / s["attempts"] if s["attempts"] else 0
        # Consistency: lower std_dev relative to mean = better
        if len(s["prices"]) >= 2:
            avg_p = mean(s["prices"])
            sd = std_dev(s["prices"], avg_p)
            cv = sd / avg_p if avg_p > 0 else 1.0  # coefficient of variation
            consistency_score = max(0, 1.0 - min(cv * 10, 1.0))
        else:
            consistency_score = 0.5

        # Coverage: how many distinct ticker types covered
        coverage = s["successes"] / s["attempts"]

        s["success_rate"] = round(success_rate, 2)
        s["consistency_score"] = round(consistency_score, 2)
        s["coverage"] = round(coverage, 2)
        s["score"] = round(success_rate * 50 + consistency_score * 30 + coverage * 20, 1)

    # Sort by score descending
    sorted_rank = sorted(stats.items(), key=lambda x: x[1]["score"], reverse=True)
    return sorted_rank


def assess_ticker_type_reliability() -> Dict[str, List[Dict[str, Any]]]:
    """Assess which provider is best for each ticker type (large cap, tech, penny, ADR, BDR)."""
    ticker_types = {
        "AAPL": "large_cap",
        "MSFT": "tech",
        "SNDL": "penny",
        "VALE": "ADR",
        "PETR4.SA": "BDR",
    }
    assessment: Dict[str, List[Dict[str, Any]]] = {}
    for ticker, ttype in ticker_types.items():
        best_provider = None
        best_price = None
        provider_prices = []
        for pname in PROVIDER_INFO:
            r = results[ticker].get(pname, {})
            if "error" not in r and r.get("price") is not None:
                pval = float(r["price"])
                provider_prices.append({"provider": pname, "price": pval})

        if provider_prices:
            vals = [p["price"] for p in provider_prices]
            consensus = mean(vals)
            for p in provider_prices:
                p["consensus"] = round(consensus, 2)
                p["pct_from_consensus"] = round((p["price"] - consensus) / consensus * 100, 2)

            # Best = closest to consensus
            provider_prices.sort(key=lambda x: abs(x["pct_from_consensus"]))
            best_provider = provider_prices[0]["provider"]

        assessment[ticker] = {
            "type": ttype,
            "best_provider": best_provider,
            "details": provider_prices,
        }
    return assessment


# ═══════════════════════════════════════════════════════════════════════
#  Report generation
# ═══════════════════════════════════════════════════════════════════════


def print_report() -> str:
    """Generate and print the full CROSS-PROVIDER DISCREPANCY TEST report."""
    report_parts = []

    def emit(line: str = "") -> None:
        report_parts.append(line)
        print(line)

    emit(f"\n{COL_BOLD}{COL_CYAN}{'='*80}{COL_RESET}")
    emit(f"{COL_BOLD}{COL_CYAN}  CROSS-PROVIDER DISCREPANCY TEST REPORT{COL_RESET}")
    emit(f"{COL_BOLD}{COL_CYAN}  Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}{COL_RESET}")
    emit(f"{COL_BOLD}{COL_CYAN}{'='*80}{COL_RESET}\n")

    # ── Environment summary ──────────────────────────────────────────
    emit(f"{COL_BOLD}ENVIRONMENT:{COL_RESET}")
    for pname, pinfo in PROVIDER_INFO.items():
        if pinfo["key_required"]:
            key = os.getenv(pinfo["api_key_var"])
            status = f"{COL_GREEN}SET{COL_RESET}" if key else f"{COL_RED}NOT SET{COL_RESET}"
            emit(f"  {pname:16s}  key={pinfo['api_key_var']:<24s} {status}")
        else:
            emit(f"  {pname:16s}  no key required (free)")
    emit()

    # ── Price table ──────────────────────────────────────────────────
    emit(f"{COL_BOLD}PRICE COMPARISON TABLE:{COL_RESET}")
    emit(build_price_table())
    emit()

    # ── Side-by-side summary ─────────────────────────────────────────
    emit(f"{COL_BOLD}SIDE-BY-SIDE PRICE SUMMARY:{COL_RESET}")
    for ticker in TICKERS:
        parts = [f"{ticker:10s}:"]
        for pname in PROVIDER_INFO:
            r = results[ticker].get(pname, {})
            if "error" not in r and r.get("price") is not None:
                parts.append(f"{pname}=${float(r['price']):.2f}")
            else:
                parts.append(f"{pname}=ERR")
        emit("  " + " | ".join(parts))
    emit()

    # ── Outliers ─────────────────────────────────────────────────────
    emit(f"{COL_BOLD}{COL_YELLOW}OUTLIER DETECTION (|z| > 2.0):{COL_RESET}")
    outliers = detect_outliers()
    if outliers:
        for o in outliers:
            emit(f"  {COL_RED}[OUTLIER] {o['ticker']} / {o['provider']}: "
                 f"${o['value']:.2f} vs mean=${o['mean']} "
                 f"(z={o['z_score']:.1f}, {o['pct_from_mean']:+.2f}%){COL_RESET}")
    else:
        emit(f"  {COL_GREEN}No outliers detected (all prices within 2-sigma).{COL_RESET}")
    emit()

    # ── Volume consistency ───────────────────────────────────────────
    emit(f"{COL_BOLD}VOLUME CONSISTENCY CHECK (>20% deviation from median):{COL_RESET}")
    vol_disc = check_volume_consistency()
    if vol_disc:
        for v in vol_disc:
            emit(f"  {COL_RED}[VOLUME] {v['ticker']} / {v['provider']}: "
                 f"vol={v['volume']:,} vs median={v['median_volume']:,} "
                 f"({v['deviation_pct']:+.1f}%){COL_RESET}")
    else:
        emit(f"  {COL_GREEN}Volume consistent across providers (no >20% deviations).{COL_RESET}")
    emit()

    # ── Historical close comparison (15 days ago) ────────────────────
    emit(f"{COL_BOLD}HISTORICAL CLOSE COMPARISON (~15 days ago):{COL_RESET}")
    hist_disc = compare_historical_close(15)
    if hist_disc:
        for h in hist_disc:
            emit(f"  {COL_RED}[HIST] {h['ticker']} / {h['provider']}: "
                 f"close={h['close_15d_ago']:.2f} on {h['date']} "
                 f"(avg={h['avg_close']:.2f}, diff={h['pct_diff_from_avg']:+.2f}%){COL_RESET}")
    else:
        emit(f"  {COL_GREEN}Historical close consistent across providers.{COL_RESET}")

    # Show what each provider returned for historical close
    emit(f"\n{COL_BOLD}HISTORICAL CLOSE RAW DATA:{COL_RESET}")
    for ticker in TICKERS:
        emit(f"  {ticker}:")
        for pname in PROVIDER_INFO:
            if pname == "stooq":
                emit(f"    {pname:16s}: N/A (no candle endpoint)")
                continue
            cr = candle_results.get(ticker, {}).get(pname, {})
            if "error" in cr:
                emit(f"    {pname:16s}: ERR - {cr['error'][:50]}")
                continue
            candles = cr.get("candles", [])
            if not candles or not isinstance(candles, list):
                emit(f"    {pname:16s}: No candles")
                continue
            # Show first and last candle date
            try:
                first_dt = candles[0].get("datetime", candles[0].get("time", "?"))[:10]
                last_dt = candles[-1].get("datetime", candles[-1].get("time", "?"))[:10]
                close_last = candles[-1].get("close", "?")
                emit(f"    {pname:16s}: {len(candles)} candles, "
                     f"{first_dt} to {last_dt}, last_close={close_last}")
            except Exception:
                emit(f"    {pname:16s}: {len(candles)} candles (parse error)")
    emit()

    # ── Reliability ranking ──────────────────────────────────────────
    emit(f"{COL_BOLD}PROVIDER RELIABILITY RANKING:{COL_RESET}")
    ranking = rank_reliability()
    emit(f"  {'Rank':>4s} {'Provider':16s} {'Success':>8s} {'Consistency':>12s} {'Coverage':>9s} {'Score':>6s}")
    emit(f"  {'-'*4} {'-'*16} {'-'*8} {'-'*12} {'-'*9} {'-'*6}")
    for rank, (pname, s) in enumerate(ranking, 1):
        emit(f"  {rank:>4d} {pname:16s} {s['success_rate']:>7.0%} {s['consistency_score']:>11.0%} {s['coverage']:>8.0%} {s['score']:>6.1f}")
    emit()

    # ── Ticker type recommendation ───────────────────────────────────
    emit(f"{COL_BOLD}BEST PROVIDER PER TICKER TYPE:{COL_RESET}")
    assessment = assess_ticker_type_reliability()
    for ticker, info in assessment.items():
        emit(f"  {ticker:10s} ({info['type']:12s}): best={info['best_provider'] or 'N/A'}")
        for d in info["details"]:
            emit(f"             {d['provider']:16s} ${d['price']:<8.2f}  "
                 f"(consensus=${d['consensus']}, {d['pct_from_consensus']:+.2f}%)")
    emit()

    # ── Recommendations ──────────────────────────────────────────────
    emit(f"{COL_BOLD}RECOMMENDATIONS:{COL_RESET}")

    # What's the most reliable provider overall?
    if ranking:
        best = ranking[0]
        emit(f"  1. Most reliable overall: {best[0]} (score={best[1]['score']})")

    # Any outliers that need investigation?
    if outliers:
        emit(f"  2. {COL_RED}ACTION REQUIRED:{COL_RESET} Investigate {len(outliers)} outlier(s):")
        for o in outliers:
            emit(f"     - {o['ticker']}: {o['provider']} reports ${o['value']:.2f} "
                 f"vs mean ${o['mean']:.2f}")
    else:
        emit(f"  2. No price outliers detected — providers agree.")

    # Volume issues?
    if vol_disc:
        emit(f"  3. {COL_YELLOW}CAUTION:{COL_RESET} {len(vol_disc)} volume discrepancy(ies) found. "
             f"Volume data may be unreliable for those tickers.")
    else:
        emit(f"  3. Volume data is consistent across providers.")

    # For PETR4.SA (BDR), which provider works best?
    emit(f"  4. PETR4.SA (BDR) recommendation:")
    for pname in PROVIDER_INFO:
        r = results.get("PETR4.SA", {}).get(pname, {})
        if "error" not in r and r.get("price") is not None:
            emit(f"     - {pname}: OK (price=${float(r['price']):.2f})")
        else:
            err = r.get("error", "N/A")
            emit(f"     - {pname}: FAIL ({err})")

    # For SNDL (penny stock)
    emit(f"  5. SNDL (penny stock) recommendation:")
    providers_ok = []
    for pname in PROVIDER_INFO:
        r = results.get("SNDL", {}).get(pname, {})
        if "error" not in r and r.get("price") is not None:
            providers_ok.append(f"{pname} (${float(r['price']):.2f})")
    if providers_ok:
        emit(f"     Working providers: {', '.join(providers_ok)}")
    else:
        emit(f"     {COL_RED}No provider returned SNDL price{COL_RESET}")

    emit(f"\n{COL_BOLD}{COL_CYAN}{'='*80}{COL_RESET}")
    emit(f"{COL_BOLD}{COL_CYAN}  END OF REPORT{COL_RESET}")
    emit(f"{COL_BOLD}{COL_CYAN}{'='*80}{COL_RESET}")

    return "\n".join(report_parts)


# ═══════════════════════════════════════════════════════════════════════
#  Entry point
# ═══════════════════════════════════════════════════════════════════════

def main() -> int:
    print(f"{COL_BOLD}{COL_CYAN}SuperEzio Cross-Provider Discrepancy Test{COL_RESET}")
    print(f"{COL_CYAN}Testing {len(TICKERS)} tickers x {len(PROVIDER_INFO)} providers{COL_RESET}")
    print(f"{COL_CYAN}{'='*70}{COL_RESET}")

    # Phase 1: prices
    run_price_tests()

    # Phase 2: candles (historical)
    print(f"\n{COL_CYAN}{'='*70}{COL_RESET}")
    print(f"{COL_BOLD}  PHASE 2: HISTORICAL CANDLES (1M){COL_RESET}")
    print(f"{COL_CYAN}{'='*70}{COL_RESET}")
    run_candle_tests()

    # Phase 3: report
    print(f"\n{COL_CYAN}{'='*70}{COL_RESET}")
    print(f"{COL_BOLD}  PHASE 3: GENERATING REPORT{COL_RESET}")
    print(f"{COL_CYAN}{'='*70}{COL_RESET}")
    print_report()

    return 0


if __name__ == "__main__":
    sys.exit(main())
