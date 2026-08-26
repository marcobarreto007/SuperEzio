import os
from datetime import UTC, datetime
from typing import Any

import requests


def _log_event(phase: str, event: str, data: dict | None = None) -> None:
    try:
        from core.observability.neural_log import log_event

        log_event(phase, event, data or {})
    except Exception:
        pass


# ── SuperEzio timeframe → TwelveData (interval, outputsize) ───────────
_TWELVE_DATA_CANDLE_MAP: dict[str, tuple[str, int]] = {
    "1D": ("5min", 78),
    "1W": ("15min", 130),
    "1M": ("1h", 160),
    "3M": ("1day", 66),
    "6M": ("1day", 130),
    "1Y": ("1day", 252),
    "5Y": ("1week", 260),
}


class TwelveDataProvider:
    """
    Provedor de dados Twelve Data.
    Requer TWELVE_DATA_API_KEY configurada no ambiente ou .env.
    """

    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("TWELVE_DATA_API_KEY")
        if not self.api_key:
            raise RuntimeError("TWELVE_DATA_API_KEY is required but not set")
        self.base_url = "https://api.twelvedata.com"

    def get_price(self, symbol: str, *, exchange: str | None = None) -> dict[str, Any]:
        """Obtain a quote with exchange, currency, and market timestamp metadata."""
        url = f"{self.base_url}/quote"
        tw_symbol = symbol
        tw_exchange = exchange
        if symbol.endswith(".TO"):
            tw_symbol = symbol[:-3]
            tw_exchange = tw_exchange or "TSX"
        elif symbol.endswith(".V"):
            tw_symbol = symbol[:-2]
            tw_exchange = tw_exchange or "TSXV"

        params = {"symbol": tw_symbol, "apikey": self.api_key}
        if tw_exchange:
            params["exchange"] = tw_exchange
        try:
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            price = data.get("close") or data.get("price")
            if price is None:
                return {"error": data.get("message", "Unknown error")}

            timestamp = data.get("last_update_at") or data.get("timestamp")
            if isinstance(timestamp, (int, float)):
                as_of = datetime.fromtimestamp(float(timestamp), tz=UTC).isoformat()
            else:
                as_of = str(timestamp or "").strip() or None

            return {
                "symbol": symbol,
                "price": float(price),
                "source": "twelve_data",
                "provider": "twelve_data",
                "exchange": str(data.get("exchange") or exchange or "").upper() or None,
                "currency": str(data.get("currency") or "").upper() or None,
                "as_of": as_of,
                "market_timestamp": data.get("timestamp"),
            }
        except Exception as e:
            _log_event("TWELVE_DATA", "ERROR", {"symbol": symbol, "error": str(e)})
            return {"error": str(e)}

    def get_candles(self, symbol: str, timeframe: str = "6M") -> dict[str, Any]:
        """OHLCV candles via TwelveData /time_series — padronizado para o DataHub."""
        interval, outputsize = _TWELVE_DATA_CANDLE_MAP.get(timeframe, ("1day", 130))
        url = f"{self.base_url}/time_series"
        tw_symbol = symbol
        tw_exchange = None
        if symbol.endswith(".TO"):
            tw_symbol = symbol[:-3]
            tw_exchange = "TSX"
        elif symbol.endswith(".V"):
            tw_symbol = symbol[:-2]
            tw_exchange = "TSXV"

        params = {
            "symbol": tw_symbol,
            "interval": interval,
            "outputsize": outputsize,
            "apikey": self.api_key,
        }
        if tw_exchange:
            params["exchange"] = tw_exchange
        try:
            response = requests.get(url, params=params, timeout=15)
            data = response.json()
            if data.get("status") == "error":
                return {"error": data.get("message", "Unknown error")}

            values = data.get("values") or []
            candles: list[dict[str, Any]] = []
            for item in values:
                candles.append(
                    {
                        "time": item["datetime"],
                        "open": float(item["open"]),
                        "high": float(item["high"]),
                        "low": float(item["low"]),
                        "close": float(item["close"]),
                        "volume": int(item.get("volume", 0)),
                    }
                )
            candles.reverse()  # TwelveData retorna mais recente primeiro

            return {
                "symbol": symbol,
                "candles": candles,
            }
        except Exception as e:
            _log_event("TWELVE_DATA", "CANDLES_ERROR", {"symbol": symbol, "error": str(e)})
            return {"error": str(e)}
