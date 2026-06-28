"""
PennyDataProvider — Provedor de dados via stack real do SuperEzio
==================================================================
Usa a infraestrutura já existente no projeto:

  Fonte primária:  DataHub (Twelve Data → Alpha Vantage) → preço real-time
  Dados completos: DataCollector.collect_all() → 10 fontes em paralelo
  Fallback final:  DataHub candles + profile (substitui yfinance)

Princípio: nunca depender de uma fonte só. O DataHub já faz fallback
automático entre providers. O DataCollector agrega tudo com timeout.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .schemas import SignalInput, DataQuality, ScanFilter, ScanResult

logger = logging.getLogger(__name__)


def _safe_float(value, default=None) -> Optional[float]:
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def _safe_int(value, default=None) -> Optional[int]:
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


# ---------------------------------------------------------------------------
# fetch_signal — Stack real do SuperEzio
# ---------------------------------------------------------------------------


def _try_datahub(ticker: str) -> Optional[SignalInput]:
    """
    Tenta obter preço via DataHub (Twelve Data → Alpha Vantage).
    É a fonte mais rápida e confiável.
    """
    try:
        from data.data_hub import hub

        result = hub.get_price(ticker)
        if isinstance(result, dict) and "error" not in result and result.get("price"):
            return SignalInput(
                ticker=ticker,
                price=_safe_float(result.get("price")),
                data_quality=DataQuality.REAL,
                source=f"datahub:{result.get('provider', 'unknown')}",
                as_of=datetime.now(timezone.utc).isoformat(),
            )
    except ImportError:
        logger.debug("DataHub não disponível")
    except Exception as e:
        logger.debug(f"DataHub falhou para {ticker}: {e}")

    return None


def _try_collector(ticker: str, timeout: float = 15.0) -> Optional[SignalInput]:
    """
    Tenta obter dados completos via DataCollector (10 fontes em paralelo).
    Roda o loop assíncrono internamente.
    """
    try:
        from core.data_collector import DataCollector

        async def _collect():
            collector = DataCollector()
            return await collector.collect_all(ticker, timeout=timeout)

        data = asyncio.run(_collect())
        return _map_collector_to_signal(ticker, data)
    except ImportError:
        logger.debug("DataCollector não disponível")
    except Exception as e:
        logger.debug(f"DataCollector falhou para {ticker}: {e}")

    return None


def _map_collector_to_signal(ticker: str, data: Dict[str, Any]) -> SignalInput:
    """Mapeia o output do DataCollector para SignalInput do PennyLab."""
    rt = data.get("realtime_price", {}) if isinstance(data.get("realtime_price"), dict) else {}
    tech = data.get("technicals", {}) if isinstance(data.get("technicals"), dict) else {}
    profile = data.get("profile", {}) if isinstance(data.get("profile"), dict) else {}

    price = _safe_float(rt.get("price")) or _safe_float(tech.get("price"))
    prev_close = _safe_float(tech.get("prev_close")) or _safe_float(tech.get("previousClose"))

    return SignalInput(
        ticker=ticker,
        price=price,
        prev_close=prev_close,
        volume=_safe_int(tech.get("volume")),
        avg_volume_10d=_safe_int(tech.get("avg_volume_10d") or tech.get("averageVolume")),
        market_cap=_safe_float(profile.get("market_cap") or profile.get("marketCap")),
        bid=_safe_float(tech.get("bid")),
        ask=_safe_float(tech.get("ask")),
        shares_float=_safe_int(profile.get("shares_float") or profile.get("floatShares")),
        rsi_14=_safe_float(tech.get("rsi_14") or tech.get("rsi")),
        data_quality=DataQuality.REAL,
        source=f"collector:{data.get('data_quality', 'unknown')}",
        as_of=data.get("collected_at") or datetime.now(timezone.utc).isoformat(),
    )


def _try_hub_fallback(ticker: str) -> Optional[SignalInput]:
    """Fallback final: DataHub candles + profile (substitui yfinance)."""
    try:
        from data.data_hub import hub

        quote = hub.get_quote(ticker)
        if "error" in quote:
            return None

        price = _safe_float(quote.get("price"))
        if price is None:
            return None

        prev_close = None
        volume = _safe_int(quote.get("volume"))

        # Try to get additional profile data
        market_cap = None
        shares_float = None
        try:
            profile = hub.get_profile(ticker)
            if "error" not in profile:
                market_cap = _safe_float(profile.get("market_cap"))
        except Exception:
            pass

        return SignalInput(
            ticker=ticker,
            price=price,
            prev_close=prev_close,
            volume=volume,
            avg_volume_10d=None,
            market_cap=market_cap,
            bid=None,
            ask=None,
            shares_float=shares_float,
            data_quality=DataQuality.REAL,
            source="datahub:fallback",
            as_of=datetime.now(timezone.utc).isoformat(),
        )
    except ImportError:
        logger.debug("DataHub não disponível")
    except Exception as e:
        logger.debug(f"DataHub fallback falhou para {ticker}: {e}")

    return None


def fetch_signal(ticker_symbol: str, fast: bool = False) -> SignalInput:
    """
    Busca dados de mercado usando a stack real do SuperEzio.

    Ordem de fallback:
      1. DataCollector (10 fontes em paralelo) — dados completos com volume, técnicos, perfil
      2. DataHub (Twelve Data → Alpha Vantage) — preço real-time
      3. DataHub fallback (quote + profile) — último recurso

    Se fast=True, pula DataCollector e vai direto pra DataHub (mais rápido).

    Retorna SignalInput com data_quality=REAL em caso de sucesso,
    ou UNAVAILABLE se TODAS as fontes falharem.
    """
    ticker_symbol = ticker_symbol.upper().strip()

    # Tier 1: DataCollector (dados completos — volume, técnicos, perfil, preço)
    if not fast:
        signal = _try_collector(ticker_symbol)
        if signal is not None and signal.price is not None:
            return signal
        if signal is not None:
            hub_signal = _try_datahub(ticker_symbol)
            if hub_signal is not None:
                signal.price = hub_signal.price
                signal.source = f"{signal.source}+{hub_signal.source}"
            if signal.price is not None:
                return signal

    # Tier 2: DataHub (rápido, preço real-time)
    hub_signal = _try_datahub(ticker_symbol)
    if hub_signal is not None:
        # Enriquece com hub fallback para volume/profile
        fb_signal = _try_hub_fallback(ticker_symbol)
        if fb_signal is not None:
            hub_signal.volume = hub_signal.volume or fb_signal.volume
            hub_signal.avg_volume_10d = hub_signal.avg_volume_10d or fb_signal.avg_volume_10d
            hub_signal.bid = hub_signal.bid or fb_signal.bid
            hub_signal.ask = hub_signal.ask or fb_signal.ask
            hub_signal.prev_close = hub_signal.prev_close or fb_signal.prev_close
            hub_signal.market_cap = hub_signal.market_cap or fb_signal.market_cap
            hub_signal.shares_float = hub_signal.shares_float or fb_signal.shares_float
            hub_signal.source = f"{hub_signal.source}+hub_enriched"
        return hub_signal

    # Tier 3: DataHub fallback puro
    signal = _try_hub_fallback(ticker_symbol)
    if signal is not None:
        return signal

    return SignalInput(
        ticker=ticker_symbol,
        data_quality=DataQuality.UNAVAILABLE,
        source="all_sources_failed",
    )


# ---------------------------------------------------------------------------
# Scan de tickers
# ---------------------------------------------------------------------------

_PENNY_WATCHLIST: List[str] = [
    "SNDL",
    "HIVE",
    "TLRY",
    "ACB",
    "CGC",
    "OGI",
    "HEXO",
    "NOK",
    "IDEX",
    "FCEL",
    "PLUG",
    "NKLA",
    "RIG",
    "MARA",
    "RIOT",
    "CLSK",
    "BITF",
    "HUT",
    "MSTR",
    "WEED.TO",
    "ACB.TO",
    "LSPD.TO",
    "SHOP.TO",
    "ENB.TO",
    "TD.TO",
    "RY.TO",
    "BNS.TO",
    "CP.TO",
    "CNQ.TO",
    "HIVE.V",
    "WCNR.TO",
    "PETR4.SA",
    "OIBR3.SA",
    "COGN3.SA",
    "MGLU3.SA",
    "BTC-USD",
    "DOGE-USD",
    "PEPE-USD",
    "GLD",
    "GD30.BA",
]


def scan_penny_stocks(
    filters: ScanFilter,
    watchlist: Optional[List[str]] = None,
    max_parallel: int = 10,  # noqa: ARG001 — reserved for async batch scanning
) -> ScanResult:
    """
    Escaneia tickers da watchlist filtrando por preço e volume.
    Usa a stack real do SuperEzio (DataHub → DataCollector).
    """
    candidates: List[str] = []
    skipped: int = 0
    tickers = watchlist or _PENNY_WATCHLIST

    for symbol in tickers:
        signal = fetch_signal(symbol)

        if signal.data_quality == DataQuality.UNAVAILABLE:
            skipped += 1
            continue

        if filters.max_price is not None and signal.price is not None:
            if signal.price > filters.max_price:
                skipped += 1
                continue

        if filters.min_volume is not None and signal.volume is not None:
            if signal.volume < filters.min_volume:
                skipped += 1
                continue

        if signal.bid is not None and signal.ask is not None and signal.bid > 0:
            spread_pct = (signal.ask - signal.bid) / signal.bid * 100
            if spread_pct > filters.max_spread_pct:
                skipped += 1
                continue

        candidates.append(symbol)

    note = (
        f"Scan concluído: {len(candidates)} candidatos, "
        f"{skipped} descartados de {len(tickers)} analisados"
    )

    return ScanResult(
        filters=filters,
        candidates=sorted(candidates),
        skipped=skipped,
        note=note,
    )
