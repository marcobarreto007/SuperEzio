"""Historical Data Cache — 6 months OHLCV for universe tickers.

Stores OHLCV data in SQLite for fast retrieval by experts and RAG.
Supports incremental updates — only fetches missing days.

Schema:
  CREATE TABLE IF NOT EXISTS ohlcv_cache (
      ticker TEXT NOT NULL,
      date TEXT NOT NULL,
      open REAL, high REAL, low REAL, close REAL, volume REAL,
      fetched_at TEXT,
      PRIMARY KEY (ticker, date)
  )
  CREATE INDEX IF NOT EXISTS idx_ohlcv_ticker_date ON ohlcv_cache(ticker, date)
"""

from __future__ import annotations

import logging
import os
import sqlite3
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote

from core.paths import resolve_project_path

logger = logging.getLogger(__name__)

# Resolved against the project root: a relative path here would land in
# src/data when the process runs with cwd=src (split-brain artifacts).
DB_PATH = resolve_project_path("data/historical_cache.db")
LOOKBACK_DAYS = 180  # ~6 months of trading days

# ── Yahoo chart API, direto (sem yfinance) ───────────────────────────────────
# Mesmo endpoint que o Coração usa em core.heart.yahoo_chart, mas este caminho
# lê `adjclose`: o cache alimenta retorno, volatilidade e HRP, onde um split
# vira um salto falso. O Coração grava as-traded de propósito (é arquivo);
# aqui é o contrário, e é por isso que os dois caminhos coexistem.
#
# O User-Agent é o que faz o Yahoo aceitar o pedido: sem um, responde 403
# (core/heart/http.py exige a env var por isso mesmo). Aqui o default é um UA
# de browser e a env var, se existir, manda.
_YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)


def _yahoo_user_agent() -> str:
    return os.getenv("SUPEREZIO_HEART_USER_AGENT", "").strip() or _BROWSER_UA


def _get_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ohlcv_cache (
            ticker TEXT NOT NULL,
            date TEXT NOT NULL,
            open REAL, high REAL, low REAL, close REAL, volume REAL,
            fetched_at TEXT,
            PRIMARY KEY (ticker, date)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ohlcv_ticker_date ON ohlcv_cache(ticker, date)")
    conn.commit()
    return conn


CandleRow = tuple[str, float, float, float, float, float]


def _rows_from_candles(candles: list[dict[str, Any]]) -> list[CandleRow]:
    """Normalize provider-shaped candles into ohlcv_cache rows (date, o, h, l, c, v)."""
    rows: list[CandleRow] = []
    for candle in candles:
        day = str(candle.get("observed_at") or candle.get("datetime") or "")[:10]
        if not day:
            continue
        try:
            rows.append(
                (
                    day,
                    float(candle["open"]),
                    float(candle["high"]),
                    float(candle["low"]),
                    float(candle["close"]),
                    float(candle.get("volume") or 0),
                )
            )
        except (KeyError, TypeError, ValueError, IndexError):
            continue
    return rows


def _rows_from_mesh(ticker: str) -> list[CandleRow]:
    """Reference cache (local, deep history) + live provider mesh, spliced.

    ``load_candle_history_safe`` is a drop-in for ``DataHub.get_candles`` and
    brings the fallback chain, the pacing and the daily quotas with it. This is
    the primary source because the mesh returns split/dividend-adjusted closes,
    which is what the return, volatility and HRP consumers of this cache need.
    """
    try:
        from core.data_collector.candle_history import load_candle_history_safe

        result = load_candle_history_safe(ticker, timeframe="6M")
        if isinstance(result, dict) and not result.get("error"):
            return _rows_from_candles(list(result.get("candles") or []))
    except Exception as exc:  # noqa: BLE001 — malha é melhor esforço; o caminho direto cobre
        logger.debug("mesh_candles_unavailable: %s — %s", ticker, exc)
    return []


# The Heart's own as-traded OHLCV CSVs (core.heart.yahoo_chart). Local, no
# network, no key — 278 series on disk. CAVEAT: these are as-traded closes
# (never adjclose, by design of the Heart archive), so a split shows up as a
# price jump. That is correct for the event archive and wrong for a return
# series, which is why this source sits *after* the adjusted mesh and is only
# a fallback for when the network sources are down.
_HEART_CSV_DIRS = (
    "data/heart/ohlcv",
    "data/reference/effective_universe/ohlcv",
)


def _csv_stems(ticker: str) -> list[str]:
    """File stems to try for a ticker, most likely first (Yahoo download naming).

    Handles the three shapes seen in the wild: a Yahoo ticker as-is (``RY.TO``),
    a TD listing of a class share (``BTCX.B`` -> file ``BTCX-B.TO.csv``, the dot
    becomes a dash and the Canadian suffix is added), and a Yahoo FX pair
    (``CAD=X`` -> file ``CAD_X.csv``). Stems that do not exist on disk cost one
    ``is_file()`` check and fall through.
    """
    t = ticker.upper().strip()
    stems: list[str] = []
    if "=" in t:  # CAD=X -> CAD_X.csv
        stems.append(t.replace("=", "_"))
    stems.append(t)
    if t.endswith(".TO") and "." in t[:-3]:  # BTCX.B.TO -> BTCX-B.TO
        stems.append(f"{t[:-3].replace('.', '-')}.TO")
    elif not t.endswith((".TO", ".V")):
        dashed = t.replace(".", "-")
        if dashed != t:  # BTCX.B -> BTCX-B.TO (listagem canadiana) e BTCX-B
            stems.append(f"{dashed}.TO")
            stems.append(dashed)
        stems.append(f"{t}.TO")  # FCID -> FCID.TO
    return stems


def _rows_from_heart_csv(ticker: str) -> list[CandleRow]:
    """Fallback: read the as-traded CSV the Heart already downloaded (no network)."""
    try:
        from core.heart.ohlcv_csv import bars_from_yahoo_csv
    except ImportError:
        return []
    for directory in _HEART_CSV_DIRS:
        root = resolve_project_path(directory)
        for stem in _csv_stems(ticker):
            path = root / f"{stem}.csv"
            if not path.is_file():
                continue
            try:
                bars = bars_from_yahoo_csv(path)
            except (ValueError, OSError) as exc:
                logger.debug("heart_csv_unreadable: %s — %s", path.name, exc)
                continue
            rows: list[CandleRow] = [
                (
                    str(bar["session_date"])[:10],
                    float(bar["open"]),
                    float(bar["high"]),
                    float(bar["low"]),
                    float(bar["close"]),
                    float(bar.get("volume") or 0),
                )
                for bar in bars
                if bar.get("session_date")
            ]
            if rows:
                return rows
    return []


def _num_at(values: list[Any], index: int) -> float | None:
    if index >= len(values) or values[index] is None:
        return None
    try:
        return float(values[index])
    except (TypeError, ValueError):
        return None


def _rows_from_chart_payload(payload: dict[str, Any]) -> list[CandleRow]:
    """Yahoo chart payload -> cache rows, preferring ``adjclose``.

    ``adjclose`` is what makes a split a non-event for the return math; when
    Yahoo omits it for a series, the raw close is the honest fallback.
    """
    results = (payload.get("chart") or {}).get("result") or []
    if not results:
        return []
    result = results[0]
    timestamps = result.get("timestamp") or []
    indicators = result.get("indicators") or {}
    quote_block = (indicators.get("quote") or [{}])[0]
    adj_block = (indicators.get("adjclose") or [{}])[0]
    adjcloses = adj_block.get("adjclose") or []
    opens = quote_block.get("open") or []
    highs = quote_block.get("high") or []
    lows = quote_block.get("low") or []
    closes = quote_block.get("close") or []
    volumes = quote_block.get("volume") or []

    rows: list[CandleRow] = []
    for index, ts in enumerate(timestamps):
        close = _num_at(adjcloses, index) or _num_at(closes, index)
        if close is None:
            continue
        try:
            day = datetime.fromtimestamp(int(ts), tz=UTC).date().isoformat()
        except (OSError, OverflowError, ValueError):
            continue
        rows.append(
            (
                day,
                _num_at(opens, index) or close,
                _num_at(highs, index) or close,
                _num_at(lows, index) or close,
                close,
                _num_at(volumes, index) or 0.0,
            )
        )
    return rows


def _rows_from_yahoo_chart(ticker: str, *, range_: str = "10y") -> list[CandleRow]:
    """Primary source: the Yahoo chart API over httpx, no yfinance involved.

    yfinance is a wrapper that breaks on its own schedule (a version bump moved
    every column name, measured in the comitê project 2026-10-13). This talks
    to the same endpoint the Heart already trusts, with a browser User-Agent and
    a 10-year window so the consumers get deep history, not six months.
    """
    try:
        import httpx
    except ImportError:
        return []
    url = _YAHOO_CHART_URL.format(symbol=quote(ticker.upper(), safe=".-^="))
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(
                url,
                params={
                    "range": range_,
                    "interval": "1d",
                    "includeAdjustedClose": "true",
                    "events": "split|div",
                },
                headers={"User-Agent": _yahoo_user_agent()},
            )
    except Exception as exc:  # noqa: BLE001 — rede é melhor esforço; a cascata cobre
        logger.debug("yahoo_chart_unreachable: %s — %s", ticker, str(exc)[:120])
        return []
    if response.status_code != 200:
        logger.debug("yahoo_chart_http_%s: %s", response.status_code, ticker)
        return []
    try:
        payload = response.json()
    except ValueError:
        return []
    return _rows_from_chart_payload(payload)


def _load_candle_rows(ticker: str) -> tuple[list[CandleRow], str]:
    """Cache rows for a ticker.

    Order: Yahoo chart API direct (adjusted, no yfinance) → adjusted mesh
    (data_hub, six providers) → local as-traded Heart CSV (offline fallback).
    """
    direct = _rows_from_yahoo_chart(ticker)
    if direct:
        return direct, "yahoo_chart"
    mesh = _rows_from_mesh(ticker)
    if mesh:
        return mesh, "mesh"
    local = _rows_from_heart_csv(ticker)
    if local:
        return local, "heart_csv"
    return [], "none"


def fetch_and_cache_ticker(ticker: str, force: bool = False) -> int:
    """Fetch OHLCV for a ticker and cache in SQLite.

    Returns number of candles cached.
    """
    ticker = ticker.upper().strip()

    # Check if already cached
    if not force:
        conn = _get_db()
        row = conn.execute(
            "SELECT COUNT(*) FROM ohlcv_cache WHERE ticker = ?", (ticker,)
        ).fetchone()
        if row and row[0] > 50:  # At least 50 candles cached
            conn.close()
            return row[0]

    # Mesh first (reference cache + providers via data_hub), direct yfinance last.
    rows, fonte = _load_candle_rows(ticker)
    if not rows:
        logger.warning("no_data_for_ticker: %s", ticker)
        return 0

    conn = _get_db()
    now_iso = datetime.now(UTC).isoformat()
    count = 0

    for date_str, open_, high_, low_, close_, volume_ in rows:
        try:
            conn.execute(
                """INSERT OR REPLACE INTO ohlcv_cache
                   (ticker, date, open, high, low, close, volume, fetched_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (ticker, date_str, open_, high_, low_, close_, volume_, now_iso),
            )
            count += 1
        except Exception as exc:  # noqa: BLE001 — linha de candle malformada é pulada sem derrubar o cache do ticker; loga em debug
            logger.debug("row_skipped_ohlcv: %s %s — %s", ticker, date_str, exc)

    conn.commit()
    conn.close()
    logger.info("cached_ohlcv: %s -> %d candles (%s)", ticker, count, fonte)
    return count


def get_cached_ohlcv(ticker: str, days: int = 180) -> list[dict[str, Any]]:
    """Retrieve cached OHLCV data for a ticker.

    Returns list of {date, open, high, low, close, volume} dicts.
    """
    conn = _get_db()
    cutoff = (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = conn.execute(
        """SELECT date, open, high, low, close, volume 
           FROM ohlcv_cache 
           WHERE ticker = ? AND date >= ?
           ORDER BY date ASC""",
        (ticker.upper(), cutoff),
    ).fetchall()
    conn.close()

    return [
        {
            "date": r[0],
            "open": r[1],
            "high": r[2],
            "low": r[3],
            "close": r[4],
            "volume": r[5],
        }
        for r in rows
    ]


def get_cached_ticker_count() -> int:
    """Number of tickers with cached data."""
    conn = _get_db()
    row = conn.execute("SELECT COUNT(DISTINCT ticker) FROM ohlcv_cache").fetchone()
    conn.close()
    return row[0] if row else 0


def get_cache_stats() -> dict[str, Any]:
    """Cache statistics."""
    conn = _get_db()
    tickers = conn.execute("SELECT COUNT(DISTINCT ticker) FROM ohlcv_cache").fetchone()[0]
    candles = conn.execute("SELECT COUNT(*) FROM ohlcv_cache").fetchone()[0]
    oldest = conn.execute("SELECT MIN(date) FROM ohlcv_cache").fetchone()[0]
    newest = conn.execute("SELECT MAX(date) FROM ohlcv_cache").fetchone()[0]
    conn.close()
    return {
        "tickers_cached": tickers,
        "total_candles": candles,
        "oldest_date": oldest,
        "newest_date": newest,
        "db_path": str(DB_PATH),
        "db_size_mb": round(DB_PATH.stat().st_size / (1024 * 1024), 2) if DB_PATH.exists() else 0,
    }


def batch_fetch_universe(tickers: list[str], max_parallel: int = 5) -> dict[str, int]:
    """Fetch OHLCV for all tickers in the universe.

    Uses sequential fetching to avoid rate limiting.
    Returns {ticker: candles_cached} dict.
    """
    results: dict[str, int] = {}
    total = len(tickers)

    for i, ticker in enumerate(tickers):
        count = fetch_and_cache_ticker(ticker)
        results[ticker] = count
        if (i + 1) % 50 == 0:
            logger.info(
                "batch_progress: %d/%d tickers (%.0f%%)",
                i + 1,
                total,
                (i + 1) / total * 100,
            )
        # Small delay to avoid rate limiting
        if count == 0:
            time.sleep(0.5)
        else:
            time.sleep(0.1)

    logger.info("batch_complete: %d tickers processed", total)
    return results
