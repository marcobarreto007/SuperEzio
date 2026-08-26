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
import sqlite3
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DB_PATH = Path("data/historical_cache.db")
LOOKBACK_DAYS = 180  # ~6 months of trading days


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


def fetch_and_cache_ticker(ticker: str, force: bool = False) -> int:
    """Fetch 6 months of OHLCV for a ticker and cache in SQLite.

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

    # Fetch from Yahoo Finance
    try:
        import yfinance as yf

        end = datetime.now(UTC)
        start = end - timedelta(days=LOOKBACK_DAYS + 10)  # +10 buffer

        stock = yf.Ticker(ticker)
        df = stock.history(start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"))

        if df.empty:
            logger.warning("no_data_for_ticker: %s", ticker)
            return 0

        conn = _get_db()
        now_iso = datetime.now(UTC).isoformat()
        count = 0

        for idx, row in df.iterrows():
            date_str = idx.strftime("%Y-%m-%d")
            try:
                conn.execute(
                    """INSERT OR REPLACE INTO ohlcv_cache 
                       (ticker, date, open, high, low, close, volume, fetched_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        ticker,
                        date_str,
                        float(row["Open"]),
                        float(row["High"]),
                        float(row["Low"]),
                        float(row["Close"]),
                        float(row["Volume"]),
                        now_iso,
                    ),
                )
                count += 1
            except Exception as exc:  # noqa: BLE001 — linha de candle malformada é pulada sem derrubar o cache do ticker; loga em debug
                logger.debug("row_skipped_ohlcv: %s %s — %s", ticker, date_str, exc)

        conn.commit()
        conn.close()
        logger.info("cached_ohlcv: %s -> %d candles", ticker, count)
        return count

    except Exception as e:  # noqa: BLE001 — falha de fetch não derruba o batch; retorna 0 candles
        logger.warning("fetch_failed_ohlcv: %s — %s", ticker, str(e)[:100])
        return 0


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
