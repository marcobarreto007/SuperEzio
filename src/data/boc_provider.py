"""
Bank of Canada (BoC) Data Provider — Dados Macroeconômicos do Canadá
=====================================================================
Puxa dados da Valet API do Bank of Canada.
API pública, sem autenticação.

Séries disponíveis:
- Policy Rate (overnight target): V39079
- CPI (year-over-year): V41690973
- USD/CAD exchange rate: FXUSDCAD
- GDP growth: V62306070 (não usado por ora)
"""

import json
import threading as _threading
import urllib.request
from datetime import datetime
from typing import Any

# Séries Bank of Canada Valet API
BOC_SERIES: dict[str, str] = {
    "policy_rate": "V39079",  # Target for the overnight rate
    "usd_cad": "FXUSDCAD",  # USD/CAD exchange rate
    "cpi_total": "V41690973",  # Total CPI index
}

# Cache simples (1 hora, thread-safe)
_cache: dict[str, Any] = {}
_cache_ts: dict[str, float] = {}
_cache_lock: _threading.Lock = _threading.Lock()
_CACHE_TTL = 3600


def _fetch_boc_series(
    series_id: str,
    recent: int = 10,
) -> list[dict[str, Any]]:
    """
    Busca série do Bank of Canada Valet API.

    Args:
        series_id: Código da série (ex: V39079)
        recent: Número de observações recentes

    Returns:
        Lista de observações com 'd' (date) e valor
    """
    url = f"https://www.bankofcanada.ca/valet/observations/{series_id}/json?recent={recent}"

    cache_key = f"boc_{series_id}_{recent}"
    now = datetime.now().timestamp()

    with _cache_lock:
        if cache_key in _cache and (now - _cache_ts.get(cache_key, 0)) < _CACHE_TTL:
            return _cache[cache_key]

    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:  # nosec: B310 — URL from Bank of Canada API
            raw = json.loads(resp.read().decode("utf-8"))
            observations = raw.get("observations", [])

            # Normalizar formato: [{date, value}, ...]
            result = []
            for obs in observations:
                date = obs.get("d", "")
                val = obs.get(series_id, {})
                if isinstance(val, dict):
                    v = val.get("v", None)
                else:
                    v = val
                if v is not None:
                    result.append({"date": date, "value": v})

            with _cache_lock:
                _cache[cache_key] = result
                _cache_ts[cache_key] = now
            return result

    except Exception as e:
        return [{"error": str(e)}]


def get_policy_rate() -> dict[str, Any]:
    """Retorna taxa de juros do Bank of Canada (overnight target rate)."""
    data = _fetch_boc_series(BOC_SERIES["policy_rate"], recent=10)
    if not data or "error" in data[0]:
        return {"error": "Falha ao buscar BoC Policy Rate", "raw": data}
    last = data[0]
    return {
        "indicator": "BoC Policy Rate",
        "current_value": float(last["value"]),
        "date": last["date"],
        "unit": "% a.a.",
        "history": [{"date": d["date"], "value": float(d["value"])} for d in data],
    }


def get_usd_cad() -> dict[str, Any]:
    """Retorna câmbio USD/CAD."""
    data = _fetch_boc_series(BOC_SERIES["usd_cad"], recent=30)
    if not data or "error" in data[0]:
        return {"error": "Falha ao buscar USD/CAD", "raw": data}
    last = data[0]

    result: dict[str, Any] = {
        "indicator": "USD/CAD",
        "current_value": float(last["value"]),
        "date": last["date"],
        "unit": "CAD per USD",
    }

    # Variação 30 dias
    if len(data) >= 20:
        old = float(data[-1]["value"])
        new = float(last["value"])
        result["change_30d_pct"] = round(((new - old) / old) * 100, 2)

    return result


def get_cpi() -> dict[str, Any]:
    """Retorna CPI (inflação) YoY do Canadá."""
    data = _fetch_boc_series(BOC_SERIES["cpi_total"], recent=24)
    if not data or "error" in data[0]:
        return {"error": "Falha ao buscar CPI Canadá", "raw": data}
    last = data[0]
    last_value = float(last["value"])
    yoy_value = None
    if len(data) >= 13:
        year_ago = float(data[12]["value"])
        if year_ago:
            yoy_value = round(((last_value - year_ago) / year_ago) * 100, 2)

    return {
        "indicator": "CPI Canada (YoY)",
        "current_value": yoy_value if yoy_value is not None else last_value,
        "index_value": last_value,
        "date": last["date"],
        "unit": "% YoY" if yoy_value is not None else "index",
        "history": [{"date": d["date"], "value": float(d["value"])} for d in data],
    }


def get_macro_summary_ca() -> dict[str, Any]:
    """
    Resumo macro completo do Canadá: Policy Rate + CPI + USD/CAD.
    Uma chamada pra todos os dados macro canadenses.
    """
    return {
        "policy_rate": get_policy_rate(),
        "cpi": get_cpi(),
        "usd_cad": get_usd_cad(),
        "country": "Canada",
        "timestamp": datetime.now().isoformat(),
    }
