"""
Federal Reserve (Fed) Data Provider — Dados Macroeconômicos dos EUA
==================================================================
Puxa dados de treasuries via Alpha Vantage TREASURY_YIELD.

Séries disponíveis:
- Fed Funds Rate (proxy: 3-month T-bill)
- 5-Year Treasury Yield
- 10-Year Treasury Yield
- 30-Year Treasury Yield
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict

import requests

logger = logging.getLogger(__name__)

TREASURY_MATURITIES = {
    "fed_funds_proxy": "3month",
    "treasury_5y": "5year",
    "treasury_10y": "10year",
    "treasury_30y": "30year",
}


def get_macro_summary_us() -> Dict[str, Any]:
    """
    Busca resumo macro dos EUA via Alpha Vantage TREASURY_YIELD.

    Returns:
        Dict com fed_funds_rate, treasury_yields, collected_at
        ou dict com 'error' em caso de falha.
    """
    api_key = os.getenv("ALPHA_VANTAGE_API_KEY")
    if not api_key:
        return {"error": "ALPHA_VANTAGE_API_KEY not configured"}

    base_url = "https://www.alphavantage.co/query"
    result: Dict[str, Any] = {
        "provider": "alpha_vantage_treasury",
        "collected_at": datetime.now(timezone.utc).isoformat(),
    }

    for name, maturity in TREASURY_MATURITIES.items():
        params = {
            "function": "TREASURY_YIELD",
            "maturity": maturity,
            "apikey": api_key,
        }
        try:
            response = requests.get(base_url, params=params, timeout=10)
            data = response.json()
            if data.get("Error Message") or data.get("Note"):
                result[name] = {
                    "value": None,
                    "error": data.get("Error Message") or data.get("Note"),
                }
                continue

            records = data.get("data", [])
            if records:
                latest = records[0]
                prev = records[1] if len(records) > 1 else latest
                latest_val = float(latest["value"])
                prev_val = float(prev["value"])
                result[name] = {
                    "value": round(latest_val, 3),
                    "date": latest.get("date", ""),
                    "change_pct": (
                        round(((latest_val - prev_val) / prev_val * 100), 2)
                        if prev_val != 0
                        else 0
                    ),
                }
            else:
                result[name] = {"value": None, "error": "no data"}
        except Exception as e:
            logger.warning("[FED] Treasury yield fetch failed for %s: %s", maturity, e)
            result[name] = {"value": None, "error": str(e)[:100]}

    return result
