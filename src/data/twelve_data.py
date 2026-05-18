import requests
import os
from typing import Dict, Any


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

    def get_price(self, symbol: str) -> Dict[str, Any]:
        """Obtém preço em tempo real."""
        url = f"{self.base_url}/price"
        params = {"symbol": symbol, "apikey": self.api_key}
        try:
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            if "price" not in data:
                return {"error": data.get("message", "Unknown error")}

            return {
                "symbol": symbol,
                "price": float(data["price"]),
                "source": "twelve_data",
            }
        except Exception as e:
            _log_event("TWELVE_DATA", "ERROR", {"symbol": symbol, "error": str(e)})
            return {"error": str(e)}

    def get_candles(self, symbol: str, timeframe: str = "6M") -> Dict[str, Any]:
        """OHLCV candles via TwelveData /time_series — padronizado para o DataHub."""
        interval, outputsize = _TWELVE_DATA_CANDLE_MAP.get(timeframe, ("1day", 130))
        url = f"{self.base_url}/time_series"
        params = {
            "symbol": symbol,
            "interval": interval,
            "outputsize": outputsize,
            "apikey": self.api_key,
        }
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
