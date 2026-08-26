"""
Federal Reserve (Fed) Data Provider — Dados Macroeconomicos dos EUA
==================================================================
Busca treasury yields via Yahoo Finance (gratuito, ilimitado).
Alpha Vantage TREASURY_YIELD como fallback.
"""

import logging
import os
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

# Yahoo Finance tickers for US Treasury yields (free, unlimited)
YFINANCE_TREASURY_TICKERS = {
    "fed_funds_proxy": "^IRX",  # 13-week T-bill (proxy for Fed Funds)
    "treasury_5y": "^FVX",  # 5-year Treasury
    "treasury_10y": "^TNX",  # 10-year Treasury
    "treasury_30y": "^TYX",  # 30-year Treasury
}

# Alpha Vantage fallback (kept for when yfinance is blocked)
AV_TREASURY_MATURITIES = {
    "fed_funds_proxy": "3month",
    "treasury_5y": "5year",
    "treasury_10y": "10year",
    "treasury_30y": "30year",
}


def _fetch_via_yfinance() -> dict[str, Any]:
    """Fetch all treasury yields via Yahoo Finance (free, no rate limit)."""
    result: dict[str, Any] = {
        "provider": "yfinance_treasury",
        "collected_at": datetime.now(UTC).isoformat(),
    }

    try:
        import yfinance as yf

        for name, symbol in YFINANCE_TREASURY_TICKERS.items():
            try:
                ticker = yf.Ticker(symbol)
                info = ticker.info or {}
                price = info.get("regularMarketPrice") or info.get("previousClose")
                if price is not None:
                    result[name] = {
                        "value": round(float(price), 3),
                        "date": datetime.now(UTC).strftime("%Y-%m-%d"),
                    }
                else:
                    result[name] = {"value": None, "error": "yfinance_no_price"}
            except Exception as exc:  # noqa: BLE001 — falha de um símbolo não derruba o fetch de treasury inteiro
                logger.warning("[FED] yfinance failed for %s: %s", symbol, exc)
                result[name] = {"value": None, "error": f"yfinance: {exc}"}

        return result
    except ImportError:
        return {"error": "yfinance_not_installed"}
    except Exception as exc:  # noqa: BLE001 — init do yfinance pode falhar de várias formas; fallback Alpha Vantage existe
        return {"error": f"yfinance_init: {exc}"}


def _fetch_via_alpha_vantage(api_key: str) -> dict[str, Any]:
    """Fallback: fetch treasury yields via Alpha Vantage TREASURY_YIELD."""
    import time

    import requests

    base_url = "https://www.alphavantage.co/query"
    result: dict[str, Any] = {
        "provider": "alpha_vantage_treasury",
        "collected_at": datetime.now(UTC).isoformat(),
    }
    empty_count = 0

    for i, (name, maturity) in enumerate(AV_TREASURY_MATURITIES.items()):
        if i > 0:
            time.sleep(1.8)

        params = {
            "function": "TREASURY_YIELD",
            "maturity": maturity,
            "apikey": api_key,
        }
        try:
            response = requests.get(base_url, params=params, timeout=10)
            data = response.json()

            if data.get("Information") and "rate limit" in str(data.get("Information", "")).lower():
                logger.warning("[FED] Alpha Vantage rate limit — aborting fallback")
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
                        round(((latest_val - prev_val) / prev_val * 100), 2) if prev_val != 0 else 0
                    ),
                }
            else:
                empty_count += 1
                result[name] = {"value": None, "error": "no data"}
        except Exception as exc:  # noqa: BLE001 — falha do fallback é registrada e o fluxo segue para o próximo vencimento
            logger.warning("[FED] Alpha Vantage failed for %s: %s", maturity, exc)
            result[name] = {"value": None, "error": str(exc)[:100]}

    if empty_count >= len(AV_TREASURY_MATURITIES):
        result["data_quality"] = "unavailable"

    return result


def get_macro_summary_us() -> dict[str, Any]:
    """Busca resumo macro dos EUA.

    Primary: Yahoo Finance (free, unlimited).
    Fallback: Alpha Vantage TREASURY_YIELD.
    """
    # 1. Try Yahoo Finance first
    yf_result = _fetch_via_yfinance()
    if "error" not in yf_result:
        filled = sum(
            1 for v in yf_result.values() if isinstance(v, dict) and v.get("value") is not None
        )
        if filled >= 2:
            yf_result["data_quality"] = "collected"
            return yf_result
        logger.warning("[FED] yfinance returned only %d/4 yields — trying Alpha Vantage", filled)
    else:
        logger.warning("[FED] yfinance failed: %s", yf_result.get("error"))

    # 2. Fallback: Alpha Vantage
    api_key = os.getenv("ALPHA_VANTAGE_API_KEY")
    if not api_key:
        return {
            "provider": "none",
            "collected_at": datetime.now(UTC).isoformat(),
            "error": "no_treasury_source",
            "yfinance_error": yf_result.get("error", "unavailable"),
            "data_quality": "unavailable",
        }

    av_result = _fetch_via_alpha_vantage(api_key)
    av_result["_yfinance_failed"] = True
    return av_result
