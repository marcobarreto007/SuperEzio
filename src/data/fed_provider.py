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
import time
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

# Alpha Vantage free tier: 5 calls/min. 4 maturities + 1.5s gap = safe.
_RATE_LIMIT_DELAY_SEC = float(os.getenv("FED_PROVIDER_RATE_DELAY", "1.8"))


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
    empty_count = 0

    for i, (name, maturity) in enumerate(TREASURY_MATURITIES.items()):
        if i > 0:
            time.sleep(_RATE_LIMIT_DELAY_SEC)

        params = {
            "function": "TREASURY_YIELD",
            "maturity": maturity,
            "apikey": api_key,
        }
        try:
            response = requests.get(base_url, params=params, timeout=10)
            data = response.json()

            # Alpha Vantage rate-limit / error surface
            if data.get("Information") and "rate limit" in str(data.get("Information", "")).lower():
                logger.warning("[FED] Alpha Vantage rate limit hit — stopping treasury collection")
                result[name] = {"value": None, "error": "rate_limit"}
                break

            if data.get("Error Message") or data.get("Note"):
                result[name] = {
                    "value": None,
                    "error": str(data.get("Error Message") or data.get("Note"))[:200],
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
                empty_count += 1
                # Distinguish "no data" from "API returned unexpected format"
                top_keys = [k for k in data.keys() if k not in ("data",)]
                detail = f"no data (api_keys={top_keys})" if top_keys else "no data (empty response)"
                result[name] = {"value": None, "error": detail}
                logger.warning(
                    "[FED] Treasury %s returned no records. API keys: %s",
                    maturity,
                    top_keys,
                )
        except Exception as e:
            logger.warning("[FED] Treasury yield fetch failed for %s: %s", maturity, e)
            result[name] = {"value": None, "error": str(e)[:100]}

    if empty_count >= len(TREASURY_MATURITIES):
        result["data_quality"] = "unavailable"

    return result
