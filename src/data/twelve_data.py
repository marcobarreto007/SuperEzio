import requests
import os
from typing import Dict, Any


def _log_event(phase: str, event: str, data: dict | None = None) -> None:
    try:
        from core.observability.neural_log import log_event

        log_event(phase, event, data or {})
    except Exception:
        pass


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
