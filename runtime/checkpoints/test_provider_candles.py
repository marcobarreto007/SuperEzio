#!/usr/bin/env python3
"""
PROVIDER CANDLES TEST — Full comparison of all OHLCV providers in DataHub.

Tests:
  1. Each provider's get_candles() for AAPL, TSLA, SNDL with timeframe 1M
  2. AKShare stock_us_hist() direct call
  3. Cross-reference AAPL close price on 2024-07-15 across all providers
  4. Intraday latency (1min, 5min, 15min) for providers that support it
  5. Ranking report

Output: PROVIDER CANDLES TEST report with ranking.
"""

from __future__ import annotations

import os
import sys
import time
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# ── Ensure src is on path ──────────────────────────────────────────────
SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src"))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

# ── Test symbols ───────────────────────────────────────────────────────
SYMBOLS = ["AAPL", "TSLA", "SNDL"]
TARGET_DATE = "2024-07-15"
TIMEFRAMES_INTRADAY = ["1m", "5m", "15m", "1M"]


# ── Helpers ─────────────────────────────────────────────────────────────
def _fmt_ms(seconds: float) -> str:
    return f"{seconds * 1000:.0f}ms"


def _count_candles(result: dict) -> int:
    c = result.get("candles") or []
    return len(c) if isinstance(c, list) else 0


def _has_fields(candle: dict) -> dict:
    """Check which OHLCV fields are present in the first candle."""
    fields = ["open", "high", "low", "close", "volume"]
    present = {}
    for f in fields:
        val = candle.get(f)
        present[f] = val is not None and val != 0
    return present


def _find_candle_by_date(candles: list, target_date: str) -> dict | None:
    """Find the closest candle to target_date (YYYY-MM-DD)."""
    for c in candles:
        dt = str(c.get("datetime") or c.get("time") or "")
        if dt.startswith(target_date):
            return c
    # Fallback: find nearest
    best = None
    best_diff = float("inf")
    for c in candles:
        dt = str(c.get("datetime") or c.get("time") or "")
        try:
            d = datetime.fromisoformat(dt.split("+")[0].split("Z")[0])
            diff = abs((d - datetime.strptime(target_date, "%Y-%m-%d")).total_seconds())
            if diff < best_diff:
                best_diff = diff
                best = c
        except ValueError:
            continue
    return best


# ── Provider Testers ────────────────────────────────────────────────────

def test_finnhub() -> dict:
    """Test FinnhubProvider.get_candles (requires FINNHUB_API_KEY)."""
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
            fields = _has_fields(data.get("candles", [{}])[0]) if n > 0 else {}
            result["symbols"][sym] = {
                "candle_count": n,
                "latency_ms": round(elapsed * 1000),
                "fields": fields,
                "error": data.get("error"),
            }
    except Exception as e:
        result["reason"] = f"ERROR: {e}"
    return result


def test_twelve_data() -> dict:
    """Test TwelveDataProvider.get_candles (requires TWELVE_DATA_API_KEY)."""
    result: Dict[str, Any] = {"name": "twelve_data", "available": False, "reason": ""}
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
            fields = _has_fields(data.get("candles", [{}])[0]) if n > 0 else {}
            result["symbols"][sym] = {
                "candle_count": n,
                "latency_ms": round(elapsed * 1000),
                "fields": fields,
                "error": data.get("error"),
            }
    except Exception as e:
        result["reason"] = f"ERROR: {e}"
    return result


def test_alpha_vantage() -> dict:
    """Test AlphaVantageProvider.get_ohlcv (requires ALPHA_VANTAGE_API_KEY)."""
    result: Dict[str, Any] = {"name": "alpha_vantage", "available": False, "reason": ""}
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
            fields = _has_fields(data.get("candles", [{}])[0]) if n > 0 else {}
            result["symbols"][sym] = {
                "candle_count": n,
                "latency_ms": round(elapsed * 1000),
                "fields": fields,
                "error": data.get("error"),
            }
    except Exception as e:
        result["reason"] = f"ERROR: {e}"
    return result


def test_yfinance() -> dict:
    """Test YFinanceProvider.get_candles (no API key needed)."""
    result: Dict[str, Any] = {"name": "yfinance", "available": False, "reason": ""}
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
            fields = _has_fields(data.get("candles", [{}])[0]) if n > 0 else {}
            result["symbols"][sym] = {
                "candle_count": n,
                "latency_ms": round(elapsed * 1000),
                "fields": fields,
                "error": data.get("error"),
            }
    except Exception as e:
        result["reason"] = f"ERROR: {e}"
    return result


def test_akshare() -> dict:
    """Test AKShareProvider.get_candles (no API key needed)."""
    result: Dict[str, Any] = {"name": "akshare", "available": False, "reason": ""}
    try:
        from data.akshare_provider import AKShareProvider
        provider = AKShareProvider()
        result["available"] = True
        result["symbols"] = {}
        for sym in SYMBOLS:
            t0 = time.perf_counter()
            data = provider.get_candles(sym, timeframe="1M")
            elapsed = time.perf_counter() - t0
            n = _count_candles(data)
            fields = _has_fields(data.get("candles", [{}])[0]) if n > 0 else {}
            result["symbols"][sym] = {
                "candle_count": n,
                "latency_ms": round(elapsed * 1000),
                "fields": fields,
                "error": data.get("error"),
            }
    except Exception as e:
        result["reason"] = f"ERROR: {e}"
    return result


# ── AKShare direct test ─────────────────────────────────────────────────

def test_akshare_direct() -> dict:
    """Test AKShare stock_us_hist() directly as specified in the task."""
    result: Dict[str, Any] = {"name": "akshare_direct_stock_us_hist", "available": False}
    try:
        import akshare as ak
        result["available"] = True
        df = ak.stock_us_hist(
            symbol="105.AAPL",
            period="daily",
            start_date="20240701",
            end_date="20240720",
        )
        result["rows"] = len(df)
        result["columns"] = list(df.columns)
        result["shape"] = df.shape
        # Check for expected fields
        chinese_names = [c for c in df.columns if any(k in c for k in ["日期", "开盘", "收盘", "最高", "最低", "成交量"])]
        result["chinese_columns"] = chinese_names

        # Show a few rows as dict
        result["head"] = df.head(3).to_dict(orient="records")
        result["tail"] = df.tail(3).to_dict(orient="records")

        # Find 2024-07-15
        for _, row in df.iterrows():
            date_val = str(row.iloc[0])
            if "2024-07-15" in date_val or "20240715" in date_val:
                result["target_date_row"] = {
                    "date": date_val,
                    "open": float(row.iloc[1]),
                    "high": float(row.iloc[2]),
                    "low": float(row.iloc[3]),
                    "close": float(row.iloc[4]),
                    "volume": float(row.iloc[5]) if len(row) > 5 else 0,
                }
                break
        if "target_date_row" not in result:
            result["target_date_note"] = "2024-07-15 not found in range (may be weekend/market holiday)"
    except Exception as e:
        result["reason"] = f"ERROR: {e}"
    return result


# ── Cross-reference AAPL close on 2024-07-15 ────────────────────────────

def cross_reference_aapl_20240715() -> dict:
    """Compare AAPL close price on 2024-07-15 across all working providers."""
    result: Dict[str, Any] = {"target_date": TARGET_DATE, "symbol": "AAPL", "providers": {}}

    # --- yfinance ---
    try:
        from data.yfinance_provider import YFinanceProvider
        provider = YFinanceProvider()
        data = provider.get_candles("AAPL", timeframe="1Y")
        if "candles" in data:
            candle = _find_candle_by_date(data["candles"], TARGET_DATE)
            if candle:
                result["providers"]["yfinance"] = {
                    "close": candle.get("close"),
                    "open": candle.get("open"),
                    "high": candle.get("high"),
                    "low": candle.get("low"),
                    "volume": candle.get("volume"),
                    "datetime": candle.get("datetime"),
                }
    except Exception as e:
        result["providers"]["yfinance"] = {"error": str(e)}

    # --- AKShare via provider ---
    try:
        from data.akshare_provider import AKShareProvider
        provider = AKShareProvider()
        data = provider.get_candles("AAPL", timeframe="1Y")
        if "candles" in data:
            candle = _find_candle_by_date(data["candles"], TARGET_DATE)
            if candle:
                result["providers"]["akshare"] = {
                    "close": candle.get("close"),
                    "open": candle.get("open"),
                    "high": candle.get("high"),
                    "low": candle.get("low"),
                    "volume": candle.get("volume"),
                    "datetime": candle.get("datetime"),
                }
    except Exception as e:
        result["providers"]["akshare"] = {"error": str(e)}

    # --- AKShare direct ---
    try:
        import akshare as ak
        df = ak.stock_us_hist(symbol="105.AAPL", period="daily", start_date="20240701", end_date="20240720")
        for _, row in df.iterrows():
            date_val = str(row.iloc[0])
            if TARGET_DATE in date_val:
                result["providers"]["akshare_direct"] = {
                    "close": float(row.iloc[4]),
                    "open": float(row.iloc[1]),
                    "high": float(row.iloc[2]),
                    "low": float(row.iloc[3]),
                    "volume": float(row.iloc[5]) if len(row) > 5 else 0,
                    "datetime": date_val,
                }
                break
    except Exception as e:
        result["providers"]["akshare_direct"] = {"error": str(e)}

    # --- TwelveData (if available) ---
    td_key = os.getenv("TWELVE_DATA_API_KEY")
    if td_key:
        try:
            from data.twelve_data import TwelveDataProvider
            provider = TwelveDataProvider(api_key=td_key)
            data = provider.get_candles("AAPL", timeframe="1Y")
            if "candles" in data:
                candle = _find_candle_by_date(data["candles"], TARGET_DATE)
                if candle:
                    result["providers"]["twelve_data"] = {
                        "close": candle.get("close"),
                        "open": candle.get("open"),
                        "high": candle.get("high"),
                        "low": candle.get("low"),
                        "volume": candle.get("volume"),
                        "datetime": candle.get("time") or candle.get("datetime"),
                    }
        except Exception as e:
            result["providers"]["twelve_data"] = {"error": str(e)}

    # --- AlphaVantage (if available) ---
    av_key = os.getenv("ALPHA_VANTAGE_API_KEY")
    if av_key:
        try:
            from data.alpha_vantage import AlphaVantageProvider
            provider = AlphaVantageProvider(api_key=av_key)
            data = provider.get_ohlcv("AAPL", timeframe="1Y")
            if "candles" in data:
                candle = _find_candle_by_date(data["candles"], TARGET_DATE)
                if candle:
                    result["providers"]["alpha_vantage"] = {
                        "close": candle.get("close"),
                        "open": candle.get("open"),
                        "high": candle.get("high"),
                        "low": candle.get("low"),
                        "volume": candle.get("volume"),
                        "datetime": candle.get("time") or candle.get("datetime"),
                    }
        except Exception as e:
            result["providers"]["alpha_vantage"] = {"error": str(e)}

    # Determine "truth" — use yfinance as reference (most reliable source)
    yf = result["providers"].get("yfinance", {})
    if "close" in yf:
        result["reference_price"] = yf["close"]
        result["reference_source"] = "yfinance"

    # Calculate discrepancies
    ref = result.get("reference_price")
    if ref:
        discrepancies = {}
        for pname, pdata in result["providers"].items():
            if isinstance(pdata, dict) and "close" in pdata:
                diff = abs(pdata["close"] - ref)
                diff_pct = (diff / ref) * 100
                discrepancies[pname] = {
                    "close": pdata["close"],
                    "diff": round(diff, 4),
                    "diff_pct": round(diff_pct, 4),
                }
        result["discrepancies_vs_reference"] = discrepancies

    return result


# ── Intraday latency test ───────────────────────────────────────────────

def test_intraday_latency() -> dict:
    """Test intraday candle support and latency for each provider."""
    result: Dict[str, Any] = {"symbol": "AAPL", "timeframes": {}}

    # --- AKShare intraday (1m, 5m, 15m) ---
    try:
        from data.akshare_provider import AKShareProvider
        provider = AKShareProvider()
        ak_tfs = {}
        for tf in TIMEFRAMES_INTRADAY[:3]:  # 1m, 5m, 15m
            t0 = time.perf_counter()
            data = provider.get_candles("AAPL", timeframe=tf)
            elapsed = time.perf_counter() - t0
            n = _count_candles(data)
            ak_tfs[tf] = {
                "candle_count": n,
                "latency_ms": round(elapsed * 1000),
                "error": data.get("error"),
            }
        result["timeframes"]["akshare"] = ak_tfs
    except Exception as e:
        result["timeframes"]["akshare"] = {"error": str(e)}

    # --- yfinance intraday (only daily granularity, no real intraday) ---
    try:
        from data.yfinance_provider import YFinanceProvider
        provider = YFinanceProvider()
        yf_tfs = {}
        for tf in TIMEFRAMES_INTRADAY[:3]:
            t0 = time.perf_counter()
            data = provider.get_candles("AAPL", timeframe=tf)
            elapsed = time.perf_counter() - t0
            n = _count_candles(data)
            yf_tfs[tf] = {
                "candle_count": n,
                "latency_ms": round(elapsed * 1000),
                "error": data.get("error"),
            }
        result["timeframes"]["yfinance"] = yf_tfs
    except Exception as e:
        result["timeframes"]["yfinance"] = {"error": str(e)}

    return result


# ── Report generation ───────────────────────────────────────────────────

def generate_report(
    results: Dict[str, Any],
    cross_ref: Dict[str, Any],
    intraday: Dict[str, Any],
    akshare_direct: Dict[str, Any],
) -> str:
    """Generate the text report."""
    lines = []
    lines.append("=" * 76)
    lines.append("PROVIDER CANDLES TEST — RELATORIO COMPLETO")
    lines.append(f"Gerado: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    lines.append("=" * 76)
    lines.append("")

    # ── Part 1: Provider Summary ──
    lines.append("-" * 76)
    lines.append("PARTE 1: DISPONIBILIDADE E CAPABILIDADE DE CADA PROVIDER")
    lines.append("-" * 76)

    for provider_name in ["finnhub", "twelve_data", "alpha_vantage", "yfinance", "akshare"]:
        r = results.get(provider_name, {})
        lines.append(f"\n  [{provider_name.upper()}]")
        if not r.get("available"):
            lines.append(f"    Status: INDISPONIVEL — {r.get('reason', 'unknown')}")
            continue
        lines.append(f"    Status: OK")
        for sym in SYMBOLS:
            sd = r.get("symbols", {}).get(sym, {})
            err = sd.get("error")
            if err:
                lines.append(f"    {sym}: ERRO — {err}")
            else:
                n = sd.get("candle_count", 0)
                lat = sd.get("latency_ms", 0)
                fields = sd.get("fields", {})
                present = [k for k, v in fields.items() if v]
                missing = [k for k, v in fields.items() if not v]
                lines.append(f"    {sym}: {n} candles, {lat}ms, fields=[{','.join(present)}]" +
                             (f" missing=[{','.join(missing)}]" if missing else ""))

    # ── Part 2: AKShare direct test ──
    lines.append("")
    lines.append("-" * 76)
    lines.append("PARTE 2: AKSHARE DIRECT — stock_us_hist(symbol='105.AAPL', period='daily')")
    lines.append("-" * 76)
    if akshare_direct.get("available"):
        lines.append(f"  Rows: {akshare_direct.get('rows', 'N/A')}")
        lines.append(f"  Shape: {akshare_direct.get('shape', 'N/A')}")
        lines.append(f"  Columns: {akshare_direct.get('columns', [])}")
        if "target_date_row" in akshare_direct:
            td = akshare_direct["target_date_row"]
            lines.append(f"  AAPL on 2024-07-15: close={td['close']} open={td['open']} high={td['high']} low={td['low']} vol={td['volume']}")
        else:
            lines.append(f"  Note: {akshare_direct.get('target_date_note', '2024-07-15 not found')}")
        lines.append(f"  Head (3 rows): {json.dumps(akshare_direct.get('head', []), default=str)}")
    else:
        lines.append(f"  FAILED: {akshare_direct.get('reason', 'unknown')}")

    # ── Part 3: Cross-reference ──
    lines.append("")
    lines.append("-" * 76)
    lines.append(f"PARTE 3: CROSS-REFERENCE — AAPL CLOSE PRICE ON {TARGET_DATE}")
    lines.append("-" * 76)
    lines.append(f"  Reference source: {cross_ref.get('reference_source', 'N/A')}")
    lines.append(f"  Reference price:  {cross_ref.get('reference_price', 'N/A')}")
    lines.append("")
    lines.append(f"  {'Provider':<20} {'Close':>10} {'Diff':>10} {'Diff%':>8}")
    lines.append(f"  {'-'*20} {'-'*10} {'-'*10} {'-'*8}")

    disc = cross_ref.get("discrepancies_vs_reference", {})
    for pname, pd in sorted(disc.items()):
        lines.append(f"  {pname:<20} {pd['close']:>10.4f} {pd['diff']:>10.4f} {pd['diff_pct']:>7.3f}%")

    # Show providers that errored
    for pname, pd in cross_ref.get("providers", {}).items():
        if isinstance(pd, dict) and "error" in pd:
            lines.append(f"  {pname:<20} {'ERROR':>10} {pd['error']}")

    # ── Part 4: Intraday latency ──
    lines.append("")
    lines.append("-" * 76)
    lines.append("PARTE 4: INTRADAY LATENCY (AAPL)")
    lines.append("-" * 76)
    lines.append(f"  {'Provider':<12} {'TF':>6} {'Candles':>8} {'Latency':>10}")
    lines.append(f"  {'-'*12} {'-'*6} {'-'*8} {'-'*10}")
    for pname, tfs in intraday.get("timeframes", {}).items():
        if "error" in tfs:
            lines.append(f"  {pname:<12} {'ERROR':>6} {tfs['error']}")
            continue
        for tf, td in tfs.items():
            err = td.get("error")
            if err:
                lines.append(f"  {pname:<12} {tf:>6} {'ERR':>8} {err}")
            else:
                lines.append(f"  {pname:<12} {tf:>6} {td.get('candle_count', 0):>8} {td.get('latency_ms', 0):>6}ms")

    # ── Part 5: Ranking ──
    lines.append("")
    lines.append("=" * 76)
    lines.append("PARTE 5: RANKING FINAL DOS PROVIDERS DE CANDLES")
    lines.append("=" * 76)

    # Score each provider
    scores = _compute_scores(results, cross_ref, intraday, akshare_direct)
    scores.sort(key=lambda x: x[1], reverse=True)

    lines.append(f"\n  {'Rank':<6} {'Provider':<16} {'Score':>6}  {'Notas'}")
    lines.append(f"  {'-'*6} {'-'*16} {'-'*6}  {'-'*40}")
    for i, (name, score, notes) in enumerate(scores, 1):
        lines.append(f"  {i:<6} {name:<16} {score:>6}/100  {notes}")

    lines.append("")
    lines.append("=" * 76)
    lines.append("RECOMENDACAO FINAL")
    lines.append("=" * 76)

    best = scores[0][0] if scores else "N/A"
    lines.append(f"\n  Melhor provider de candles: {best}")
    if best == "yfinance":
        lines.append("  Motivo: Dados diarios confiaveis, sem API key, latencia aceitavel, OHLCV completo.")
        lines.append("  Limitacao: Sem candles intraday (1min/5min/15min).")
    elif best == "akshare":
        lines.append("  Motivo: Intraday + daily, sem API key, OHLCV completo, bom volume de dados.")
        lines.append("  Limitacao: Colunas em chines, latencia maior no intraday.")

    lines.append("")
    lines.append("  Cadeia recomendada para candles (prioridade):")
    lines.append("    1. Finnhub (se tiver key — melhor latencia, dados mais limpos)")
    lines.append("    2. TwelveData (se tiver key — intraday suportado)")
    lines.append("    3. yfinance (sempre disponivel, melhor para daily)")
    lines.append("    4. AKShare (intraday gratis, fallback)")
    lines.append("")
    lines.append("=" * 76)

    return "\n".join(lines)


def _compute_scores(
    results: Dict[str, Any],
    cross_ref: Dict[str, Any],
    intraday: Dict[str, Any],
    akshare_direct: Dict[str, Any],
) -> List[Tuple[str, int, str]]:
    """Compute score (0-100) for each provider."""
    scores: List[Tuple[str, int, str]] = []

    for pname, label in [
        ("finnhub", "Finnhub"),
        ("twelve_data", "TwelveData"),
        ("alpha_vantage", "AlphaVantage"),
        ("yfinance", "yFinance"),
        ("akshare", "AKShare"),
    ]:
        r = results.get(pname, {})
        if not r.get("available"):
            scores.append((label, 0, "Indisponivel (sem API key)"))
            continue

        score = 50  # base
        notes = []

        # Check candle counts across symbols
        total_candles = 0
        total_latency = 0
        n_syms = 0
        all_fields_ok = True

        for sym in SYMBOLS:
            sd = r.get("symbols", {}).get(sym, {})
            err = sd.get("error")
            if err:
                notes.append(f"{sym}: {err}")
                continue
            n_syms += 1
            n = sd.get("candle_count", 0)
            total_candles += n
            total_latency += sd.get("latency_ms", 0)
            fields = sd.get("fields", {})
            if not all(fields.get(f, False) for f in ["open", "high", "low", "close", "volume"]):
                all_fields_ok = False

        if n_syms == 0:
            scores.append((label, 10, "Nenhum simbolo funcionou"))
            continue

        avg_candles = total_candles / n_syms
        avg_latency = total_latency / n_syms

        # Score components
        if avg_candles >= 60:
            score += 15
            notes.append(f"~{avg_candles:.0f}candles/symbol")
        elif avg_candles >= 20:
            score += 8
            notes.append(f"~{avg_candles:.0f}candles/symbol")
        else:
            score -= 5
            notes.append(f"poucos candles({avg_candles:.0f})")

        if avg_latency < 1000:
            score += 15
            notes.append(f"rapido({avg_latency:.0f}ms)")
        elif avg_latency < 3000:
            score += 8
            notes.append(f"latencia media({avg_latency:.0f}ms)")
        else:
            score -= 5
            notes.append(f"lento({avg_latency:.0f}ms)")

        if all_fields_ok:
            score += 10
            notes.append("OHLCV completo")
        else:
            score -= 5
            notes.append("campos ausentes")

        # Intraday support bonus
        intra = intraday.get("timeframes", {}).get(pname, {})
        if isinstance(intra, dict) and not intra.get("error"):
            intra_ok = sum(1 for tf in TIMEFRAMES_INTRADAY[:3] if isinstance(intra.get(tf), dict) and not intra[tf].get("error") and intra[tf].get("candle_count", 0) > 0)
            if intra_ok >= 2:
                score += 15
                notes.append(f"intraday({intra_ok}/3 timeframes)")
            elif intra_ok >= 1:
                score += 8
                notes.append(f"intraday limitado({intra_ok}/3)")

        # Cross-reference accuracy
        disc = cross_ref.get("discrepancies_vs_reference", {})
        if label.lower().startswith("yf"):
            score += 5
            notes.append("referencia de precos")
        elif label.lower().startswith("ak"):
            pd = disc.get("akshare") or disc.get("akshare_direct") or {}
            diff_pct = pd.get("diff_pct", 999)
            if diff_pct < 1:
                score += 5
                notes.append(f"preco preciso(diff {diff_pct:.2f}%)")
            else:
                notes.append(f"preco diff {diff_pct:.2f}%")

        # No API key bonus
        if pname in ("yfinance", "akshare"):
            score += 5
            notes.append("sem API key")

        score = min(100, max(0, score))
        scores.append((label, score, "; ".join(notes)))

    return scores


# ── Main ────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 76)
    print("PROVIDER CANDLES TEST — Iniciando...")
    print("=" * 76)
    print(f"Data: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"Simbolos: {SYMBOLS}")
    print(f"Target cross-ref: AAPL on {TARGET_DATE}")
    print()

    # 1. Test each provider
    results = {}
    for name, func in [
        ("finnhub", test_finnhub),
        ("twelve_data", test_twelve_data),
        ("alpha_vantage", test_alpha_vantage),
        ("yfinance", test_yfinance),
        ("akshare", test_akshare),
    ]:
        print(f"  Testing {name}... ", end="", flush=True)
        r = func()
        results[name] = r
        status = "OK" if r.get("available") else r.get("reason", "FAIL")
        print(status)

    # 2. AKShare direct test
    print(f"\n  Testing akshare direct... ", end="", flush=True)
    akshare_direct = test_akshare_direct()
    status = "OK" if akshare_direct.get("available") else akshare_direct.get("reason", "FAIL")
    print(status)

    # 3. Cross-reference
    print(f"  Cross-referencing AAPL on {TARGET_DATE}... ", end="", flush=True)
    cross_ref = cross_reference_aapl_20240715()
    print(f"OK ({len(cross_ref.get('providers', {}))} providers)")

    # 4. Intraday latency
    print(f"  Testing intraday latency... ", end="", flush=True)
    intraday = test_intraday_latency()
    print("OK")

    # 5. Generate report
    print(f"\n  Generating report...")
    report = generate_report(results, cross_ref, intraday, akshare_direct)
    print()
    print(report)

    # Save report to file
    report_path = os.path.join(
        os.path.dirname(__file__),
        f"provider_candles_test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    )
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\n  Report saved to: {report_path}")

    # Save raw data as JSON
    raw_data = {
        "providers": results,
        "akshare_direct": akshare_direct,
        "cross_reference": cross_ref,
        "intraday": intraday,
    }
    json_path = report_path.replace(".txt", ".json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(raw_data, f, indent=2, default=str)
    print(f"  Raw data saved to: {json_path}")


if __name__ == "__main__":
    main()
