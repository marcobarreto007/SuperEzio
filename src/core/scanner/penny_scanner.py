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
    "SNDL",
    "TLRY",
    "PLUG",
    "FCEL",
    "NOK",
    "GNUS",
    "AEHR",
    "SOS",
    "CEI",
    "XELA",
    "BBIG",
    "ATER",
    "CRKN",
    "GFAI",
    "MEGL",
    "TOP",
    "PRPL",
    "KODK",
    "BB",
    "NIO",
    "RIG",
    "CLF",
    "F",
    "VALE",
    "PBR",
    "HBI",
    "GPS",
    "SIRI",
    "TEVA",
    "CPRX",
]


def scan_penny_stocks(max_price: float = 5.0, min_volume: int = 100_000) -> list[dict[str, Any]]:
    """Scan for true penny stocks below max_price with minimum volume."""
    try:
        import yfinance as yf
    except ImportError:
        logger.warning("yfinance not installed")
        return []

    from concurrent.futures import ThreadPoolExecutor

    def _fetch_one(ticker: str) -> dict[str, Any] | None:
        try:
            stock = yf.Ticker(ticker)
            fast = getattr(stock, "fast_info", None)
            price = None
            volume = None
            if fast is not None:
                try:
                    price = getattr(fast, "last_price", None) or getattr(
                        fast, "regular_market_price", None
                    )
                    volume = getattr(fast, "last_volume", None)
                except Exception as exc:  # noqa: BLE001 — fast_info do yfinance pode lançar vários tipos; fallback é o history()
                    logger.debug("fast_info unavailable for %s: %s", ticker, exc)

            if price is None or float(price) <= 0:
                hist = stock.history(period="1d")
                if hist is not None and not hist.empty:
                    price = float(hist["Close"].iloc[-1])
                    volume = int(hist["Volume"].iloc[-1]) if "Volume" in hist else volume

            if not price:
                return None
            price_f = float(price)
            if price_f <= 0 or price_f > max_price:
                return None

            vol_val = int(volume) if volume else 0
            if vol_val < min_volume:
                return None

            currency = getattr(fast, "currency", "USD") if fast else "USD"
            exchange = getattr(fast, "exchange", "NASDAQ") if fast else "NASDAQ"

            return {
                "ticker": ticker,
                "price": price_f,
                "volume": vol_val,
                "name": ticker,
                "currency": currency,
                "exchange": exchange,
                "source": "yfinance_penny",
            }
        except Exception:  # noqa: BLE001 — falha de um ticker não derruba o scan inteiro; retorna None e segue
            return None

    with ThreadPoolExecutor(max_workers=10) as executor:
        results = [r for r in executor.map(_fetch_one, _PENNY_WATCHLIST) if r is not None]

    results.sort(key=lambda x: x["volume"], reverse=True)
    logger.info("Penny scan: %d stocks < $%.2f", len(results), max_price)
    return results
