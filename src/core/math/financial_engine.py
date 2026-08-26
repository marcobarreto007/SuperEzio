import logging
from typing import Any

from .indicators import ema as canonical_ema
from .indicators import macd as canonical_macd
from .indicators import rsi as canonical_rsi

logger = logging.getLogger(__name__)

try:
    import pandas as pd
except ImportError:
    pd = None

try:
    from ..observability.neural_log import log_event as _log_event
except Exception as exc:  # noqa: BLE001 — telemetria opcional nunca pode quebrar o engine financeiro; fallback no-op
    logger.debug("[ENGINE] neural_log unavailable: %s", exc)

    def _log_event(phase, event, data=None):  # type: ignore[misc]
        return None


class FinancialEngine:
    """
    Financial engine used by the pipeline.
    Fetches market candles via DataHub and computes technical indicators.
    """

    def __init__(self):
        _log_event("ENGINE", "INIT", {"backend": "datahub+indicators"})

    def get_market_data(
        self, symbol: str, period: str = "1y", interval: str = "1d"
    ) -> dict[str, Any]:
        """Fetch historical prices and compute RSI, MACD and EMA via DataHub."""
        try:
            from data.data_hub import hub
        except ImportError:
            return {"error": "DataHub not available"}

        # Map yfinance-style period to SuperEzio timeframe
        _PERIOD_TO_TF = {
            "1d": "1D",
            "5d": "1W",
            "1mo": "1M",
            "3mo": "3M",
            "6mo": "6M",
            "1y": "1Y",
            "5y": "5Y",
        }
        timeframe = _PERIOD_TO_TF.get(period, "6M")

        try:
            result = hub.get_candles(symbol, timeframe=timeframe)
            if "error" in result:
                return {"error": str(result.get("error") or result.get("attempts"))}

            candles = result.get("candles", [])
            if not candles:
                return {"error": f"No data found for {symbol}"}

            # Build close/high/low/volume lists from candles
            closes = [c["close"] for c in candles]
            highs = [c["high"] for c in candles]
            lows = [c["low"] for c in candles]
            volumes = [c["volume"] for c in candles]
            current_price = closes[-1]

            # Compute indicators from close prices
            rsi14 = _compute_rsi(closes, 14)
            macd_v, macd_s = _compute_macd(closes)
            ema20 = _compute_ema(closes, 20)
            ema50 = _compute_ema(closes, 50)
            bb_u, bb_l = _compute_bollinger(closes, 20)
            stoch_k, stoch_d = _compute_stoch(highs, lows, closes, 14)

            return {
                "symbol": symbol,
                "price": current_price,
                "rsi_14": rsi14,
                "macd": macd_v,
                "macd_signal": macd_s,
                "ema_20": ema20,
                "ema_50": ema50,
                "bb_upper": bb_u,
                "bb_lower": bb_l,
                "stoch_k": stoch_k,
                "stoch_d": stoch_d,
                "volume": volumes[-1] if volumes else 0,
                "last_updated": str(candles[-1].get("time", "")),
            }

        except Exception as e:  # noqa: BLE001 — contrato público do método: falha vira dict de erro, nunca exceção
            return {"error": str(e)}

    def get_company_profile(self, symbol: str) -> dict[str, Any]:
        """Return basic company profile fields via DataHub."""
        try:
            from data.data_hub import hub
        except ImportError:
            return {"error": "DataHub not available"}

        try:
            result = hub.get_profile(symbol)
            if "error" in result:
                return result
            return {
                "name": result.get("name"),
                "sector": result.get("sector"),
                "industry": result.get("industry"),
                "market_cap": result.get("market_cap"),
                "pe_ratio": result.get("pe_ratio"),
                "dividend_yield": result.get("dividend_yield"),
                "enterprise_to_ebitda": result.get("enterprise_to_ebitda"),
                "return_on_equity": result.get("return_on_equity"),
                "beta": result.get("beta"),
                "summary": result.get("summary"),
            }
        except Exception as exc:  # noqa: BLE001 — contrato público do método: falha vira dict de erro, nunca exceção
            logger.warning("[ENGINE] profile lookup failed for %s: %s", symbol, exc)
            return {"error": str(exc), "symbol": symbol}


# ── Indicator helpers (pure functions, no pandas dependency) ────────────


def _compute_rsi(closes: list, period: int = 14) -> float:
    value = canonical_rsi(closes, period)
    return round(value, 1) if value is not None else 50.0


def _compute_ema(values: list, span: int) -> float:
    value = canonical_ema(values, span)
    return round(value, 2) if value is not None else 0.0


def _compute_macd(closes: list) -> tuple[float, float]:
    values = canonical_macd(closes)
    line = values["macd"]
    signal = values["signal"]
    return (
        round(line, 4) if line is not None else 0.0,
        round(signal, 4) if signal is not None else 0.0,
    )


def _compute_bollinger(closes: list, period: int = 20) -> tuple[float, float]:
    if len(closes) < period:
        return 0.0, 0.0
    window = closes[-period:]
    mean = sum(window) / period
    variance = sum((x - mean) ** 2 for x in window) / period
    std = variance**0.5
    return round(mean + 2 * std, 2), round(mean - 2 * std, 2)


def _compute_stoch(highs: list, lows: list, closes: list, period: int = 14) -> tuple[float, float]:
    if len(closes) < period:
        return 50.0, 50.0
    h = max(highs[-period:])
    lo = min(lows[-period:])
    if h == lo:
        return 50.0, 50.0
    k = 100.0 * (closes[-1] - lo) / (h - lo)
    return round(k, 1), round(k, 1)
