"""
Yahoo Finance provider (via yfinance) — last-resort market data fallback.

No API key. Used after Finnhub and Twelve Data fail or are unavailable.
"""

from __future__ import annotations

import io
import sys
from datetime import timezone
from typing import Any, Dict, List

from .finnhub_symbols import finnhub_symbol_variants


class _SuppressYFinanceOutput:
    """Context manager to suppress yfinance stdout/stderr spam ("possibly delisted", etc.)."""

    def __init__(self) -> None:
        self._devnull = io.StringIO()
        self._old_stdout: list[Any] = []
        self._old_stderr: list[Any] = []

    def __enter__(self) -> "_SuppressYFinanceOutput":
        self._old_stdout.append(sys.stdout)
        self._old_stderr.append(sys.stderr)
        sys.stdout = self._devnull  # type: ignore[assignment]
        sys.stderr = self._devnull  # type: ignore[assignment]
        return self

    def __exit__(self, *args: Any) -> None:
        sys.stdout = self._old_stdout.pop()
        sys.stderr = self._old_stderr.pop()


def yfinance_ticker(symbol: str, market: str | None = None) -> str | None:
    """Best-effort Yahoo ticker (BRK-B, RY.TO, etc.)."""
    variants = finnhub_symbol_variants(symbol, market)
    if not variants:
        return None
    raw = variants[0]
    if "." in raw and not raw.endswith((".TO", ".V")):
        return raw.replace(".", "-")
    return raw


_PERIOD_MAP: dict[str, str] = {
    "1D": "5d",
    "1W": "1mo",
    "1M": "3mo",
    "3M": "6mo",
    "6M": "6mo",
    "1Y": "1y",
    "5Y": "5y",
}


class YFinanceProvider:
    """Delayed/real-time equity data through yfinance."""

    def get_price(
        self,
        symbol: str,
        *,
        market: str | None = None,
        **_: Any,
    ) -> Dict[str, Any]:
        ysym = yfinance_ticker(symbol, market)
        if not ysym:
            return {"error": "invalid_symbol"}
        try:
            import yfinance as yf
        except ImportError:
            return {"error": "yfinance_not_installed"}

        try:
            with _SuppressYFinanceOutput():
                ticker = yf.Ticker(ysym)
                fast = getattr(ticker, "fast_info", None)
                price = None
                if fast is not None:
                    price = getattr(fast, "last_price", None) or getattr(
                        fast, "regular_market_price", None
                    )
                if price is None:
                    info = ticker.info or {}
                    price = info.get("regularMarketPrice") or info.get(
                        "currentPrice"
                    )
                if price is None or float(price) <= 0:
                    hist = ticker.history(period="5d")
                    if hist is not None and not hist.empty:
                        price = float(hist["Close"].iloc[-1])
                if price is None or float(price) <= 0:
                    return {"error": "yfinance_no_price"}

                volume = None
                if fast is not None:
                    volume = getattr(fast, "last_volume", None)
                if volume is None:
                    info = ticker.info or {}
                    volume = info.get("averageVolume") or info.get("volume")

            return {
                "symbol": symbol,
                "yahoo_symbol": ysym,
                "price": float(price),
                "volume": int(volume) if volume is not None else None,
                "source": "yfinance",
                "provider": "yfinance",
            }
        except Exception as exc:
            return {"error": f"yfinance: {exc}"}

    def get_candles(
        self,
        symbol: str,
        timeframe: str = "6M",
        *,
        market: str | None = None,
        **_: Any,
    ) -> Dict[str, Any]:
        ysym = yfinance_ticker(symbol, market)
        if not ysym:
            return {"error": "invalid_symbol"}
        try:
            import yfinance as yf
        except ImportError:
            return {"error": "yfinance_not_installed"}

        period = _PERIOD_MAP.get(timeframe, "6mo")
        try:
            with _SuppressYFinanceOutput():
                hist = yf.Ticker(ysym).history(period=period, auto_adjust=True)
            if hist is None or hist.empty:
                return {"error": "yfinance_no_candles"}
            candles: List[Dict[str, Any]] = []
            for ts, row in hist.iterrows():
                candles.append(
                    {
                        "datetime": (
                            ts.to_pydatetime().replace(tzinfo=timezone.utc)
                            if hasattr(ts, "to_pydatetime")
                            else str(ts)
                        ),
                        "open": float(row["Open"]),
                        "high": float(row["High"]),
                        "low": float(row["Low"]),
                        "close": float(row["Close"]),
                        "volume": float(row.get("Volume") or 0),
                    }
                )
            return {
                "symbol": symbol,
                "yahoo_symbol": ysym,
                "timeframe": timeframe,
                "candles": candles,
                "source": "yfinance",
                "provider": "yfinance",
            }
        except Exception as exc:
            return {"error": f"yfinance: {exc}"}

    def get_profile(
        self,
        symbol: str,
        *,
        market: str | None = None,
        **_: Any,
    ) -> Dict[str, Any]:
        ysym = yfinance_ticker(symbol, market)
        if not ysym:
            return {"error": "invalid_symbol"}
        try:
            import yfinance as yf
        except ImportError:
            return {"error": "yfinance_not_installed"}
        try:
            with _SuppressYFinanceOutput():
                info = yf.Ticker(ysym).info or {}
            name = info.get("longName") or info.get("shortName")
            if not name:
                return {"error": "yfinance_no_profile"}
            mcap = info.get("marketCap")
            return {
                "symbol": symbol,
                "yahoo_symbol": ysym,
                "name": name,
                "exchange": info.get("exchange"),
                "currency": info.get("currency"),
                "market_cap": int(mcap) if mcap is not None else None,
                "country": info.get("country"),
                "source": "yfinance",
                "provider": "yfinance",
            }
        except Exception as exc:
            return {"error": f"yfinance: {exc}"}
