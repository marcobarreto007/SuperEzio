"""
Federal Reserve (Fed) Data Provider — Dados Macroeconômicos dos EUA
==================================================================
Puxa dados de treasuries via yfinance.

Séries disponíveis:
- Fed Funds Rate (proxy: 13-week T-bill ^IRX)
- 10-Year Treasury Yield (^TNX)
- 5-Year Treasury Yield (^FVX)
- 2-Year Treasury Yield (^2YR)
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict

import yfinance as yf

logger = logging.getLogger(__name__)

TREASURY_TICKERS = {
    "fed_funds_proxy": "^IRX",
    "treasury_5y": "^FVX",
    "treasury_10y": "^TNX",
    "treasury_30y": "^TYX",
}


def get_macro_summary_us() -> Dict[str, Any]:
    """
    Busca resumo macro dos EUA via yfinance treasuries.

    Returns:
        Dict com fed_funds_rate, treasury_yields, collected_at
        ou dict com 'error' em caso de falha.
    """
    try:
        result: Dict[str, Any] = {
            "provider": "fed_yfinance",
            "collected_at": datetime.now(timezone.utc).isoformat(),
        }

        for name, ticker in TREASURY_TICKERS.items():
            try:
                t = yf.Ticker(ticker)
                info = t.history(period="5d", interval="1d")
                if not info.empty:
                    latest = info.iloc[-1]
                    result[name] = {
                        "value": round(float(latest["Close"]), 3),
                        "date": str(latest.name.date()),
                        "change_pct": round(
                            (
                                (
                                    (
                                        float(latest["Close"])
                                        - float(info.iloc[-2]["Close"])
                                    )
                                    / float(info.iloc[-2]["Close"])
                                    * 100
                                )
                                if len(info) >= 2
                                else 0
                            ),
                            2,
                        ),
                    }
                else:
                    result[name] = {"value": None, "error": "no data"}
            except Exception as e:
                result[name] = {"value": None, "error": str(e)[:100]}

        return result

    except Exception as e:
        logger.warning("[FED] Failed to fetch US macro: %s", e)
        return {"error": f"fed_provider failed: {e}"}
