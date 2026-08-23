"""
Yahoo Finance provider (via yfinance) — last-resort market data fallback.

No API key. Used after Finnhub and Twelve Data fail or are unavailable.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from .finnhub_symbols import finnhub_symbol_variants


class _SuppressYFinanceOutput:
    """Safe context manager without global sys.stdout mutation."""

    def __enter__(self) -> "_SuppressYFinanceOutput":
        return self

    def __exit__(self, *args: Any) -> None:
        pass


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

# Yahoo `Ticker.info` key -> DataHub fundamentals contract key (same payload
# shape as Finnhub get_fundamentals). Yahoo covers TSX/TSXV tickers (.TO/.V)
# with full quoteSummary, so this is the free, keyless fundamentals source for
# Canadian-listed equities. dividendYield is reported by Yahoo in percent
# (2.78 = 2.78%), matching Finnhub's dividendYieldIndicatedAnnual units.
_YF_FUNDAMENTALS_MAP: dict[str, tuple[str, ...]] = {
    "pe_ratio": ("trailingPE", "forwardPE"),
    "forward_pe": ("forwardPE",),
    "beta": ("beta",),
    "eps": ("trailingEps", "forwardEps"),
    "forward_eps": ("forwardEps",),
    "dividend_yield": ("dividendYield",),
    "price_to_book": ("priceToBook",),
    "price_to_sales": ("priceToSalesTrailing12Months",),
    "roe": ("returnOnEquity",),
    "roa": ("returnOnAssets",),
    "profit_margin": ("profitMargins",),
    "operating_margin": ("operatingMargins",),
    "gross_margin": ("grossMargins",),
    "revenue_growth_yoy": ("revenueGrowth",),
    "eps_growth_yoy": ("earningsGrowth",),
    "debt_to_equity": ("debtToEquity",),
    "current_ratio": ("currentRatio",),
    "enterprise_to_ebitda": ("enterpriseToEbitda",),
    "free_cash_flow": ("freeCashflow", "operatingCashflow"),
    "shares_outstanding": ("sharesOutstanding", "impliedSharesOutstanding"),
    "target_mean_price": ("targetMeanPrice",),
    "recommendation_key": ("recommendationKey",),
}


def _utc_observed_at(value: Any) -> str:
    """Return the actual observed instant without relabelling an aware zone."""
    observed = value.to_pydatetime() if hasattr(value, "to_pydatetime") else value
    if not isinstance(observed, datetime):
        raise ValueError("yfinance candle timestamp is not a datetime")
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=timezone.utc)
    else:
        observed = observed.astimezone(timezone.utc)
    return observed.isoformat()


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
                    try:
                        price = getattr(fast, "last_price", None) or getattr(
                            fast, "regular_market_price", None
                        )
                    except Exception:
                        price = None
                if price is None:
                    try:
                        info = getattr(ticker, "info", None) or {}
                        price = info.get("regularMarketPrice") or info.get("currentPrice")
                    except Exception:
                        price = None
                if price is None or float(price) <= 0:
                    try:
                        hist = ticker.history(period="5d")
                        if hist is not None and not hist.empty:
                            price = float(hist["Close"].iloc[-1])
                    except Exception:
                        pass
                if price is None or float(price) <= 0:
                    return {"error": "yfinance_no_price"}

                volume = None
                if fast is not None:
                    try:
                        volume = getattr(fast, "last_volume", None)
                    except Exception:
                        volume = None
                if volume is None:
                    try:
                        info = getattr(ticker, "info", None) or {}
                        volume = info.get("averageVolume") or info.get("volume")
                    except Exception:
                        volume = None

                as_of = None
                try:
                    intraday = ticker.history(period="1d", interval="1m", prepost=False)
                    if intraday is not None and not intraday.empty:
                        price = float(intraday["Close"].iloc[-1])
                        timestamp = intraday.index[-1]
                        if hasattr(timestamp, "to_pydatetime"):
                            as_of = timestamp.to_pydatetime().astimezone(timezone.utc).isoformat()
                except Exception:
                    pass

                exchange = None
                currency = None
                if fast is not None:
                    try:
                        exchange = getattr(fast, "exchange", None)
                        currency = getattr(fast, "currency", None)
                    except Exception:
                        pass

            return {
                "symbol": symbol,
                "yahoo_symbol": ysym,
                "price": float(price),
                "volume": int(volume) if volume is not None else None,
                "source": "yfinance",
                "provider": "yfinance",
                "exchange": str(exchange or "").upper() or None,
                "currency": str(currency or "").upper() or None,
                "as_of": as_of,
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
                ticker = yf.Ticker(ysym)
                try:
                    hist = ticker.history(period=period, auto_adjust=True)
                except KeyError as exc:
                    if "exchangeTimezoneName" in str(exc):
                        # yfinance 1.5.x raises KeyError('exchangeTimezoneName')
                        # when Yahoo omits the timezone metadata field — the
                        # module-level download parses defensively.
                        hist = yf.download(ysym, period=period, auto_adjust=True, progress=False)
                    else:
                        raise
            if hist is None or hist.empty:
                return {"error": "yfinance_no_candles"}
            candles: List[Dict[str, Any]] = []
            for ts, row in hist.iterrows():
                observed_at = _utc_observed_at(ts)
                candles.append(
                    {
                        "datetime": observed_at,
                        "observed_at": observed_at,
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
                ticker = yf.Ticker(ysym)
                try:
                    info = ticker.info or {}
                except KeyError as exc:
                    if "exchangeTimezoneName" in str(exc):
                        # Same yfinance 1.5.x timezone-metadata break — the
                        # get_info() path reads the raw quoteSummary payload.
                        info = ticker.get_info() or {}
                    else:
                        raise
            name = info.get("longName") or info.get("shortName")
            if not name:
                return {"error": "yfinance_no_profile"}
            mcap = info.get("marketCap")
            fcf = info.get("freeCashflow") or info.get("operatingCashflow")
            shares = info.get("sharesOutstanding") or info.get("impliedSharesOutstanding")
            return {
                "symbol": symbol,
                "yahoo_symbol": ysym,
                "name": name,
                "exchange": info.get("exchange"),
                "currency": info.get("currency"),
                "market_cap": int(mcap) if mcap is not None else None,
                "free_cash_flow": float(fcf) if fcf is not None else None,
                "shares_outstanding": int(shares) if shares is not None else None,
                "country": info.get("country"),
                "source": "yfinance",
                "provider": "yfinance",
            }
        except Exception as exc:
            return {"error": f"yfinance: {exc}"}

    def get_fundamentals(
        self,
        symbol: str,
        *,
        market: str | None = None,
        **_: Any,
    ) -> Dict[str, Any]:
        """Keyless fundamentals for any Yahoo-covered market (incl. .TO/.V).

        Uses a single `Ticker.info` call (the same quoteSummary feed as the
        profile method), so it adds no extra dependency or API quota. Works
        for TSX/TSXV tickers where Finnhub/AlphaVantage free tiers are
        unavailable or rate-limited. dividend_yield is in percent, matching
        the Finnhub fundamentals contract.

        Returns:
            {symbol, pe_ratio, beta, eps, dividend_yield, price_to_book, ...,
             sector, industry, market_cap, name, source}
            or {"error": ...} when Yahoo returns no usable metrics.
        """
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
                try:
                    info = ticker.info or {}
                except KeyError as exc:
                    if "exchangeTimezoneName" in str(exc):
                        # Same yfinance 1.5.x timezone-metadata break handled
                        # in get_profile — raw quoteSummary read still works.
                        info = ticker.get_info() or {}
                    else:
                        raise

            payload: Dict[str, Any] = {
                "symbol": symbol,
                "yahoo_symbol": ysym,
                "source": "yfinance",
                "provider": "yfinance",
            }
            for target, sources in _YF_FUNDAMENTALS_MAP.items():
                value = next((info.get(src) for src in sources if info.get(src) is not None), None)
                if value is not None:
                    payload[target] = float(value) if isinstance(value, (int, float)) else value

            name = info.get("longName") or info.get("shortName")
            if name:
                payload["name"] = name
            for target, source in (
                ("sector", "sector"),
                ("industry", "industry"),
                ("currency", "currency"),
                ("country", "country"),
                ("exchange", "exchange"),
            ):
                if info.get(source) is not None:
                    payload[target] = info[source]
            mcap = info.get("marketCap")
            if mcap is not None:
                payload["market_cap"] = int(mcap)
            if info.get("averageVolume") is not None:
                payload["avg_daily_volume_shares"] = int(info["averageVolume"])

            if len(payload) <= 4:  # only symbol/yahoo_symbol/source/provider
                return {"error": "yfinance_no_fundamentals", "symbol": symbol}
            return payload
        except Exception as exc:
            return {"error": f"yfinance: {exc}"}
