from typing import Any

import requests

from core.observability.neural_log import log_event


class RealTimeScraper:
    """
    Fallback scraper para dados em tempo real usando a API interna do Yahoo.
    """

    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

    def get_price(self, ticker: str) -> dict[str, Any]:
        """Busca preço, variação e volume via query1.finance.yahoo.com."""
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        try:
            response = requests.get(url, headers=self.headers, timeout=5)
            data = response.json()

            result = data.get("chart", {}).get("result")
            if not result:
                error = data.get("chart", {}).get("error", {}).get("description", "Unknown error")
                return {"error": f"Yahoo API error: {error}"}

            meta = result[0].get("meta", {})
            return {
                "symbol": ticker,
                "price": meta.get("regularMarketPrice"),
                "previous_close": meta.get("previousClose"),
                "currency": meta.get("currency"),
                "exchange": meta.get("exchangeName"),
                "timestamp": meta.get("regularMarketTime"),
                "method": "realtime_api_fallback",
            }
        except Exception as e:  # noqa: BLE001 — catch amplo deliberado: scraper fallback retorna dict de erro, nunca levanta excecao
            log_event("SCRAPER", "ERROR", {"ticker": ticker, "error": str(e)})
            return {"error": str(e)}
