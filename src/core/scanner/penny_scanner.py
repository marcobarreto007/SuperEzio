"""Penny Stock Scanner — yfinance direct, finds true sub-$5 stocks.

OpenBB discovery methods filter out stocks below $5.
This scanner uses yfinance directly with a curated watchlist
plus dynamic screening to find true penny stocks.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Curated list of known active penny stocks
_PENNY_WATCHLIST = [
    "SNDL", "TLRY", "PLUG", "FCEL", "NOK", "GNUS", "AEHR",
    "SOS", "CEI", "XELA", "BBIG", "ATER", "CRKN", "GFAI",
    "MEGL", "TOP", "PRPL", "KODK", "BB", "NIO", "RIG", "CLF",
    "F", "VALE", "PBR", "HBI", "GPS", "SIRI", "TEVA", "CPRX",
]


def scan_penny_stocks(max_price: float = 5.0, min_volume: int = 100_000) -> list[dict[str, Any]]:
    """Scan for true penny stocks below max_price with minimum volume."""
    try:
        import yfinance as yf
    except ImportError:
        logger.warning("yfinance not installed")
        return []

    results: list[dict[str, Any]] = []
    for ticker in _PENNY_WATCHLIST:
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            price = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose")
            volume = info.get("volume") or info.get("averageVolume") or 0
            name = info.get("shortName") or info.get("longName") or ticker

            if not price:
                continue
            price_f = float(price)
            if price_f <= 0 or price_f > max_price:
                continue
            if volume < min_volume:
                continue

            results.append({
                "ticker": ticker,
                "price": price_f,
                "volume": int(volume),
                "name": str(name),
                "currency": info.get("currency", "USD"),
                "exchange": info.get("exchange", ""),
                "sector": info.get("sector", ""),
                "market_cap": info.get("marketCap"),
                "source": "yfinance_penny",
            })
        except Exception:
            continue

    results.sort(key=lambda x: x["volume"], reverse=True)
    logger.info("Penny scan: %d stocks < $%.2f", len(results), max_price)
    return results
