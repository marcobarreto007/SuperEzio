import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

try:
    import pandas_ta as ta
except ImportError:
    ta = None

try:
    import yfinance as yf
except ImportError:
    yf = None

try:
    from ..observability.neural_log import log_event as _log_event
except Exception as exc:
    logger.debug("[ENGINE] neural_log unavailable: %s", exc)

    def _log_event(phase, event, data=None):  # type: ignore[misc]
        return None


class FinancialEngine:
    """
    Financial engine used by the pipeline.
    Fetches market candles and computes basic technical indicators.
    """

    def __init__(self):
        _log_event("ENGINE", "INIT", {"backend": "yfinance+pandas_ta"})

    def get_market_data(
        self, symbol: str, period: str = "1y", interval: str = "1d"
    ) -> Dict[str, Any]:
        """Fetch historical prices and compute RSI, MACD and EMA."""
        if yf is None:
            return {
                "error": "yfinance not installed. Install with: pip install yfinance"
            }

        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=period, interval=interval)

            if df.empty:
                return {"error": f"No data found for {symbol}"}

            info = ticker.info
            current_price = info.get("currentPrice") or df["Close"].iloc[-1]

            if ta is not None:
                df.ta.rsi(length=14, append=True)
                df.ta.macd(append=True)
                df.ta.ema(length=20, append=True)
                df.ta.ema(length=50, append=True)
                df.ta.bbands(length=20, std=2, append=True)
                df.ta.stoch(length=14, k=3, d=3, append=True)
            else:
                close = df["Close"]
                high = df["High"]
                low = df["Low"]

                delta = close.diff()
                gain = delta.clip(lower=0)
                loss = -delta.clip(upper=0)
                avg_gain = gain.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
                avg_loss = loss.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
                rs = avg_gain / avg_loss.replace(0, float("nan"))
                df["RSI_14"] = (100 - (100 / (1 + rs))).fillna(100.0)

                ema_12 = close.ewm(span=12, adjust=False).mean()
                ema_26 = close.ewm(span=26, adjust=False).mean()
                df["MACD_12_26_9"] = ema_12 - ema_26
                df["MACDs_12_26_9"] = (
                    df["MACD_12_26_9"].ewm(span=9, adjust=False).mean()
                )
                df["EMA_20"] = close.ewm(span=20, adjust=False).mean()
                df["EMA_50"] = close.ewm(span=50, adjust=False).mean()

                middle = close.rolling(window=20, min_periods=20).mean()
                std = close.rolling(window=20, min_periods=20).std()
                df["BBU_20_2.0"] = middle + (2 * std)
                df["BBL_20_2.0"] = middle - (2 * std)

                lowest = low.rolling(window=14, min_periods=14).min()
                highest = high.rolling(window=14, min_periods=14).max()
                stoch = (
                    100 * (close - lowest) / (highest - lowest).replace(0, float("nan"))
                )
                df["STOCHk_14_3_3"] = stoch.rolling(window=3, min_periods=1).mean()
                df["STOCHd_14_3_3"] = (
                    df["STOCHk_14_3_3"].rolling(window=3, min_periods=1).mean()
                )

            last = df.iloc[-1]

            return {
                "symbol": symbol,
                "price": current_price,
                "rsi_14": float(last.get("RSI_14", 0)),
                "macd": float(last.get("MACD_12_26_9", 0)),
                "macd_signal": float(last.get("MACDs_12_26_9", 0)),
                "ema_20": float(last.get("EMA_20", 0)),
                "ema_50": float(last.get("EMA_50", 0)),
                "bb_upper": float(last.get("BBU_20_2.0", 0)),
                "bb_lower": float(last.get("BBL_20_2.0", 0)),
                "stoch_k": float(last.get("STOCHk_14_3_3", 0)),
                "stoch_d": float(last.get("STOCHd_14_3_3", 0)),
                "volume": int(last["Volume"]),
                "last_updated": str(last.name),
            }

        except Exception as e:
            return {"error": str(e)}

    def get_company_profile(self, symbol: str) -> Dict[str, Any]:
        """Return basic company profile fields."""
        if yf is None:
            return {
                "error": "yfinance not installed. Install with: pip install yfinance"
            }

        try:
            t = yf.Ticker(symbol)
            i = t.info
            return {
                "name": i.get("longName"),
                "sector": i.get("sector"),
                "industry": i.get("industry"),
                "market_cap": i.get("marketCap"),
                "pe_ratio": i.get("trailingPE"),
                "dividend_yield": i.get("dividendYield"),
                "enterprise_to_ebitda": i.get("enterpriseToEbitda"),
                "return_on_equity": i.get("returnOnEquity"),
                "beta": i.get("beta"),
                "summary": i.get("longBusinessSummary"),
            }
        except Exception as exc:
            logger.warning("[ENGINE] profile lookup failed for %s: %s", symbol, exc)
            return {"error": str(exc), "symbol": symbol}
