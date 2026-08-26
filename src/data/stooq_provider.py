"""
Stooq delayed quote provider — no API key required.

Used as a last-resort price fallback when Finnhub / Twelve Data / Alpha Vantage
are missing or rate-limited. Suitable for liquid US and Canada listings in the
US_CANADA_LIQUID scan universe.
"""

from __future__ import annotations

import csv
import io
from typing import Any

import requests


def stooq_symbol(symbol: str, market: str | None = None) -> str | None:
    """Map a FinanceDatabase-style ticker to a Stooq symbol (e.g. aapl.us)."""
    raw = (symbol or "").strip().upper()
    if not raw:
        return None

    market_l = (market or "").lower()
    if raw.endswith(".TO"):
        return raw.lower()
    if raw.endswith(".V"):
        return raw.lower()
    if "canada" in market_l:
        base = raw.split(".")[0]
        return f"{base.lower()}.to"

    base = raw.replace(".", "-")
    return f"{base.lower()}.us"


class StooqProvider:
    """Fetch last close from Stooq CSV endpoint (delayed, free)."""

    def __init__(self) -> None:
        self.base_url = "https://stooq.com/q/l/"
        self.timeout = 12

    def get_price(
        self,
        symbol: str,
        *,
        market: str | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        stooq_sym = stooq_symbol(symbol, market)
        if not stooq_sym:
            return {"error": "invalid_symbol"}

        params = {"s": stooq_sym, "f": "sd2t2ohlcv", "h": "", "e": "csv"}
        try:
            response = requests.get(self.base_url, params=params, timeout=self.timeout)
            response.raise_for_status()
        except Exception as exc:
            return {"error": f"stooq_http: {exc}"}

        text = response.text.strip()
        if not text or "Exceeded" in text:
            return {"error": "stooq_rate_or_empty"}

        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
        if not rows:
            return {"error": "stooq_no_rows"}

        row = rows[-1]
        close_raw = row.get("Close") or row.get("close")
        if close_raw in (None, "", "N/D"):
            return {"error": "stooq_no_close"}

        try:
            price = float(str(close_raw).replace(",", ""))
        except ValueError:
            return {"error": "stooq_bad_close"}

        if price <= 0:
            return {"error": "stooq_zero_close"}

        volume_raw = row.get("Volume") or row.get("volume")
        volume: int | None = None
        if volume_raw not in (None, "", "N/D"):
            try:
                volume = int(float(str(volume_raw).replace(",", "")))
            except ValueError:
                volume = None

        return {
            "symbol": symbol,
            "price": price,
            "volume": volume,
            "source": "stooq",
            "provider": "stooq",
            "stooq_symbol": stooq_sym,
        }
