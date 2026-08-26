#!/usr/bin/env python3
"""
Cross-Provider Discrepancy Test — SuperEzio F51

Tests 5 tickers against available price providers:
  TwelveData, AlphaVantage, yfinance, Stooq

Finds DISCREPANCIES between providers.
"""

from __future__ import annotations

import concurrent.futures
import math
import os
import sys
import time
from datetime import UTC, datetime
from typing import Any

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

TICKERS = ["AAPL", "MSFT", "SNDL", "VALE", "PETR4.SA"]

PROVIDERS_CONFIG = [
    {"name": "twelve_data", "candles": True, "key": "TWELVE_DATA_API_KEY"},
    {"name": "alpha_vantage", "candles": True, "key": "ALPHA_VANTAGE_API_KEY"},
    {"name": "yfinance", "candles": True, "key": None},
    {"name": "stooq", "candles": False, "key": None},
]
PROVIDER_TIMEOUT = 30

R = "\033[0m"
G = "\033[92m"
Y = "\033[93m"
C = "\033[96m"
B = "\033[1m"
RED = "\033[91m"

results: dict[str, dict[str, Any]] = {}
candle_results: dict[str, dict[str, Any]] = {}


def price_str(n, r):
    return f"{float(r['price']):.2f}"


def _load_env(path: str) -> None:
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip("\"'").strip())
    except FileNotFoundError:
        pass


_load_env(os.path.join(PROJECT_ROOT, ".env.local"))
_load_env(os.path.join(PROJECT_ROOT, ".env"))


def provider_ok(pname: str) -> tuple[bool, str]:
    cfg = next((p for p in PROVIDERS_CONFIG if p["name"] == pname), None)
    if not cfg:
        return False, "unknown"
    if cfg["key"] and not os.getenv(cfg["key"]):
        return False, f"no_{cfg['key']}"
    if pname == "yfinance":
        try:
            import yfinance  # noqa
        except ImportError:
            return False, "yfinance_not_installed"
    return True, "ok"


def _get_provider(pname: str):
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
        elif pname == "stooq":
            from src.data.stooq_provider import StooqProvider

            return StooqProvider()
    except Exception:
        return None


def _price(pname: str, prov, sym: str) -> dict:
    try:
        if pname == "alpha_vantage":
            return prov.get_quote(sym)
        elif pname == "twelve_data":
            return prov.get_price(sym)
        elif pname == "yfinance" or pname == "stooq":
            return prov.get_price(sym, market="US")
    except Exception as e:
        return {"error": f"exc:{e}"}


def _candles(pname: str, prov, sym: str, tf="1M") -> dict:
    try:
        if pname == "twelve_data":
            return prov.get_candles(sym, timeframe=tf)
        elif pname == "alpha_vantage":
            return prov.get_ohlcv(sym, timeframe=tf)
        elif pname == "yfinance":
            return prov.get_candles(sym, timeframe=tf, market="US")
        elif pname == "stooq":
            return {"error": "no_candles"}
    except Exception as e:
        return {"error": f"exc:{e}"}


def mean(v):
    return sum(v) / len(v) if v else 0.0


def std(v, a=None):
    if len(v) < 2:
        return 0.0
    a = a or mean(v)
    return math.sqrt(sum((x - a) ** 2 for x in v) / len(v))


def zs(v, a, sd):
    return (v - a) / sd if sd else 0.0


def run_prices():
    print(f"\n{B}{C}PHASE 1: PRICES{R}")
    for ticker in TICKERS:
        results[ticker] = {}
        print(f"{B}-- {ticker} --{R}")
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            futures = {}
            for cfg in PROVIDERS_CONFIG:
                pn = cfg["name"]
                ok, why = provider_ok(pn)
                if not ok:
                    results[ticker][pn] = {"error": why}
                    print(f"  {Y}[SKIP] {pn:16s}: {why}{R}")
                    continue
                prov = _get_provider(pn)
                if not prov:
                    results[ticker][pn] = {"error": "inst_fail"}
                    print(f"  {Y}[SKIP] {pn:16s}: inst_fail{R}")
                    continue
                futures[pn] = pool.submit(_price, pn, prov, ticker)
            for pn, fut in futures.items():
                try:
                    r = fut.result(timeout=PROVIDER_TIMEOUT)
                except concurrent.futures.TimeoutError:
                    r = {"error": "timeout"}
                except Exception as e:
                    r = {"error": f"exec:{e}"}
                results[ticker][pn] = r
                if "error" in r:
                    print(f"  {RED}[ERR]  {pn:16s}: {str(r['error'])[:60]}{R}")
                else:
                    print(f"  {G}[OK]   {pn:16s}: price={r.get('price')} vol={r.get('volume')}{R}")
        time.sleep(0.3)


def run_candles():
    print(f"\n{B}{C}PHASE 2: CANDLES (1M){R}")
    for ticker in TICKERS:
        candle_results[ticker] = {}
        print(f"  {ticker}...", end=" ", flush=True)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            futures = {}
            for cfg in PROVIDERS_CONFIG:
                pn = cfg["name"]
                if not cfg["candles"]:
                    candle_results[ticker][pn] = {"error": "no_endpoint"}
                    continue
                ok, why = provider_ok(pn)
                if not ok:
                    candle_results[ticker][pn] = {"error": why}
                    continue
                prov = _get_provider(pn)
                if not prov:
                    candle_results[ticker][pn] = {"error": "inst_fail"}
                    continue
                futures[pn] = pool.submit(_candles, pn, prov, ticker, "1M")
            for pn, fut in futures.items():
                try:
                    r = fut.result(timeout=PROVIDER_TIMEOUT)
                except concurrent.futures.TimeoutError:
                    r = {"error": "timeout"}
                except Exception as e:
                    r = {"error": f"exec:{e}"}
                candle_results[ticker][pn] = r
        print("done")


def price_table() -> str:
    lines = [f"{'TICKER':12s} {'Provider':16s} {'Price':>10s} {'Volume':>12s}"]
    lines.append("-" * 50)
    for t in TICKERS:
        for c in PROVIDERS_CONFIG:
            pn = c["name"]
            r = results[t].get(pn, {})
            if "error" in r:
                lines.append(f"{t:12s} {pn:16s} {'---':>10s} {'---':>12s}")
            else:
                pv = r.get("price")
                ps = f"{pv:.2f}" if pv else "N/A"
                vv = r.get("volume")
                vs = f"{vv:,}" if vv else "N/A"
                lines.append(f"{t:12s} {pn:16s} {ps:>10s} {vs:>12s}")
    return "\n".join(lines)


def side_by_side() -> str:
    lines = []
    for t in TICKERS:
        parts = [f"{t:10s}:"]
        for c in PROVIDERS_CONFIG:
            r = results[t].get(c["name"], {})
            if "error" not in r and r.get("price"):
                parts.append(f"{c['name']}=${float(r['price']):.2f}")
            else:
                parts.append(f"{c['name']}=ERR")
        lines.append("  " + " | ".join(parts))
    return "\n".join(lines)


def outliers() -> list[dict]:
    out = []
    for t in TICKERS:
        prs = [
            (c["name"], float(results[t][c["name"]]["price"]))
            for c in PROVIDERS_CONFIG
            if "error" not in results[t].get(c["name"], {}) and results[t][c["name"]].get("price")
        ]
        if len(prs) < 3:
            continue
        vals = [p[1] for p in prs]
        avg = mean(vals)
        sd = std(vals, avg)
        if sd < avg * 0.001:
            continue
        for pn, pv in prs:
            z = zs(pv, avg, sd)
            if abs(z) > 2.0:
                out.append(
                    {
                        "ticker": t,
                        "provider": pn,
                        "value": pv,
                        "mean": round(avg, 2),
                        "z": round(z, 2),
                        "dev": round((pv - avg) / avg * 100, 2),
                    }
                )
    return out


def vol_issues() -> list[dict]:
    issues = []
    for t in TICKERS:
        vols = [
            (c["name"], int(results[t][c["name"]]["volume"]))
            for c in PROVIDERS_CONFIG
            if "error" not in results[t].get(c["name"], {}) and results[t][c["name"]].get("volume")
        ]
        if len(vols) < 2:
            continue
        sv = sorted(v[1] for v in vols)
        mid = len(sv) // 2
        med = sv[mid] if len(sv) % 2 else (sv[mid - 1] + sv[mid]) / 2
        for pn, v in vols:
            if med == 0:
                continue
            d = abs(v - med) / med * 100
            if d > 20:
                issues.append(
                    {
                        "ticker": t,
                        "provider": pn,
                        "volume": v,
                        "median": int(med),
                        "dev": round(d, 1),
                    }
                )
    return issues


def hist_close(days=15) -> list[dict]:
    issues = []
    for t in TICKERS:
        closes = []
        for c in PROVIDERS_CONFIG:
            pn = c["name"]
            if not c["candles"]:
                continue
            cr = candle_results.get(t, {}).get(pn, {})
            if "error" in cr:
                continue
            cdl = cr.get("candles", [])
            if not isinstance(cdl, list) or len(cdl) < days + 1:
                continue
            try:
                fd = str(cdl[0].get("datetime", cdl[0].get("time", "")))
                ld = str(cdl[-1].get("datetime", cdl[-1].get("time", "")))
                old = fd < ld
            except:
                old = True
            idx = max(0, len(cdl) - days - 1) if old else min(len(cdl) - 1, days)
            cv = float(cdl[idx].get("close", 0))
            dt = str(cdl[idx].get("datetime", cdl[idx].get("time", "?")))[:10]
            if cv > 0:
                closes.append((pn, cv, dt))
        if len(closes) < 2:
            continue
        vals = [c[1] for c in closes]
        avg = mean(vals)
        for pn, cv, dt in closes:
            if avg > 0:
                pd = abs(cv - avg) / avg * 100
                if pd > 2.0:
                    issues.append(
                        {
                            "ticker": t,
                            "provider": pn,
                            "close": cv,
                            "date": dt,
                            "avg": round(avg, 2),
                            "diff": round(pd, 2),
                        }
                    )
    return issues


def ranking() -> list[tuple]:
    stats = {}
    for c in PROVIDERS_CONFIG:
        pn = c["name"]
        stats[pn] = {"att": 0, "ok": 0, "prices": [], "score": 0}
    for t in TICKERS:
        for c in PROVIDERS_CONFIG:
            pn = c["name"]
            stats[pn]["att"] += 1
            r = results[t].get(pn, {})
            if "error" not in r and r.get("price"):
                stats[pn]["ok"] += 1
                stats[pn]["prices"].append(float(r["price"]))
    for pn, s in stats.items():
        sr = s["ok"] / s["att"] if s["att"] else 0
        if len(s["prices"]) >= 3:
            ap = mean(s["prices"])
            sdv = std(s["prices"], ap)
            cv = sdv / ap if ap > 0 else 1.0
            cs = max(0, 1.0 - min(cv * 10, 1.0))
        else:
            cs = 0.5
        cov = s["ok"] / s["att"] if s["att"] else 0
        s["sr"] = round(sr, 2)
        s["cs"] = round(cs, 2)
        s["cov"] = round(cov, 2)
        s["score"] = round(sr * 50 + cs * 30 + cov * 20, 1)
    return sorted(stats.items(), key=lambda x: x[1]["score"], reverse=True)


def by_type() -> dict:
    tt = {"AAPL": "large_cap", "MSFT": "tech", "SNDL": "penny", "VALE": "ADR", "PETR4.SA": "BDR"}
    a = {}
    for t, tp in tt.items():
        prs = []
        for c in PROVIDERS_CONFIG:
            r = results[t].get(c["name"], {})
            if "error" not in r and r.get("price"):
                prs.append({"p": c["name"], "v": float(r["price"])})
        if prs:
            vals = [p["v"] for p in prs]
            con = mean(vals)
            for p in prs:
                p["con"] = round(con, 2)
                p["pct"] = round((p["v"] - con) / con * 100, 2)
            prs.sort(key=lambda x: abs(x["pct"]))
            best = prs[0]["p"] if prs else None
        else:
            best = None
        a[t] = {"type": tp, "best": best, "details": prs}
    return a


def candle_summary() -> str:
    lines = []
    for t in TICKERS:
        lines.append(f"  {t}:")
        for c in PROVIDERS_CONFIG:
            pn = c["name"]
            if not c["candles"]:
                lines.append(f"    {pn:16s}: N/A")
                continue
            cr = candle_results.get(t, {}).get(pn, {})
            if "error" in cr:
                lines.append(f"    {pn:16s}: ERR - {str(cr['error'])[:50]}")
                continue
            cdl = cr.get("candles", [])
            if not isinstance(cdl, list) or not cdl:
                lines.append(f"    {pn:16s}: no candles")
                continue
            try:
                f = str(cdl[0].get("datetime", cdl[0].get("time", "?")))[:10]
                l = str(cdl[-1].get("datetime", cdl[-1].get("time", "?")))[:10]
                lc = cdl[-1].get("close", "?")
                lines.append(f"    {pn:16s}: {len(cdl)} candles, {f}..{l}, close={lc}")
            except:
                lines.append(f"    {pn:16s}: {len(cdl)} candles")
    return "\n".join(lines)


def report():
    print(f"\n{B}{C}{'=' * 90}{R}")
    print(f"{B}{C}  CROSS-PROVIDER DISCREPANCY TEST REPORT{R}")
    print(f"{B}{C}  {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}{R}")
    print(f"{B}{C}{'=' * 90}{R}\n")

    print(f"{B}ENVIRONMENT:{R}")
    for c in PROVIDERS_CONFIG:
        ok, why = provider_ok(c["name"])
        s = f"{G}OK{R}" if ok else f"{RED}{why}{R}"
        print(f"  {c['name']:16s} {s}")
    print()

    print(f"{B}PRICE TABLE:{R}")
    print(price_table())
    print()

    print(f"{B}SIDE-BY-SIDE:{R}")
    print(side_by_side())
    print()

    # Price ranges
    print(f"{B}PRICE RANGES:{R}")
    for t in TICKERS:
        prs = [
            float(results[t][c["name"]]["price"])
            for c in PROVIDERS_CONFIG
            if "error" not in results[t].get(c["name"], {}) and results[t][c["name"]].get("price")
        ]
        if len(prs) >= 2:
            print(
                f"  {t:10s}: min=${min(prs):.2f} max=${max(prs):.2f} spread=${max(prs) - min(prs):.2f} mean=${mean(prs):.2f}"
            )
    print()

    # Outliers
    print(f"{B}{Y}OUTLIERS (|z|>2.0):{R}")
    o = outliers()
    if o:
        for x in o:
            print(
                f"  {RED}[OUTLIER] {x['ticker']}/{x['provider']}: ${x['value']:.2f} vs ${x['mean']:.2f} (z={x['z']:.1f}, dev={x['dev']:+.2f}%){R}"
            )
    else:
        print(f"  {G}None detected{R}")
    print()

    # Volume
    print(f"{B}VOLUME CONSISTENCY:{R}")
    vi = vol_issues()
    if vi:
        for x in vi:
            print(
                f"  {RED}[VOL] {x['ticker']}/{x['provider']}: {x['volume']:,} vs median {x['median']:,} ({x['dev']:+.1f}%){R}"
            )
    else:
        print(f"  {G}All consistent{R}")
    print()

    # Historical
    print(f"{B}HISTORICAL CLOSE (~15d ago):{R}")
    h = hist_close(15)
    if h:
        for x in h:
            print(
                f"  {RED}[HIST] {x['ticker']}/{x['provider']}: close={x['close']:.2f} on {x['date']} vs avg={x['avg']:.2f} ({x['diff']:+.2f}%){R}"
            )
    else:
        print(f"  {G}All consistent{R}")
    print()

    # Candle summary
    print(f"{B}CANDLE DATA:{R}")
    print(candle_summary())
    print()

    # Ranking
    print(f"{B}RANKING:{R}")
    rk = ranking()
    print(
        f"  {'Rank':>4s} {'Provider':16s} {'Success':>8s} {'Consistency':>12s} {'Coverage':>9s} {'Score':>7s}"
    )
    print(f"  {'-' * 4} {'-' * 16} {'-' * 8} {'-' * 12} {'-' * 9} {'-' * 7}")
    for i, (pn, s) in enumerate(rk, 1):
        print(
            f"  {i:>4d} {pn:16s} {s['sr']:>7.0%} {s['cs']:>11.0%} {s['cov']:>8.0%} {s['score']:>7.1f}"
        )
    print()

    # Best per type
    print(f"{B}BEST PER TICKER TYPE:{R}")
    bt = by_type()
    for t, info in bt.items():
        print(f"  {t:10s} ({info['type']:12s}): best={info['best'] or 'N/A'}")
        for d in info["details"]:
            print(
                f"             {d['p']:16s} ${d['v']:<8.2f}  (consensus=${d['con']}, {d['pct']:+.2f}%)"
            )
    print()

    # Findings
    print(f"{B}FINDINGS:{R}")
    if rk:
        print(f"  1. Most reliable provider: {rk[0][0]} (score={rk[0][1]['score']})")
    if o:
        print(f"  2. {RED}{len(o)} outlier(s){R} detected")
    print("  3. PETR4.SA (BDR):")
    for c in PROVIDERS_CONFIG:
        rr = results.get("PETR4.SA", {}).get(c["name"], {})
        if "error" not in rr and rr.get("price"):
            print(f"     - {c['name']:16s}: OK  ${float(rr['price']):.2f}")
        else:
            print(f"     - {c['name']:16s}: FAIL ({rr.get('error', 'N/A')[:40]})")
    print("  4. SNDL (penny):")
    oks = [(c["name"], results.get("SNDL", {}).get(c["name"], {})) for c in PROVIDERS_CONFIG]
    oks = [(n, r) for n, r in oks if "error" not in r and r.get("price")]
    if oks:
        print(f"     Working: {', '.join(f'{n} (${price_str(n, r)})' for n, r in oks)}")
    else:
        print(f"     {RED}No provider returned price{R}")
    print("  5. Coverage:")
    for t in TICKERS:
        n_ok = sum(
            1 for c in PROVIDERS_CONFIG if "error" not in results.get(t, {}).get(c["name"], {})
        )
        print(f"     {t:12s}: {n_ok}/{len(PROVIDERS_CONFIG)} providers")

    print(f"\n{B}{C}{'=' * 90}{R}")
    print(f"{B}{C}  END{R}")
    print(f"{B}{C}{'=' * 90}{R}")


def main():
    print(f"{B}{C}SuperEzio Cross-Provider Discrepancy Test{R}")
    print(f"{C}Tickers: {', '.join(TICKERS)}{R}")
    print(f"{C}Providers: {', '.join(c['name'] for c in PROVIDERS_CONFIG)}{R}")
    run_prices()
    run_candles()
    report()
    return 0


if __name__ == "__main__":
    sys.exit(main())
