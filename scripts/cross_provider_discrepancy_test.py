#!/usr/bin/env python3
"""
Cross-Provider Discrepancy Test — SuperEzio F51

Tests 5 tickers against ALL available price providers:
  TwelveData, AlphaVantage, AKShare, yfinance, Stooq

Output: CROSS-PROVIDER DISCREPANCY TEST report with tables, outliers,
volume consistency, historical close comparison, and reliability ranking.

Each provider call has a 30-second timeout via concurrent.futures.
"""

from __future__ import annotations

import os
import sys
import math
import signal
import functools
import concurrent.futures
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# ── Configuration ────────────────────────────────────────────────────
TICKERS = ["AAPL", "MSFT", "SNDL", "VALE", "PETR4.SA"]
PROVIDER_NAMES = ["twelve_data", "alpha_vantage", "akshare", "yfinance", "stooq"]
PROVIDER_TIMEOUT = 35  # seconds per call

PROVIDER_INFO = {
    "twelve_data":   {"key_required": True,  "api_key_var": "TWELVE_DATA_API_KEY"},
    "alpha_vantage": {"key_required": True,  "api_key_var": "ALPHA_VANTAGE_API_KEY"},
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

# Stored results
results: Dict[str, Dict[str, Any]] = {}
candle_results: Dict[str, Dict[str, Any]] = {}

# ═══════════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════════


def _load_env(path: str) -> None:
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip().strip("\"'").strip())
    except FileNotFoundError:
        pass


_load_env(os.path.join(PROJECT_ROOT, ".env.local"))
_load_env(os.path.join(PROJECT_ROOT, ".env"))


def _get_provider(name: str):
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


def _get_price_from(pname: str, provider, symbol: str) -> Dict[str, Any]:
    try:
        if pname == "alpha_vantage":
            return provider.get_quote(symbol)
        elif pname == "twelve_data":
            return provider.get_price(symbol)
        elif pname == "akshare":
            return provider.get_price(symbol, market="US")
        elif pname == "yfinance":
            return provider.get_price(symbol, market="US")
        elif pname == "stooq":
            return provider.get_price(symbol, market="US")
    except Exception as exc:
        return {"error": f"{pname}_exception: {exc}"}


def _get_candles_from(pname: str, provider, symbol: str, tf: str = "1M") -> Dict[str, Any]:
    try:
        if pname == "twelve_data":
            return provider.get_candles(symbol, timeframe=tf)
        elif pname == "alpha_vantage":
            return provider.get_ohlcv(symbol, timeframe=tf)
        elif pname == "akshare":
            return provider.get_candles(symbol, timeframe=tf, market="US")
        elif pname == "yfinance":
            return provider.get_candles(symbol, timeframe=tf, market="US")
        elif pname == "stooq":
            return {"error": "stooq_no_candles"}
    except Exception as exc:
        return {"error": f"{pname}_candles_exception: {exc}"}


def mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def std_dev(values: list[float], avg: float | None = None) -> float:
    if len(values) < 2:
        return 0.0
    avg = avg or mean(values)
    return math.sqrt(sum((v - avg) ** 2 for v in values) / len(values))


def z_score(value: float, avg: float, sd: float) -> float:
    if sd == 0:
        return 0.0
    return (value - avg) / sd


def pct_diff(a: float, b: float) -> float:
    if a == 0 and b == 0:
        return 0.0
    avg = (abs(a) + abs(b)) / 2
    if avg == 0:
        return 0.0
    return abs(a - b) / avg * 100


def check_provider_available(pname: str) -> bool:
    """Check if a provider can be used (API key check)."""
    pinfo = PROVIDER_INFO[pname]
    if pinfo["key_required"]:
        return bool(os.getenv(pinfo["api_key_var"]))
    return True


# ═══════════════════════════════════════════════════════════════════════
#  Parallel execution with timeout
# ═══════════════════════════════════════════════════════════════════════


def _run_with_timeout(func, timeout: int = PROVIDER_TIMEOUT) -> Any:
    """Run a function in a thread with timeout."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        fut = executor.submit(func)
        try:
            return fut.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            return {"error": f"timeout_{timeout}s"}
        except Exception as exc:
            return {"error": f"execution_error: {exc}"}


def run_price_test(ticker: str) -> None:
    """Run price test for one ticker across all providers in parallel."""
    per_provider_results: Dict[str, Any] = {}
    futures: Dict[str, concurrent.futures.Future] = {}

    print(f"\n{COL_CYAN}{'='*70}{COL_RESET}")
    print(f"{COL_BOLD}  TICKER: {ticker}{COL_RESET}")
    print(f"{COL_CYAN}{'='*70}{COL_RESET}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        for pname in PROVIDER_NAMES:
            if not check_provider_available(pname):
                print(f"  {COL_YELLOW}[SKIP] {pname}: API key not set{COL_RESET}")
                per_provider_results[pname] = {"error": f"no_{PROVIDER_INFO[pname]['api_key_var']}_set"}
                continue

            provider = _get_provider(pname)
            if provider is None:
                print(f"  {COL_YELLOW}[SKIP] {pname}: instantiation failed{COL_RESET}")
                per_provider_results[pname] = {"error": "instantiation_failed"}
                continue

            future = pool.submit(_get_price_from, pname, provider, ticker)
            futures[pname] = future

        for pname, future in futures.items():
            try:
                result = future.result(timeout=PROVIDER_TIMEOUT)
            except concurrent.futures.TimeoutError:
                result = {"error": f"timeout_{PROVIDER_TIMEOUT}s"}
            except Exception as exc:
                result = {"error": f"execution_error: {exc}"}

            per_provider_results[pname] = result
            if "error" in result:
                print(f"  {COL_RED}[ERR]  {pname:16s}: {result['error'][:60]}{COL_RESET}")
            else:
                price = result.get("price", "N/A")
                volume = result.get("volume", "N/A")
                print(f"  {COL_GREEN}[OK]   {pname:16s}: price={price}  volume={volume}{COL_RESET}")

    results[ticker] = per_provider_results


def run_candle_test(ticker: str) -> None:
    """Run candle test for one ticker across all providers in parallel."""
    per_provider_results: Dict[str, Any] = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        futures = {}
        for pname in PROVIDER_NAMES:
            if pname == "stooq":
                per_provider_results[pname] = {"error": "stooq_no_candles"}
                continue
            if not check_provider_available(pname):
                per_provider_results[pname] = {"error": f"no_{PROVIDER_INFO[pname]['api_key_var']}_set"}
                continue
            provider = _get_provider(pname)
            if provider is None:
                per_provider_results[pname] = {"error": "instantiation_failed"}
                continue
            future = pool.submit(_get_candles_from, pname, provider, ticker, "1M")
            futures[pname] = future

        for pname, future in futures.items():
            try:
                result = future.result(timeout=PROVIDER_TIMEOUT)
            except concurrent.futures.TimeoutError:
                result = {"error": f"timeout_{PROVIDER_TIMEOUT}s"}
            except Exception as exc:
                result = {"error": f"candle_execution_error: {exc}"}
            per_provider_results[pname] = result

    candle_results[ticker] = per_provider_results


# ═══════════════════════════════════════════════════════════════════════
#  Analysis
# ═══════════════════════════════════════════════════════════════════════


def build_price_table() -> str:
    lines = []
    header = f"{'TICKER':12s} {'Provider':16s} {'Price':>10s} {'Volume':>12s} {'Source':>10s}"
    lines.append(header)
    lines.append("-" * len(header))
    for ticker in TICKERS:
        for pname in PROVIDER_NAMES:
            r = results[ticker].get(pname, {})
            if "error" in r:
                lines.append(f"{ticker:12s} {pname:16s} {'---':>10s} {'---':>12s} {'ERR':>10s}")
            else:
                pv = r.get("price")
                ps = f"{pv:.2f}" if pv is not None else "N/A"
                vv = r.get("volume")
                vs = f"{vv:,}" if vv is not None else "N/A"
                src = r.get("source", pname)[:10]
                lines.append(f"{ticker:12s} {pname:16s} {ps:>10s} {vs:>12s} {src:>10s}")
    return "\n".join(lines)


def detect_outliers() -> List[Dict[str, Any]]:
    outliers = []
    for ticker in TICKERS:
        prices = []
        for pname in PROVIDER_NAMES:
            r = results[ticker].get(pname, {})
            if "error" not in r and r.get("price") is not None:
                prices.append((pname, float(r["price"])))
        if len(prices) < 3:
            continue
        vals = [p[1] for p in prices]
        avg = mean(vals)
        sd = std_dev(vals, avg)
        for pname, pval in prices:
            zs = z_score(pval, avg, sd)
            if abs(zs) > 2.0:
                outliers.append({"ticker": ticker, "provider": pname, "value": pval,
                                 "mean": round(avg, 2), "z_score": round(zs, 2),
                                 "pct_from_mean": round((pval - avg) / avg * 100, 2)})
    return outliers


def check_volume_consistency() -> List[Dict[str, Any]]:
    discrepancies = []
    for ticker in TICKERS:
        volumes = []
        for pname in PROVIDER_NAMES:
            r = results[ticker].get(pname, {})
            if "error" not in r and r.get("volume") is not None:
                vol = int(r["volume"])
                if vol > 0:
                    volumes.append((pname, vol))
        if len(volumes) < 2:
            continue
        sorted_vols = sorted(v[1] for v in volumes)
        mid = len(sorted_vols) // 2
        median_vol = sorted_vols[mid] if len(sorted_vols) % 2 else (
            sorted_vols[mid - 1] + sorted_vols[mid]) / 2
        for pname, vol in volumes:
            if median_vol == 0:
                continue
            dev = abs(vol - median_vol) / median_vol * 100
            if dev > 20:
                discrepancies.append({"ticker": ticker, "provider": pname, "volume": vol,
                                      "median_volume": int(median_vol), "deviation_pct": round(dev, 1)})
    return discrepancies


def compare_historical_close(days_ago: int = 15) -> List[Dict[str, Any]]:
    discrepancies = []
    for ticker in TICKERS:
        closes = []
        for pname in PROVIDER_NAMES:
            if pname == "stooq":
                continue
            cr = candle_results.get(ticker, {}).get(pname, {})
            if "error" in cr:
                continue
            candles = cr.get("candles", [])
            if not candles or not isinstance(candles, list) or len(candles) < days_ago + 1:
                continue
            # Determine sort order
            try:
                fd = candles[0].get("datetime", candles[0].get("time", ""))
                ld = candles[-1].get("datetime", candles[-1].get("time", ""))
                oldest_first = str(fd) < str(ld)
            except Exception:
                oldest_first = True
            idx = max(0, len(candles) - days_ago - 1) if oldest_first else min(len(candles) - 1, days_ago)
            c = candles[idx]
            cv = float(c.get("close", 0))
            dt = str(c.get("datetime", c.get("time", "?")))[:10]
            if cv > 0:
                closes.append((pname, cv, dt))
        if len(closes) < 2:
            continue
        vals = [c[1] for c in closes]
        avg = mean(vals)
        for pname, cv, dt in closes:
            pd = pct_diff(cv, avg) if avg > 0 else 0
            if pd > 2.0:
                discrepancies.append({"ticker": ticker, "provider": pname,
                                      "close_15d_ago": cv, "date": dt,
                                      "avg_close": round(avg, 2), "pct_diff_from_avg": round(pd, 2)})
    return discrepancies


def rank_reliability() -> List[Tuple[str, Dict[str, Any]]]:
    stats = {}
    for pname in PROVIDER_NAMES:
        stats[pname] = {"attempts": 0, "successes": 0, "prices": [], "score": 0}
    for ticker in TICKERS:
        for pname in PROVIDER_NAMES:
            stats[pname]["attempts"] += 1
            r = results[ticker].get(pname, {})
            if "error" not in r and r.get("price") is not None:
                stats[pname]["successes"] += 1
                stats[pname]["prices"].append(float(r["price"]))
    for pname, s in stats.items():
        sr = s["successes"] / s["attempts"] if s["attempts"] else 0
        if len(s["prices"]) >= 2:
            ap = mean(s["prices"])
            sd = std_dev(s["prices"], ap)
            cv = sd / ap if ap > 0 else 1.0
            cs = max(0, 1.0 - min(cv * 10, 1.0))
        else:
            cs = 0.5
        cov = s["successes"] / s["attempts"] if s["attempts"] else 0
        s["success_rate"] = round(sr, 2)
        s["consistency_score"] = round(cs, 2)
        s["coverage"] = round(cov, 2)
        s["score"] = round(sr * 50 + cs * 30 + cov * 20, 1)
    return sorted(stats.items(), key=lambda x: x[1]["score"], reverse=True)


def assess_ticker_type_reliability() -> Dict[str, Any]:
    ttypes = {"AAPL": "large_cap", "MSFT": "tech", "SNDL": "penny", "VALE": "ADR", "PETR4.SA": "BDR"}
    assessment = {}
    for ticker, ttype in ttypes.items():
        prices = []
        for pname in PROVIDER_NAMES:
            r = results[ticker].get(pname, {})
            if "error" not in r and r.get("price") is not None:
                prices.append({"provider": pname, "price": float(r["price"])})
        if prices:
            vals = [p["price"] for p in prices]
            consensus = mean(vals)
            for p in prices:
                p["consensus"] = round(consensus, 2)
                p["pct_from_consensus"] = round((p["price"] - consensus) / consensus * 100, 2)
            prices.sort(key=lambda x: abs(x["pct_from_consensus"]))
            best = prices[0]["provider"] if prices else None
        else:
            best = None
        assessment[ticker] = {"type": ttype, "best_provider": best, "details": prices}
    return assessment


# ═══════════════════════════════════════════════════════════════════════
#  Report
# ═══════════════════════════════════════════════════════════════════════


def print_report() -> str:
    parts = []
    def emit(line: str = ""):
        parts.append(line)
        print(line)

    emit(f"\n{COL_BOLD}{COL_CYAN}{'='*80}{COL_RESET}")
    emit(f"{COL_BOLD}{COL_CYAN}  CROSS-PROVIDER DISCREPANCY TEST REPORT{COL_RESET}")
    emit(f"{COL_BOLD}{COL_CYAN}  Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}{COL_RESET}")
    emit(f"{COL_BOLD}{COL_CYAN}{'='*80}{COL_RESET}\n")

    # Environment
    emit(f"{COL_BOLD}ENVIRONMENT:{COL_RESET}")
    for pname in PROVIDER_NAMES:
        pinfo = PROVIDER_INFO[pname]
        if pinfo["key_required"]:
            key = os.getenv(pinfo["api_key_var"])
            status = f"{COL_GREEN}SET{COL_RESET}" if key else f"{COL_RED}NOT SET{COL_RESET}"
            emit(f"  {pname:16s}  key={pinfo['api_key_var']:<24s} {status}")
        else:
            emit(f"  {pname:16s}  no key required (free)")
    emit(f"  {'':16s}  timeout={PROVIDER_TIMEOUT}s per call")
    emit()

    # Price table
    emit(f"{COL_BOLD}PRICE COMPARISON TABLE:{COL_RESET}")
    emit(build_price_table())
    emit()

    # Side-by-side
    emit(f"{COL_BOLD}SIDE-BY-SIDE PRICE SUMMARY:{COL_RESET}")
    for ticker in TICKERS:
        parts_line = [f"{ticker:10s}:"]
        for pname in PROVIDER_NAMES:
            r = results[ticker].get(pname, {})
            if "error" not in r and r.get("price") is not None:
                parts_line.append(f"{pname}=${float(r['price']):.2f}")
            else:
                parts_line.append(f"{pname}=ERR")
        emit("  " + " | ".join(parts_line))
    emit()

    # Outliers
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

    # Volume
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

    # Historical close
    emit(f"{COL_BOLD}HISTORICAL CLOSE COMPARISON (~15 days ago):{COL_RESET}")
    hist_disc = compare_historical_close(15)
    if hist_disc:
        for h in hist_disc:
            emit(f"  {COL_RED}[HIST] {h['ticker']} / {h['provider']}: "
                 f"close={h['close_15d_ago']:.2f} on {h['date']} "
                 f"(avg={h['avg_close']:.2f}, diff={h['pct_diff_from_avg']:+.2f}%){COL_RESET}")
    else:
        emit(f"  {COL_GREEN}Historical close consistent across providers.{COL_RESET}")

    # Raw candle data
    emit(f"\n{COL_BOLD}HISTORICAL CANDLE DATA SUMMARY:{COL_RESET}")
    for ticker in TICKERS:
        emit(f"  {ticker}:")
        for pname in PROVIDER_NAMES:
            if pname == "stooq":
                emit(f"    {pname:16s}: N/A (no candle endpoint)")
                continue
            cr = candle_results.get(ticker, {}).get(pname, {})
            if "error" in cr:
                emit(f"    {pname:16s}: ERR - {str(cr['error'])[:60]}")
                continue
            candles = cr.get("candles", [])
            if not candles or not isinstance(candles, list):
                emit(f"    {pname:16s}: No candles returned")
                continue
            try:
                fd = str(candles[0].get("datetime", candles[0].get("time", "?")))[:10]
                ld = str(candles[-1].get("datetime", candles[-1].get("time", "?")))[:10]
                lc = candles[-1].get("close", "?")
                lv = candles[-1].get("volume", "?")
                emit(f"    {pname:16s}: {len(candles)} candles, {fd} to {ld}, "
                     f"last_close={lc}, last_vol={lv}")
            except Exception:
                emit(f"    {pname:16s}: {len(candles)} candles (parse error)")
    emit()

    # Reliability ranking
    emit(f"{COL_BOLD}PROVIDER RELIABILITY RANKING:{COL_RESET}")
    ranking = rank_reliability()
    hdr = f"  {'Rank':>4s} {'Provider':16s} {'Success':>8s} {'Consistency':>12s} {'Coverage':>9s} {'Score':>6s}"
    emit(hdr)
    emit(f"  {'-'*4} {'-'*16} {'-'*8} {'-'*12} {'-'*9} {'-'*6}")
    for rk, (pname, s) in enumerate(ranking, 1):
        emit(f"  {rk:>4d} {pname:16s} {s['success_rate']:>7.0%} {s['consistency_score']:>11.0%} {s['coverage']:>8.0%} {s['score']:>6.1f}")
    emit()

    # Ticker type recommendations
    emit(f"{COL_BOLD}BEST PROVIDER PER TICKER TYPE:{COL_RESET}")
    assessment = assess_ticker_type_reliability()
    for ticker, info in assessment.items():
        emit(f"  {ticker:10s} ({info['type']:12s}): best={info['best_provider'] or 'N/A'}")
        for d in info["details"]:
            emit(f"             {d['provider']:16s} ${d['price']:<8.2f}  "
                 f"(consensus=${d['consensus']}, {d['pct_from_consensus']:+.2f}%)")
    emit()

    # Recommendations
    emit(f"{COL_BOLD}RECOMMENDATIONS:{COL_RESET}")
    if ranking:
        emit(f"  1. Most reliable overall: {ranking[0][0]} (score={ranking[0][1]['score']})")
    if outliers:
        emit(f"  2. {COL_RED}ACTION REQUIRED:{COL_RESET} {len(outliers)} outlier(s) found:")
        for o in outliers:
            emit(f"     - {o['ticker']}: {o['provider']} ${o['value']:.2f} vs mean ${o['mean']:.2f}")
    else:
        emit(f"  2. No price outliers detected.")
    if vol_disc:
        emit(f"  3. {COL_YELLOW}CAUTION:{COL_RESET} {len(vol_disc)} volume discrepancy(ies) found.")
    else:
        emit(f"  3. Volume data is consistent across providers.")

    # PETR4.SA
    emit(f"  4. PETR4.SA (BDR) recommendation:")
    for pname in PROVIDER_NAMES:
        r = results.get("PETR4.SA", {}).get(pname, {})
        if "error" not in r and r.get("price") is not None:
            emit(f"     - {pname}: OK (${float(r['price']):.2f})")
        else:
            emit(f"     - {pname}: FAIL ({r.get('error', 'N/A')[:40]})")

    # SNDL (penny stock)
    emit(f"  5. SNDL (penny stock) recommendation:")
    ok_providers = []
    for pname in PROVIDER_NAMES:
        r = results.get("SNDL", {}).get(pname, {})
        if "error" not in r and r.get("price") is not None:
            ok_providers.append(f"{pname} (${float(r['price']):.2f})")
    if ok_providers:
        emit(f"     Working: {', '.join(ok_providers)}")
    else:
        emit(f"     {COL_RED}No provider returned SNDL price{COL_RESET}")

    emit(f"\n{COL_BOLD}{COL_CYAN}{'='*80}{COL_RESET}")
    emit(f"{COL_BOLD}{COL_CYAN}  END OF REPORT{COL_RESET}")
    emit(f"{COL_BOLD}{COL_CYAN}{'='*80}{COL_RESET}")
    return "\n".join(parts)


# ═══════════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════════

def main() -> int:
    print(f"{COL_BOLD}{COL_CYAN}SuperEzio Cross-Provider Discrepancy Test{COL_RESET}")
    print(f"{COL_CYAN}Testing {len(TICKERS)} tickers x {len(PROVIDER_NAMES)} providers{COL_RESET}")
    print(f"{COL_CYAN}Each call has {PROVIDER_TIMEOUT}s timeout{COL_RESET}")
    print(f"{COL_CYAN}{'='*70}{COL_RESET}")

    # Phase 1: Prices (parallel per ticker)
    for ticker in TICKERS:
        run_price_test(ticker)

    # Phase 2: Candles (parallel per ticker)
    print(f"\n{COL_CYAN}{'='*70}{COL_RESET}")
    print(f"{COL_BOLD}  PHASE 2: HISTORICAL CANDLES (1M){COL_RESET}")
    print(f"{COL_CYAN}{'='*70}{COL_RESET}")
    for ticker in TICKERS:
        print(f"  Fetching candles for {ticker}...")
        run_candle_test(ticker)

    # Phase 3: Report
    print(f"\n{COL_CYAN}{'='*70}{COL_RESET}")
    print(f"{COL_BOLD}  PHASE 3: GENERATING REPORT{COL_RESET}")
    print(f"{COL_CYAN}{'='*70}{COL_RESET}")
    print_report()
    return 0


if __name__ == "__main__":
    sys.exit(main())
