#!/usr/bin/env python3
"""
Cross-Provider Discrepancy Test — SuperEzio F51

Tests 5 tickers against available price providers:
  TwelveData, AlphaVantage, AKShare, yfinance, Stooq

Finds DISCREPANCIES between providers — if one says $325 and another says $327,
identifies which is right using consensus analysis.

Status of providers:
  - TwelveData:   API key present, rate limited (8/min)
  - AlphaVantage: API key present, works
  - AKShare:      Keyless, stock_us_spot() downloads ALL us stocks (~893 rows) — very slow
  - yfinance:     Keyless, works
  - Stooq:        Keyless, API changed (requires JS now), 404 on CSV endpoint
"""

from __future__ import annotations

import os
import sys
import math
import time
import concurrent.futures
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# ── Configuration ────────────────────────────────────────────────────
TICKERS = ["AAPL", "MSFT", "SNDL", "VALE", "PETR4.SA"]

# Provider definitions: (name, has_candles, is_available_check)
PROVIDERS_CONFIG = [
    {"name": "twelve_data",   "candles": True,  "key": "TWELVE_DATA_API_KEY"},
    {"name": "alpha_vantage", "candles": True,  "key": "ALPHA_VANTAGE_API_KEY"},
    {"name": "yfinance",      "candles": True,  "key": None},
    {"name": "akshare",       "candles": True,  "key": None},
    {"name": "stooq",         "candles": False, "key": None},
]
PROVIDER_TIMEOUT = 45  # seconds per call (AKShare is slow)

COL_RESET = "\033[0m"
COL_RED = "\033[91m"
COL_GREEN = "\033[92m"
COL_YELLOW = "\033[93m"
COL_CYAN = "\033[96m"
COL_BOLD = "\033[1m"

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


def _provider_available(pname: str) -> Tuple[bool, str]:
    """Check if provider is available. Returns (ok, reason)."""
    cfg = next((p for p in PROVIDERS_CONFIG if p["name"] == pname), None)
    if not cfg:
        return False, "unknown_provider"
    if cfg["key"]:
        if not os.getenv(cfg["key"]):
            return False, f"missing_key_{cfg['key']}"
    # Special checks
    if pname == "twelve_data":
        # Rate limited to 8 requests per minute
        pass
    if pname == "akshare":
        # Check if akshare is importable
        try:
            import akshare  # noqa: F401
        except ImportError:
            return False, "akshare_not_installed"
    if pname == "yfinance":
        try:
            import yfinance  # noqa: F401
        except ImportError:
            return False, "yfinance_not_installed"
    return True, "ok"


def _get_provider(pname: str):
    """Lazy-import and instantiate provider."""
    try:
        if pname == "twelve_data":
            from src.data.twelve_data import TwelveDataProvider
            return TwelveDataProvider()
        elif pname == "alpha_vantage":
            from src.data.alpha_vantage import AlphaVantageProvider
            return AlphaVantageProvider()
        elif pname == "yfinance":
            from src.data.yfinance_provider import YFinanceProvider
            return YFinanceProvider()
        elif pname == "akshare":
            from src.data.akshare_provider import AKShareProvider
            return AKShareProvider()
        elif pname == "stooq":
            from src.data.stooq_provider import StooqProvider
            return StooqProvider()
    except Exception as exc:
        return None


def _get_price(pname: str, provider, symbol: str) -> Dict[str, Any]:
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


def _get_candles(pname: str, provider, symbol: str, tf: str = "1M") -> Dict[str, Any]:
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


# Statistics
def mean(v: List[float]) -> float:
    return sum(v) / len(v) if v else 0.0

def std_dev(v: List[float], a: float | None = None) -> float:
    if len(v) < 2:
        return 0.0
    a = a or mean(v)
    return math.sqrt(sum((x - a) ** 2 for x in v) / len(v))

def z_score(v: float, a: float, sd: float) -> float:
    return (v - a) / sd if sd != 0 else 0.0


# ═══════════════════════════════════════════════════════════════════════
#  Parallel Test Runner
# ═══════════════════════════════════════════════════════════════════════

def run_all_price_tests():
    """Run price tests for all tickers x all providers in parallel batches."""
    print(f"\n{COL_BOLD}{COL_CYAN}PHASE 1: PRICE TESTS{COL_RESET}")
    print(f"{COL_CYAN}Testing {len(TICKERS)} tickers x {len(PROVIDERS_CONFIG)} providers{COL_RESET}")
    print(f"{COL_CYAN}Timeout per call: {PROVIDER_TIMEOUT}s{COL_RESET}\n")

    for ticker in TICKERS:
        results[ticker] = {}
        print(f"{COL_BOLD}-- {ticker} --{COL_RESET}")

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            futures = {}
            for cfg in PROVIDERS_CONFIG:
                pname = cfg["name"]
                ok, reason = _provider_available(pname)
                if not ok:
                    results[ticker][pname] = {"error": reason}
                    print(f"  {COL_YELLOW}[SKIP] {pname:16s}: {reason}{COL_RESET}")
                    continue
                provider = _get_provider(pname)
                if provider is None:
                    results[ticker][pname] = {"error": "instantiation_failed"}
                    print(f"  {COL_YELLOW}[SKIP] {pname:16s}: instantiation failed{COL_RESET}")
                    continue
                futures[pname] = pool.submit(_get_price, pname, provider, ticker)

            for pname, future in futures.items():
                try:
                    result = future.result(timeout=PROVIDER_TIMEOUT)
                except concurrent.futures.TimeoutError:
                    result = {"error": f"timeout_{PROVIDER_TIMEOUT}s"}
                except Exception as exc:
                    result = {"error": f"execution_error: {exc}"}

                results[ticker][pname] = result
                if "error" in result:
                    print(f"  {COL_RED}[ERR]  {pname:16s}: {str(result['error'])[:65]}{COL_RESET}")
                else:
                    price = result.get("price", "N/A")
                    vol = result.get("volume", "N/A")
                    print(f"  {COL_GREEN}[OK]   {pname:16s}: price={price}  volume={vol}{COL_RESET}")

        # Rate limiting: small pause if we hit TwelveData
        time.sleep(0.5)


def run_all_candle_tests():
    """Run candle tests for all tickers x all providers."""
    print(f"\n{COL_BOLD}{COL_CYAN}PHASE 2: HISTORICAL CANDLES (1M){COL_RESET}\n")

    for ticker in TICKERS:
        candle_results[ticker] = {}
        print(f"  {ticker}...", end=" ", flush=True)

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            futures = {}
            for cfg in PROVIDERS_CONFIG:
                pname = cfg["name"]
                if not cfg["candles"]:
                    candle_results[ticker][pname] = {"error": "no_candle_endpoint"}
                    continue
                ok, reason = _provider_available(pname)
                if not ok:
                    candle_results[ticker][pname] = {"error": reason}
                    continue
                provider = _get_provider(pname)
                if provider is None:
                    candle_results[ticker][pname] = {"error": "instantiation_failed"}
                    continue
                futures[pname] = pool.submit(_get_candles, pname, provider, ticker, "1M")

            for pname, future in futures.items():
                try:
                    result = future.result(timeout=PROVIDER_TIMEOUT)
                except concurrent.futures.TimeoutError:
                    result = {"error": f"timeout_{PROVIDER_TIMEOUT}s"}
                except Exception as exc:
                    result = {"error": f"candle_error: {exc}"}
                candle_results[ticker][pname] = result

        print("done")


# ═══════════════════════════════════════════════════════════════════════
#  Analysis
# ═══════════════════════════════════════════════════════════════════════

def build_price_table() -> str:
    lines = []
    hdr = f"{'TICKER':12s} {'Provider':16s} {'Price':>10s} {'Volume':>12s} {'Status':>12s}"
    lines.append(hdr)
    lines.append("-" * len(hdr))
    for ticker in TICKERS:
        for cfg in PROVIDERS_CONFIG:
            pname = cfg["name"]
            r = results[ticker].get(pname, {})
            if "error" in r:
                lines.append(f"{ticker:12s} {pname:16s} {'---':>10s} {'---':>12s} {'ERR':>12s}")
            else:
                pv = r.get("price")
                ps = f"{pv:.2f}" if pv is not None else "N/A"
                vv = r.get("volume")
                vs = f"{vv:,}" if vv is not None else "N/A"
                lines.append(f"{ticker:12s} {pname:16s} {ps:>10s} {vs:>12s} {'OK':>12s}")
    return "\n".join(lines)


def detect_outliers() -> List[Dict]:
    outliers = []
    for ticker in TICKERS:
        prices = []
        for cfg in PROVIDERS_CONFIG:
            r = results[ticker].get(cfg["name"], {})
            if "error" not in r and r.get("price") is not None and float(r["price"]) > 0:
                prices.append((cfg["name"], float(r["price"])))
        if len(prices) < 3:
            continue
        vals = [p[1] for p in prices]
        avg = mean(vals)
        sd = std_dev(vals, avg)
        if sd < avg * 0.001:  # tiny variance means all are essentially equal
            continue
        for pname, pval in prices:
            zs = z_score(pval, avg, sd)
            if abs(zs) > 2.0:
                outliers.append({"ticker": ticker, "provider": pname, "value": pval,
                                 "mean": round(avg, 2), "z_score": round(zs, 2),
                                 "pct_dev": round((pval - avg) / avg * 100, 2)})
    return outliers


def check_volume() -> List[Dict]:
    discrepancies = []
    for ticker in TICKERS:
        vols = []
        for cfg in PROVIDERS_CONFIG:
            r = results[ticker].get(cfg["name"], {})
            if "error" not in r and r.get("volume") is not None:
                v = int(r["volume"])
                if v > 0:
                    vols.append((cfg["name"], v))
        if len(vols) < 2:
            continue
        sv = sorted(v[1] for v in vols)
        mid = len(sv) // 2
        median_v = sv[mid] if len(sv) % 2 else (sv[mid - 1] + sv[mid]) / 2
        for pname, v in vols:
            if median_v == 0:
                continue
            dev = abs(v - median_v) / median_v * 100
            if dev > 20:
                discrepancies.append({"ticker": ticker, "provider": pname, "volume": v,
                                      "median_volume": int(median_v), "deviation_pct": round(dev, 1)})
    return discrepancies


def compare_historical_close(days_ago: int = 15) -> List[Dict]:
    discrepancies = []
    for ticker in TICKERS:
        closes = []
        for cfg in PROVIDERS_CONFIG:
            pname = cfg["name"]
            if not cfg["candles"]:
                continue
            cr = candle_results.get(ticker, {}).get(pname, {})
            if "error" in cr:
                continue
            candles = cr.get("candles", [])
            if not isinstance(candles, list) or len(candles) < days_ago + 1:
                continue
            try:
                fd = str(candles[0].get("datetime", candles[0].get("time", "")))
                ld = str(candles[-1].get("datetime", candles[-1].get("time", "")))
                oldest_first = fd < ld
            except Exception:
                oldest_first = True
            idx = max(0, len(candles) - days_ago - 1) if oldest_first else min(len(candles) - 1, days_ago)
            cv = float(candles[idx].get("close", 0))
            dt = str(candles[idx].get("datetime", candles[idx].get("time", "?")))[:10]
            if cv > 0:
                closes.append((pname, cv, dt))
        if len(closes) < 2:
            continue
        vals = [c[1] for c in closes]
        avg = mean(vals)
        for pname, cv, dt in closes:
            if avg > 0:
                pd = abs(cv - avg) / avg * 100
                if pd > 2.0:
                    discrepancies.append({"ticker": ticker, "provider": pname,
                                          "close": cv, "date": dt,
                                          "avg_close": round(avg, 2), "pct_diff": round(pd, 2)})
    return discrepancies


def rank_providers() -> List[Tuple]:
    stats = {}
    for cfg in PROVIDERS_CONFIG:
        pname = cfg["name"]
        stats[pname] = {"attempts": 0, "successes": 0, "prices": [], "score": 0}
    for ticker in TICKERS:
        for cfg in PROVIDERS_CONFIG:
            pname = cfg["name"]
            stats[pname]["attempts"] += 1
            r = results[ticker].get(pname, {})
            if "error" not in r and r.get("price") is not None:
                stats[pname]["successes"] += 1
                stats[pname]["prices"].append(float(r["price"]))
    for pname, s in stats.items():
        sr = s["successes"] / s["attempts"] if s["attempts"] else 0
        if len(s["prices"]) >= 3:
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


def assess_by_type() -> Dict:
    ttypes = {"AAPL": "large_cap", "MSFT": "tech", "SNDL": "penny", "VALE": "ADR", "PETR4.SA": "BDR"}
    assessment = {}
    for ticker, ttype in ttypes.items():
        prices = []
        for cfg in PROVIDERS_CONFIG:
            r = results[ticker].get(cfg["name"], {})
            if "error" not in r and r.get("price") is not None:
                prices.append({"provider": cfg["name"], "price": float(r["price"])})
        if prices:
            vals = [p["price"] for p in prices]
            con = mean(vals)
            for p in prices:
                p["consensus"] = round(con, 2)
                p["pct_from_consensus"] = round((p["price"] - con) / con * 100, 2)
            prices.sort(key=lambda x: abs(x["pct_from_consensus"]))
            best = prices[0]["provider"] if prices else None
        else:
            best = None
        assessment[ticker] = {"type": ttype, "best_provider": best, "details": prices}
    return assessment


# ═══════════════════════════════════════════════════════════════════════
#  Report
# ═══════════════════════════════════════════════════════════════════════

def print_report():
    lines = []
    def emit(s: str = ""):
        lines.append(s)
        print(s)

    emit(f"\n{COL_BOLD}{COL_CYAN}{'='*90}{COL_RESET}")
    emit(f"{COL_BOLD}{COL_CYAN}  CROSS-PROVIDER DISCREPANCY TEST REPORT{COL_RESET}")
    emit(f"{COL_BOLD}{COL_CYAN}  Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}{COL_RESET}")
    emit(f"{COL_BOLD}{COL_CYAN}{'='*90}{COL_RESET}\n")

    # ── Environment ──────────────────────────────────────────────────
    emit(f"{COL_BOLD}TEST ENVIRONMENT:{COL_RESET}")
    emit(f"  Tickers: {', '.join(TICKERS)}")
    emit(f"  Providers: {', '.join(c['name'] for c in PROVIDERS_CONFIG)}")
    emit(f"  Timeout: {PROVIDER_TIMEOUT}s per call")
    for cfg in PROVIDERS_CONFIG:
        pname = cfg["name"]
        ok, reason = _provider_available(pname)
        s = f"{COL_GREEN}AVAILABLE{COL_RESET}" if ok else f"{COL_RED}{reason}{COL_RESET}"
        emit(f"  {pname:18s} {s}")
    emit()

    # ── Price table ──────────────────────────────────────────────────
    emit(f"{COL_BOLD}PRICE COMPARISON TABLE:{COL_RESET}")
    emit(build_price_table())
    emit()

    # ── Side-by-side ─────────────────────────────────────────────────
    emit(f"{COL_BOLD}SIDE-BY-SIDE PRICE SUMMARY:{COL_RESET}")
    for ticker in TICKERS:
        parts = [f"{ticker:10s}:"]
        for cfg in PROVIDERS_CONFIG:
            r = results[ticker].get(cfg["name"], {})
            if "error" not in r and r.get("price") is not None:
                parts.append(f"{cfg['name']}=${float(r['price']):.2f}")
            else:
                parts.append(f"{cfg['name']}=ERR")
        emit("  " + " | ".join(parts))

    # Price ranges
    emit(f"\n{COL_BOLD}PRICE RANGES:{COL_RESET}")
    for ticker in TICKERS:
        prices = []
        for cfg in PROVIDERS_CONFIG:
            r = results[ticker].get(cfg["name"], {})
            if "error" not in r and r.get("price") is not None:
                prices.append(float(r["price"]))
        if len(prices) >= 2:
            emit(f"  {ticker:10s}: min=${min(prices):.2f}  max=${max(prices):.2f}  "
                 f"spread=${max(prices)-min(prices):.2f}  "
                 f"mean=${mean(prices):.2f}")
    emit()

    # ── Outliers ─────────────────────────────────────────────────────
    emit(f"{COL_BOLD}{COL_YELLOW}OUTLIER DETECTION (|z| > 2.0):{COL_RESET}")
    outliers = detect_outliers()
    if outliers:
        for o in outliers:
            emit(f"  {COL_RED}[OUTLIER] {o['ticker']}/{o['provider']}: "
                 f"${o['value']:.2f} vs mean=${o['mean']:.2f} "
                 f"(z={o['z_score']:.1f}, dev={o['pct_dev']:+.2f}%){COL_RESET}")
    else:
        emit(f"  {COL_GREEN}No outliers detected (all values within 2-sigma).{COL_RESET}")
    emit()

    # ── Volume ───────────────────────────────────────────────────────
    emit(f"{COL_BOLD}VOLUME CONSISTENCY (>20% deviation from median):{COL_RESET}")
    vd = check_volume()
    if vd:
        for v in vd:
            emit(f"  {COL_RED}[VOLUME] {v['ticker']}/{v['provider']}: "
                 f"vol={v['volume']:,} vs median={v['median_volume']:,} "
                 f"({v['deviation_pct']:+.1f}%){COL_RESET}")
    else:
        emit(f"  {COL_GREEN}All volumes within 20% of median.{COL_RESET}")
    emit()

    # ── Historical close ─────────────────────────────────────────────
    emit(f"{COL_BOLD}HISTORICAL CLOSE (~15 trading days ago):{COL_RESET}")
    hd = compare_historical_close(15)
    if hd:
        for h in hd:
            emit(f"  {COL_RED}[HIST] {h['ticker']}/{h['provider']}: "
                 f"close={h['close']:.2f} on {h['date']} "
                 f"(avg={h['avg_close']:.2f}, diff={h['pct_diff']:+.2f}%){COL_RESET}")
    else:
        emit(f"  {COL_GREEN}Historical close consistent across providers.{COL_RESET}")

    # Raw candle summary
    emit(f"\n{COL_BOLD}CANDLE DATA SUMMARY:{COL_RESET}")
    for ticker in TICKERS:
        emit(f"  {ticker}:")
        for cfg in PROVIDERS_CONFIG:
            pname = cfg["name"]
            if not cfg["candles"]:
                emit(f"    {pname:16s}: N/A")
                continue
            cr = candle_results.get(ticker, {}).get(pname, {})
            if "error" in cr:
                emit(f"    {pname:16s}: ERR - {str(cr['error'])[:55]}")
                continue
            cdl = cr.get("candles", [])
            if not isinstance(cdl, list) or not cdl:
                emit(f"    {pname:16s}: no candles")
                continue
            try:
                f = str(cdl[0].get("datetime", cdl[0].get("time", "?")))[:10]
                l = str(cdl[-1].get("datetime", cdl[-1].get("time", "?")))[:10]
                lc = cdl[-1].get("close", "?")
                emit(f"    {pname:16s}: {len(cdl)} candles, {f}..{l}, close={lc}")
            except Exception:
                emit(f"    {pname:16s}: {len(cdl)} candles")
    emit()

    # ── Reliability ranking ──────────────────────────────────────────
    emit(f"{COL_BOLD}PROVIDER RELIABILITY RANKING:{COL_RESET}")
    ranking = rank_providers()
    emit(f"  {'Rank':>4s} {'Provider':18s} {'Success':>8s} {'Consistency':>12s} {'Coverage':>9s} {'Score':>7s}")
    emit(f"  {'-'*4} {'-'*18} {'-'*8} {'-'*12} {'-'*9} {'-'*7}")
    for rk, (pname, s) in enumerate(ranking, 1):
        emit(f"  {rk:>4d} {pname:18s} {s['success_rate']:>7.0%} {s['consistency_score']:>11.0%} "
             f"{s['coverage']:>8.0%} {s['score']:>7.1f}")
    emit()

    # ── Ticker-type recommendations ──────────────────────────────────
    emit(f"{COL_BOLD}BEST PROVIDER PER TICKER TYPE:{COL_RESET}")
    assessment = assess_by_type()
    for ticker, info in assessment.items():
        emit(f"  {ticker:10s} ({info['type']:12s}): best={info['best_provider'] or 'N/A'}")
        for d in info["details"]:
            emit(f"             {d['provider']:16s} ${d['price']:<8.2f}  "
                 f"(consensus=${d['consensus']}, {d['pct_from_consensus']:+.2f}%)")
    emit()

    # ── Final recommendations ────────────────────────────────────────
    emit(f"{COL_BOLD}FINDINGS:{COL_RESET}")
    if ranking:
        best = ranking[0]
        emit(f"  1. Most reliable provider: {best[0]} (score={best[1]['score']})")
    if outliers:
        emit(f"  2. {COL_RED}{len(outliers)} outlier(s){COL_RESET} detected — investigate:")
        for o in outliers:
            emit(f"     - {o['ticker']}: {o['provider']} ${o['value']:.2f} vs consensus ${o['mean']:.2f}")

    # PETR4.SA analysis
    emit(f"  3. PETR4.SA (Brazilian BDR):")
    for cfg in PROVIDERS_CONFIG:
        r = results.get("PETR4.SA", {}).get(cfg["name"], {})
        if "error" not in r and r.get("price") is not None:
            emit(f"     - {cfg['name']:16s}: OK  ${float(r['price']):.2f}")
        else:
            emit(f"     - {cfg['name']:16s}: FAIL ({r.get('error','N/A')[:40]})")

    # SNDL analysis
    emit(f"  4. SNDL (penny stock):")
    ok_list = []
    for cfg in PROVIDERS_CONFIG:
        r = results.get("SNDL", {}).get(cfg["name"], {})
        if "error" not in r and r.get("price") is not None:
            ok_list.append(f"{cfg['name']} (${float(r['price']):.2f})")
    if ok_list:
        emit(f"     Working providers: {', '.join(ok_list)}")
    else:
        emit(f"     {COL_RED}No provider returned SNDL price{COL_RESET}")

    # Summary of which provider works for which ticker type
    emit(f"  5. Coverage by ticker type:")
    emit(f"     Large cap (AAPL):  {sum(1 for c in PROVIDERS_CONFIG if 'error' not in results.get('AAPL',{}).get(c['name'],{}))}/{len(PROVIDERS_CONFIG)} providers")
    emit(f"     Tech (MSFT):       {sum(1 for c in PROVIDERS_CONFIG if 'error' not in results.get('MSFT',{}).get(c['name'],{}))}/{len(PROVIDERS_CONFIG)} providers")
    emit(f"     Penny (SNDL):      {sum(1 for c in PROVIDERS_CONFIG if 'error' not in results.get('SNDL',{}).get(c['name'],{}))}/{len(PROVIDERS_CONFIG)} providers")
    emit(f"     ADR (VALE):        {sum(1 for c in PROVIDERS_CONFIG if 'error' not in results.get('VALE',{}).get(c['name'],{}))}/{len(PROVIDERS_CONFIG)} providers")
    emit(f"     BDR (PETR4.SA):    {sum(1 for c in PROVIDERS_CONFIG if 'error' not in results.get('PETR4.SA',{}).get(c['name'],{}))}/{len(PROVIDERS_CONFIG)} providers")

    emit(f"\n{COL_BOLD}{COL_CYAN}{'='*90}{COL_RESET}")
    emit(f"{COL_BOLD}{COL_CYAN}  END OF REPORT{COL_RESET}")
    emit(f"{COL_BOLD}{COL_CYAN}{'='*90}{COL_RESET}")


# ═══════════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════════

def main() -> int:
    print(f"{COL_BOLD}{COL_CYAN}SuperEzio Cross-Provider Discrepancy Test{COL_RESET}")
    print(f"{COL_CYAN}Purpose: Detect price discrepancies between data providers{COL_RESET}")
    print(f"{COL_CYAN}Date:    {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}{COL_RESET}")

    run_all_price_tests()
    run_all_candle_tests()

    print(f"\n{COL_BOLD}{COL_CYAN}PHASE 3: REPORT{COL_RESET}")
    print_report()
    return 0


if __name__ == "__main__":
    sys.exit(main())
