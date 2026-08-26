import os
from typing import Any

import requests


def _log_event(phase: str, event: str, data: dict | None = None) -> None:
    try:
        from core.observability.neural_log import log_event

        log_event(phase, event, data or {})
    except Exception:  # noqa: BLE001,S110 — telemetria é best-effort: falha de log nunca pode derrubar o chamador
        pass


# ── SuperEzio timeframe → AlphaVantage (function, interval, outputsize) ─
_AV_CANDLE_MAP: dict[str, tuple[str, str | None, str]] = {
    "1D": ("TIME_SERIES_INTRADAY", "5min", "compact"),
    "1W": ("TIME_SERIES_INTRADAY", "15min", "compact"),
    "1M": ("TIME_SERIES_INTRADAY", "60min", "compact"),
    "3M": ("TIME_SERIES_DAILY", None, "compact"),
    "6M": ("TIME_SERIES_DAILY", None, "compact"),
    "1Y": ("TIME_SERIES_DAILY", None, "compact"),
    "5Y": ("TIME_SERIES_WEEKLY", None, "compact"),
}

# Keys que AlphaVantage usa nas respostas de time series
_AV_SERIES_KEYS = (
    "Time Series (Daily)",
    "Time Series (5min)",
    "Time Series (15min)",
    "Time Series (60min)",
    "Weekly Time Series",
)


def _parse_av_time_series(data: dict) -> list[dict[str, Any]]:
    """Extrai candles de qualquer resposta time series do AlphaVantage."""
    series_key = next((k for k in _AV_SERIES_KEYS if k in data), None)
    if not series_key:
        return []
    raw = data[series_key]
    candles: list[dict[str, Any]] = []
    for ts, values in raw.items():
        candles.append(
            {
                "time": ts,
                "open": float(values.get("1. open", 0)),
                "high": float(values.get("2. high", 0)),
                "low": float(values.get("3. low", 0)),
                "close": float(values.get("4. close", 0)),
                "volume": int(values.get("5. volume", 0)),
            }
        )
    candles.sort(key=lambda c: c["time"])
    return candles


class AlphaVantageProvider:
    """
    Provedor de dados Alpha Vantage.
    Requer ALPHA_VANTAGE_API_KEY configurada no ambiente ou .env.
    """

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("ALPHA_VANTAGE_API_KEY")
        if not self.api_key:
            raise RuntimeError("ALPHA_VANTAGE_API_KEY is required but not set")
        self.base_url = "https://www.alphavantage.co/query"

    def get_quote(self, symbol: str) -> dict[str, Any]:
        """Obtém cotação em tempo real (Global Quote)."""
        params = {"function": "GLOBAL_QUOTE", "symbol": symbol, "apikey": self.api_key}
        try:
            response = requests.get(self.base_url, params=params, timeout=10)
            data = response.json()
            quote = data.get("Global Quote", {})
            if not quote:
                return {"error": "No data found"}

            return {
                "symbol": symbol,
                "price": float(quote.get("05. price", 0)),
                "change_pct": float(quote.get("10. change percent", "0%").replace("%", "")),
                "volume": int(quote.get("06. volume", 0)),
                "source": "alpha_vantage",
            }
        except Exception as e:  # noqa: BLE001 — contrato do provider: falha vira dict de erro, nunca levanta
            _log_event("ALPHA_VANTAGE", "ERROR", {"symbol": symbol, "error": str(e)})
            return {"error": str(e)}

    def get_ohlcv(self, symbol: str, timeframe: str = "6M") -> dict[str, Any]:
        """OHLCV candles via AlphaVantage — padronizado para o DataHub."""
        function, interval, outputsize = _AV_CANDLE_MAP.get(
            timeframe, ("TIME_SERIES_DAILY", None, "compact")
        )
        params: dict[str, str] = {
            "function": function,
            "symbol": symbol,
            "apikey": self.api_key,
        }
        if interval:
            params["interval"] = interval
        if outputsize:
            params["outputsize"] = outputsize

        try:
            response = requests.get(self.base_url, params=params, timeout=15)
            data = response.json()
            if data.get("Error Message") or data.get("Note"):
                return {"error": data.get("Error Message") or data.get("Note")}

            candles = _parse_av_time_series(data)
            if not candles:
                return {"error": "No time series data found"}

            return {"symbol": symbol, "candles": candles}
        except Exception as e:  # noqa: BLE001 — contrato do provider: falha vira dict de erro, nunca levanta
            _log_event("ALPHA_VANTAGE", "OHLCV_ERROR", {"symbol": symbol, "error": str(e)})
            return {"error": str(e)}

    def get_profile(self, symbol: str) -> dict[str, Any]:
        """Company overview (nome, setor, market cap, moeda, exchange)."""
        params = {"function": "OVERVIEW", "symbol": symbol, "apikey": self.api_key}
        try:
            response = requests.get(self.base_url, params=params, timeout=10)
            data = response.json()
            if not data or data.get("Note"):
                return {"error": data.get("Note", "No profile data")}
            return {
                "symbol": symbol,
                "name": data.get("Name") or symbol,
                "sector": data.get("Sector"),
                "currency": data.get("Currency", "USD"),
                "exchange": data.get("Exchange"),
                "market_cap": (
                    int(float(data["MarketCapitalization"]))
                    if data.get("MarketCapitalization")
                    else None
                ),
            }
        except Exception as e:  # noqa: BLE001 — contrato do provider: falha vira dict de erro, nunca levanta
            _log_event("ALPHA_VANTAGE", "PROFILE_ERROR", {"symbol": symbol, "error": str(e)})
            return {"error": str(e)}

    def get_treasury_yield(self, maturity: str = "10year") -> dict[str, Any]:
        """US Treasury yield para uma maturity específica (3month, 2year, 5year, 7year, 10year, 30year)."""
        params = {
            "function": "TREASURY_YIELD",
            "maturity": maturity,
            "apikey": self.api_key,
        }
        try:
            response = requests.get(self.base_url, params=params, timeout=10)
            data = response.json()
            if data.get("Error Message") or data.get("Note"):
                return {"error": data.get("Error Message") or data.get("Note")}
            return {"maturity": maturity, "data": data.get("data", [])}
        except Exception as e:  # noqa: BLE001 — contrato do provider: falha vira dict de erro, nunca levanta
            _log_event(
                "ALPHA_VANTAGE",
                "TREASURY_ERROR",
                {"maturity": maturity, "error": str(e)},
            )
            return {"error": str(e)}
