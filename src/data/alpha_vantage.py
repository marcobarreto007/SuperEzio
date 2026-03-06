import requests
import os
from typing import Dict, Any


def _log_event(phase: str, event: str, data: dict | None = None) -> None:
    try:
        from core.observability.neural_log import log_event

        log_event(phase, event, data or {})
    except Exception:
        pass


class AlphaVantageProvider:
    """
    Provedor de dados Alpha Vantage.
    Requer ALPHA_VANTAGE_API_KEY configurada no ambiente ou .env.
    """

    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("ALPHA_VANTAGE_API_KEY")
        if not self.api_key:
            raise RuntimeError("ALPHA_VANTAGE_API_KEY is required but not set")
        self.base_url = "https://www.alphavantage.co/query"

    def get_quote(self, symbol: str) -> Dict[str, Any]:
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
                "change_pct": float(
                    quote.get("10. change percent", "0%").replace("%", "")
                ),
                "volume": int(quote.get("06. volume", 0)),
                "source": "alpha_vantage",
            }
        except Exception as e:
            _log_event("ALPHA_VANTAGE", "ERROR", {"symbol": symbol, "error": str(e)})
            return {"error": str(e)}
