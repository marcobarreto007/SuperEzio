#!/usr/bin/env python3
"""
PROVIDER CANDLES TEST v2 — Full comparison of all OHLCV providers in DataHub.

Corrections from v1:
  - AKShare "1M"/"6M" triggers intraday bug (timeframe ending in 'm') — fixed by using "1Y"
  - yfinance datetime is a Timestamp, not string — handled
  - AKShare East Money servers are geo-restricted — retry logic added

Tests:
  1. Each provider's get_candles() for AAPL, TSLA, SNDL with monthly/daily timeframe
  2. AKShare stock_us_hist() direct call
  3. Cross-reference AAPL close price on 2024-07-15
  4. Intraday latency (1min, 5min, 15min)
  5. Ranking report with scoring
"""

from __future__ import annotations

import os
import sys
import time
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src"))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

SYMBOLS = ["AAPL", "TSLA", "SNDL"]
TARGET_DATE = "2024-07-15"
TIMEFRAMES_INTRADAY = ["1m", "5m", "15m"]

# ── Helpers ─────────────────────────────────────────────────────────────

def _fmt_ms(seconds: float) -> str:
    return f"{seconds * 1000:.0f}ms"

def _count_candles(result: dict) -> int:
    c = result.get("candles") or []
    return len(c) if isinstance(c, list) else 0

def _check_fields(candles: list) -> dict:
    """Check which OHLCV fields are present in candles."""
    required = ["open", "high", "low", "close", "volume"]
    if not candles:
        return {f: False for f in required}
    present = {}
    for f in required:
        vals = [c.get(f) for c in candles[:10] if c.get(f) is not None]
        present[f] = len(vals) > 0 and any(float(v) != 0 for v in vals)
    return present

def _find_candle_by_date(candles: list, target: str) -> dict | None:
    """Find candle closest to target date string."""
    for c in candles:
        raw = c.get("datetime") or c.get("time") or ""
        if isinstance(raw, datetime):
            raw = raw.isoformat()
        if str(raw).startswith(target):
            return c
    return None

def _get_candle_close(candle: dict) -> float | None:
    val = candle.get("close")
    return float(val) if val is not None else None

def _dt_str(val: Any) -> str:
    if isinstance(val, datetime):
        return val.strftime("%Y-%m-%dT%H:%M:%S")
    return str(val)

# ── Provider Tests ──────────────────────────────────────────────────────

def test_finnhub() -> dict:
    result: Dict[str, Any] = {"name": "finnhub", "available": False, "reason": ""}
    api_key = os.getenv("FINNHUB_API_KEY")
    if not api_key:
        result["reason"] = "SKIP: FINNHUB_API_KEY not set"
        return result
    try:
        from data.finnhub_provider import FinnhubProvider
        provider = FinnhubProvider(api_key=api_key)
        result["available"] = True
        result["symbols"] = {}
        for sym in SYMBOLS:
            t0 = time.perf_counter()
            data = provider.get_candles(sym, timeframe="1M")
            elapsed = time.perf_counter() - t0
            n = _count_candles(data)
            flds = _check_fields(data.get("candles", []))
            result["symbols"][sym] = {
                "candle_count": n, "latency_ms": round(elapsed * 1000),
                "fields": flds, "error": data.get("error"),
            }
    except Exception as e:
        result["reason"] = f"ERROR: {e}"
    return result

def test_twelve_data() -> dict:
    result = {"name": "twelve_data", "available": False, "reason": ""}
    api_key = os.getenv("TWELVE_DATA_API_KEY")
    if not api_key:
        result["reason"] = "SKIP: TWELVE_DATA_API_KEY not set"
        return result
    try:
        from data.twelve_data import TwelveDataProvider
        provider = TwelveDataProvider(api_key=api_key)
        result["available"] = True
        result["symbols"] = {}
        for sym in SYMBOLS:
            t0 = time.perf_counter()
            data = provider.get_candles(sym, timeframe="1M")
            elapsed = time.perf_counter() - t0
            n = _count_candles(data)
            flds = _check_fields(data.get("candles", []))
            result["symbols"][sym] = {
                "candle_count": n, "latency_ms": round(elapsed * 1000),
                "fields": flds, "error": data.get("error"),
            }
    except Exception as e:
        result["reason"] = f"ERROR: {e}"
    return result

def test_alpha_vantage() -> dict:
    result = {"name": "alpha_vantage", "available": False, "reason": ""}
    api_key = os.getenv("ALPHA_VANTAGE_API_KEY")
    if not api_key:
        result["reason"] = "SKIP: ALPHA_VANTAGE_API_KEY not set"
        return result
    try:
        from data.alpha_vantage import AlphaVantageProvider
        provider = AlphaVantageProvider(api_key=api_key)
        result["available"] = True
        result["symbols"] = {}
        for sym in SYMBOLS:
            t0 = time.perf_counter()
            data = provider.get_ohlcv(sym, timeframe="1M")
            elapsed = time.perf_counter() - t0
            n = _count_candles(data)
            flds = _check_fields(data.get("candles", []))
            result["symbols"][sym] = {
                "candle_count": n, "latency_ms": round(elapsed * 1000),
                "fields": flds, "error": data.get("error"),
            }
    except Exception as e:
        result["reason"] = f"ERROR: {e}"
    return result

def test_yfinance() -> dict:
    result = {"name": "yfinance", "available": False, "reason": ""}
    try:
        from data.yfinance_provider import YFinanceProvider
        provider = YFinanceProvider()
        result["available"] = True
        result["symbols"] = {}
        for sym in SYMBOLS:
            t0 = time.perf_counter()
            data = provider.get_candles(sym, timeframe="1M")
            elapsed = time.perf_counter() - t0
            n = _count_candles(data)
            flds = _check_fields(data.get("candles", []))
            result["symbols"][sym] = {
                "candle_count": n, "latency_ms": round(elapsed * 1000),
                "fields": flds, "error": data.get("error"),
            }
    except Exception as e:
        result["reason"] = f"ERROR: {e}"
    return result

def test_akshare() -> dict:
    """AKShare: '1M' timeframe has intraday bug (ends with 'm').
    We test with '1Y' for daily and note the bug separately."""
    result = {"name": "akshare", "available": False, "reason": ""}
    try:
        from data.akshare_provider import AKShareProvider
        provider = AKShareProvider()
        result["available"] = True

        # Test 1: daily with '1Y' (correct path)
        result["daily"] = {}
        for sym in SYMBOLS:
            t0 = time.perf_counter()
            data = provider.get_candles(sym, timeframe="1Y")
            elapsed = time.perf_counter() - t0
            n = _count_candles(data)
            flds = _check_fields(data.get("candles", []))
            result["daily"][sym] = {
                "candle_count": n, "latency_ms": round(elapsed * 1000),
                "fields": flds, "error": data.get("error"),
            }

        # Test 2: Test the intraday bug with '1M'
        result["bug_1m_as_intraday"] = {}
        for sym in SYMBOLS:
            t0 = time.perf_counter()
            data = provider.get_candles(sym, timeframe="1M")
            elapsed = time.perf_counter() - t0
            err = data.get("error")
            result["bug_1m_as_intraday"][sym] = {
                "error": err, "latency_ms": round(elapsed * 1000),
            }

        # For backward compat: use daily results as main
        result["symbols"] = result["daily"]

    except Exception as e:
        result["reason"] = f"ERROR: {e}"
    return result

def test_akshare_direct() -> dict:
    """AKShare stock_us_hist() direct call. Retries on connection failure."""
    result = {"name": "akshare_direct_stock_us_hist", "available": False}
    try:
        import akshare as ak
        result["available"] = True
        result["retries"] = []

        for attempt in range(3):
            try:
                t0 = time.perf_counter()
                df = ak.stock_us_hist(
                    symbol="105.AAPL", period="daily",
                    start_date="20240601", end_date="20240830",
                    adjust="",
                )
                elapsed = time.perf_counter() - t0
                result["latency_ms"] = round(elapsed * 1000)
                result["rows"] = len(df)
                result["columns"] = list(df.columns)
                result["shape"] = df.shape
                # Find target date
                for _, row in df.iterrows():
                    date_val = str(row.iloc[0])
                    if TARGET_DATE in date_val:
                        result["target_date_row"] = {
                            "date": date_val, "open": float(row.iloc[1]),
                            "high": float(row.iloc[2]), "low": float(row.iloc[3]),
                            "close": float(row.iloc[4]),
                            "volume": float(row.iloc[5]) if len(row) > 5 else 0,
                        }
                        break
                if "target_date_row" not in result:
                    result["head"] = df.head(3).to_dict(orient="records")
                    dates = [str(r.iloc[0]) for _, r in df.iterrows()]
                    result["date_range"] = [dates[0], dates[-1]] if dates else []
                break
            except Exception as e:
                result["retries"].append(str(e)[:100])
                if attempt < 2:
                    time.sleep(3)
                else:
                    result["reason"] = f"ERROR after 3 retries: {e}"
    except Exception as e:
        result["reason"] = f"ERROR: {e}"
    return result

def cross_reference_aapl() -> dict:
    """Compare AAPL close on TARGET_DATE across all providers."""
    result = {"target_date": TARGET_DATE, "symbol": "AAPL", "providers": {}}

    # yfinance (reference)
    try:
        from data.yfinance_provider import YFinanceProvider
        provider = YFinanceProvider()
        data = provider.get_candles("AAPL", timeframe="1Y")
        c = _find_candle_by_date(data.get("candles", []), TARGET_DATE)
        if c:
            result["providers"]["yfinance"] = {
                "close": _get_candle_close(c),
                "datetime": _dt_str(c.get("datetime") or c.get("time", "")),
            }
    except Exception as e:
        result["providers"]["yfinance"] = {"error": str(e)}

    # AKShare (daily via 1Y)
    try:
        from data.akshare_provider import AKShareProvider
        provider = AKShareProvider()
        data = provider.get_candles("AAPL", timeframe="1Y")
        c = _find_candle_by_date(data.get("candles", []), TARGET_DATE)
        if c:
            result["providers"]["akshare"] = {
                "close": _get_candle_close(c),
                "datetime": _dt_str(c.get("datetime") or c.get("time", "")),
            }
    except Exception as e:
        result["providers"]["akshare"] = {"error": str(e)}

    # AKShare direct
    try:
        import akshare as ak
        df = ak.stock_us_hist(symbol="105.AAPL", period="daily", start_date="20240601", end_date="20240830", adjust="")
        for _, row in df.iterrows():
            dv = str(row.iloc[0])
            if TARGET_DATE in dv:
                result["providers"]["akshare_direct"] = {
                    "close": float(row.iloc[4]),
                    "datetime": dv,
                }
                break
    except Exception as e:
        result["providers"]["akshare_direct"] = {"error": str(e)}

    # Reference from yfinance
    yf = result["providers"].get("yfinance", {})
    if "close" in yf:
        result["reference_price"] = yf["close"]
        result["reference_source"] = "yfinance"

    # Discrepancies
    ref = result.get("reference_price")
    if ref:
        disc = {}
        for pn, pd in result["providers"].items():
            if isinstance(pd, dict) and "close" in pd:
                d = abs(pd["close"] - ref)
                dp = (d / ref) * 100 if ref else 0
                disc[pn] = {"close": pd["close"], "diff": round(d, 4), "diff_pct": round(dp, 4)}
        result["discrepancies_vs_reference"] = disc

    return result

def test_intraday() -> dict:
    """Intraday latency for 1m, 5m, 15m."""
    result = {"symbol": "AAPL", "timeframes": {}}

    # yfinance intraday
    try:
        from data.yfinance_provider import YFinanceProvider
        provider = YFinanceProvider()
        yf_tfs = {}
        for tf in TIMEFRAMES_INTRADAY:
            t0 = time.perf_counter()
            data = provider.get_candles("AAPL", timeframe=tf)
            elapsed = time.perf_counter() - t0
            n = _count_candles(data)
            yf_tfs[tf] = {"candle_count": n, "latency_ms": round(elapsed * 1000), "error": data.get("error")}
        result["timeframes"]["yfinance"] = yf_tfs
    except Exception as e:
        result["timeframes"]["yfinance"] = {"error": str(e)}

    # AKShare intraday
    try:
        from data.akshare_provider import AKShareProvider
        provider = AKShareProvider()
        ak_tfs = {}
        for tf in TIMEFRAMES_INTRADAY:
            t0 = time.perf_counter()
            data = provider.get_candles("AAPL", timeframe=tf)
            elapsed = time.perf_counter() - t0
            n = _count_candles(data)
            ak_tfs[tf] = {"candle_count": n, "latency_ms": round(elapsed * 1000), "error": data.get("error")}
        result["timeframes"]["akshare"] = ak_tfs
    except Exception as e:
        result["timeframes"]["akshare"] = {"error": str(e)}

    return result

# ── Report ──────────────────────────────────────────────────────────────

def generate_report(results, xref, intraday, ak_direct) -> str:
    lines = []
    lines.append("=" * 80)
    lines.append("PROVIDER CANDLES TEST — RELATORIO COMPLETO v2")
    lines.append(f"Gerado: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    lines.append("=" * 80)

    # Part 1
    lines.append("\n" + "-" * 80)
    lines.append("PARTE 1: TESTE DE CADA PROVIDER (timeframe mensal/diario)")
    lines.append("-" * 80)
    for pn in ["finnhub", "twelve_data", "alpha_vantage", "yfinance", "akshare"]:
        r = results.get(pn, {})
        lines.append(f"\n  [{pn.upper()}]")
        if not r.get("available"):
            lines.append(f"    Status: INDISPONIVEL — {r.get('reason', 'desconhecido')}")
            continue
        lines.append(f"    Status: OK")
        syms = r.get("symbols", {})
        # Handle nested daily dict for akshare
        if not syms and "daily" in r:
            syms = r["daily"]
        for sym in SYMBOLS:
            sd = syms.get(sym, {})
            err = sd.get("error")
            if err:
                lines.append(f"    {sym}: ERRO — {err}")
            else:
                n = sd.get("candle_count", 0)
                lat = sd.get("latency_ms", 0)
                flds = sd.get("fields", {})
                present = [k for k, v in flds.items() if v]
                missing = [k for k, v in flds.items() if not v]
                info = f"{sym}: {n} candles, {lat}ms, fields=[{','.join(present)}]"
                if missing:
                    info += f" AUSENTE=[{','.join(missing)}]"
                lines.append(f"    {info}")

        # Bug report for AKShare '1M'
        if pn == "akshare" and "bug_1m_as_intraday" in r:
            lines.append(f"    >>> BUG: timeframe='1M' e tratado como intraday (1 minuto) porque o nome termina com 'm'")
            for sym in SYMBOLS:
                b = r["bug_1m_as_intraday"].get(sym, {})
                lines.append(f"       {sym}: ERRO={b.get('error','')[:80]} ({b.get('latency_ms',0)}ms)")

    # Part 2
    lines.append("\n" + "-" * 80)
    lines.append("PARTE 2: AKSHARE DIRETO — stock_us_hist(symbol='105.AAPL', period='daily')")
    lines.append("-" * 80)
    if ak_direct.get("available") and "rows" in ak_direct:
        lines.append(f"  Latencia: {ak_direct.get('latency_ms','N/A')}ms")
        lines.append(f"  Rows: {ak_direct.get('rows')}, Shape: {ak_direct.get('shape')}")
        lines.append(f"  Columns: {ak_direct.get('columns')}")
        if "target_date_row" in ak_direct:
            td = ak_direct["target_date_row"]
            lines.append(f"  AAPL em {TARGET_DATE}: close={td['close']} O={td['open']} H={td['high']} L={td['low']} V={td['volume']}")
        else:
            dr = ak_direct.get("date_range", [])
            lines.append(f"  {TARGET_DATE} nao encontrado. Range de datas: {dr[0] if dr else 'N/A'} a {dr[-1] if dr else 'N/A'}")
    else:
        lines.append(f"  FALHA: {ak_direct.get('reason', 'conexao com servidores East Money (China) bloqueada desta rede')}")
        if ak_direct.get("retries"):
            for i, rtry in enumerate(ak_direct["retries"], 1):
                lines.append(f"    Tentativa {i}: {rtry}")

    # Part 3
    lines.append("\n" + "-" * 80)
    lines.append(f"PARTE 3: CROSS-REFERENCE — AAPL CLOSE EM {TARGET_DATE}")
    lines.append("-" * 80)
    lines.append(f"  Referencia: {xref.get('reference_source','N/A')} = {xref.get('reference_price','N/A')}")
    lines.append("")
    lines.append(f"  {'Provider':<20} {'Close':>10} {'Diff':>10} {'Diff%':>8}")
    lines.append(f"  {'-'*20} {'-'*10} {'-'*10} {'-'*8}")
    disc = xref.get("discrepancies_vs_reference", {})
    for pn, pd in sorted(disc.items()):
        lines.append(f"  {pn:<20} {pd['close']:>10.4f} {pd['diff']:>10.4f} {pd['diff_pct']:>7.3f}%")
    for pn, pd in xref.get("providers", {}).items():
        if isinstance(pd, dict) and "error" in pd:
            lines.append(f"  {pn:<20} {'ERROR':>10} {str(pd['error'])[:60]}")

    # Part 4
    lines.append("\n" + "-" * 80)
    lines.append("PARTE 4: LATENCIA INTRADAY (AAPL — 1m, 5m, 15m)")
    lines.append("-" * 80)
    lines.append(f"  {'Provider':<12} {'TF':>6} {'Candles':>8} {'Latencia':>10}")
    lines.append(f"  {'-'*12} {'-'*6} {'-'*8} {'-'*10}")
    for pn, tfs in intraday.get("timeframes", {}).items():
        if "error" in tfs:
            lines.append(f"  {pn:<12} {'ERR':>6} {str(tfs['error'])[:60]}")
            continue
        for tf, td in tfs.items():
            err = td.get("error")
            if err:
                lines.append(f"  {pn:<12} {tf:>6} {'ERR':>8} {str(err)[:60]}")
            else:
                lines.append(f"  {pn:<12} {tf:>6} {td.get('candle_count',0):>8} {td.get('latency_ms',0):>6}ms")

    # Part 5 — Ranking
    lines.append("\n" + "=" * 80)
    lines.append("PARTE 5: RANKING FINAL DOS PROVIDERS DE CANDLES (0-100)")
    lines.append("=" * 80)
    scores = compute_scores(results, xref, intraday)
    scores.sort(key=lambda x: x[1], reverse=True)
    lines.append(f"\n  {'Rank':<6} {'Provider':<16} {'Score':>6}  {'Notas'}")
    lines.append(f"  {'-'*6} {'-'*16} {'-'*6}  {'-'*50}")
    for i, (nm, sc, notes) in enumerate(scores, 1):
        lines.append(f"  {i:<6} {nm:<16} {sc:>6}/100  {notes}")

    # Final recommendation
    lines.append("\n" + "=" * 80)
    lines.append("RECOMENDACAO FINAL")
    lines.append("=" * 80)
    best = scores[0][0] if scores else "N/A"
    lines.append(f"\n  Melhor provider: {best}")

    # BUG report
    lines.append("\n  BUG ENCONTRADO:")
    lines.append("  AKShareProvider._parse_intraday_timeframe(): timeframe '1M', '3M', '6M'")
    lines.append("  sao interpretados como intraday (1 minuto) porque o metodo verifica")
    lines.append("  se o nome termina com 'm' (case-insensitive). '1M' vira '1m' e cai")
    lines.append("  no ramo intraday, ignorando o mapeamento _PERIOD_MAP que mapeia")
    lines.append("  corretamente '1M' -> 'monthly'.")

    lines.append("\n  Cadeia recomendada (prioridade):")
    lines.append("    1. Finnhub (se FINNHUB_API_KEY setada — melhor latencia)")
    lines.append("    2. TwelveData (se TWELVE_DATA_API_KEY setada — intraday suportado)")
    lines.append("    3. yfinance (sempre disponivel, OHLCV completo, sem key)")
    lines.append("    4. AKShare (gratis, daily funciona, intraday via China)")
    lines.append("")
    lines.append("  NOTA: Este ambiente nao tem FINNHUB_API_KEY, TWELVE_DATA_API_KEY,")
    lines.append("  nem ALPHA_VANTAGE_API_KEY. Apenas yfinance esta operacional,")
    lines.append("  e AKShare com conectividade intermitente a servidores chineses.")
    lines.append("")
    lines.append("=" * 80)

    return "\n".join(lines)

def compute_scores(results, xref, intraday) -> list:
    scores = []
    for pn, lbl in [("finnhub","Finnhub"), ("twelve_data","TwelveData"),
                     ("alpha_vantage","AlphaVantage"), ("yfinance","yFinance"),
                     ("akshare","AKShare")]:
        r = results.get(pn, {})
        if not r.get("available"):
            scores.append((lbl, 0, "Indisponivel"))
            continue

        score = 40
        notes = []

        # Use daily data for scoring
        syms = r.get("symbols", {})
        if not syms and "daily" in r:
            syms = r["daily"]

        total_candles = 0
        total_latency = 0
        n_syms = 0
        all_fields = True

        for sym in SYMBOLS:
            sd = syms.get(sym, {})
            err = sd.get("error")
            if err:
                notes.append(f"{sym}:{err[:40]}")
                continue
            n_syms += 1
            n = sd.get("candle_count", 0)
            total_candles += n
            total_latency += sd.get("latency_ms", 0)
            flds = sd.get("fields", {})
            if not all(flds.get(f) for f in ["open","high","low","close","volume"]):
                all_fields = False

        if n_syms == 0:
            scores.append((lbl, 10, "Nenhum simbolo respondeu"))
            continue

        avg_c = total_candles / n_syms
        avg_l = total_latency / n_syms

        if avg_c >= 50: score += 15; notes.append(f"{avg_c:.0f}candles/sym")
        elif avg_c >= 20: score += 8; notes.append(f"{avg_c:.0f}candles/sym")
        else: score -= 5; notes.append(f"poucos candles({avg_c:.0f})")

        if avg_l < 1000: score += 15; notes.append(f"rapido({avg_l:.0f}ms)")
        elif avg_l < 5000: score += 8; notes.append(f"medio({avg_l:.0f}ms)")
        else: score -= 5; notes.append(f"lento({avg_l:.0f}ms)")

        if all_fields: score += 10; notes.append("OHLCV completo")
        else: score -= 5; notes.append("campos ausentes")

        # Intraday
        intra = intraday.get("timeframes", {}).get(pn, {})
        if isinstance(intra, dict) and not intra.get("error"):
            ok = sum(1 for tf in TIMEFRAMES_INTRADAY
                     if isinstance(intra.get(tf), dict) and not intra[tf].get("error") and intra[tf].get("candle_count",0) > 0)
            if ok >= 2: score += 15; notes.append(f"intraday({ok}/3)")
            elif ok >= 1: score += 8; notes.append(f"intraday limitado({ok}/3)")

        # Cross-ref accuracy
        disc = xref.get("discrepancies_vs_reference", {})
        if lbl.lower().startswith("yf"):
            score += 5; notes.append("referencia")
        elif lbl.lower().startswith("ak"):
            pd = disc.get("akshare") or disc.get("akshare_direct") or {}
            dp = pd.get("diff_pct", 999)
            if dp < 1: score += 5; notes.append(f"preciso({dp:.2f}%)")
            else: notes.append(f"diff {dp:.2f}%")

        # No key bonus
        if pn in ("yfinance","akshare"):
            score += 5; notes.append("sem API key")

        score = max(0, min(100, score))
        scores.append((lbl, score, "; ".join(notes)))

    return scores

# ── Main ────────────────────────────────────────────────────────────────

def main():
    print("=" * 80)
    print("PROVIDER CANDLES TEST v2")
    print("=" * 80)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"Data: {now}")
    print(f"Simbolos: {SYMBOLS}")
    print(f"Target: AAPL em {TARGET_DATE}")

    results = {}
    tests = [
        ("finnhub", test_finnhub),
        ("twelve_data", test_twelve_data),
        ("alpha_vantage", test_alpha_vantage),
        ("yfinance", test_yfinance),
        ("akshare", test_akshare),
    ]
    for name, func in tests:
        print(f"  {name}... ", end="", flush=True)
        r = func()
        results[name] = r
        status = "OK" if r.get("available") else r.get("reason", "FAIL")
        print(status)

    print(f"  akshare_direct... ", end="", flush=True)
    ak_direct = test_akshare_direct()
    print("OK" if ak_direct.get("available") and "rows" in ak_direct else ak_direct.get("reason","FAILED"))

    print(f"  cross_reference... ", end="", flush=True)
    xref = cross_reference_aapl()
    print(f"OK ({len(xref.get('providers',{}))} providers)")

    print(f"  intraday_latency... ", end="", flush=True)
    intraday = test_intraday()
    print("OK")

    report = generate_report(results, xref, intraday, ak_direct)
    print("\n" + report)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = os.path.join(os.path.dirname(__file__), f"provider_candles_test_report_{ts}.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\nRelatorio: {report_path}")

    raw = {"providers": results, "akshare_direct": ak_direct, "cross_ref": xref, "intraday": intraday}
    jpath = report_path.replace(".txt", ".json")
    with open(jpath, "w") as f:
        json.dump(raw, f, indent=2, default=str)
    print(f"Dados: {jpath}")

if __name__ == "__main__":
    main()
