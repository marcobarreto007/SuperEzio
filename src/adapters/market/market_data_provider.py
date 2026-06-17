"""Market Data Provider - dados de mercado reais para Bob.

Fontes:
- IBKR (via ib_insync) - dados em tempo real
- Yahoo Finance (yfinance) - gratuito, dados históricos e tempo real
- Alpha Vantage - backups

Bob precisa de dados reais para tomar decisões.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class DataSource(Enum):
    """Fontes de dados."""
    IBKR = "ibkr"
    YAHOO = "yahoo"
    ALPHA_VANTAGE = "alpha_vantage"
    FALLBACK = "fallback"


@dataclass
class MarketData:
    """Dados de mercado para um ativo."""
    symbol: str
    last_price: float
    bid: float | None = None
    ask: float | None = None
    volume: int | None = None
    avg_daily_volume: int | None = None
    change: float | None = None
    change_pct: float | None = None
    day_high: float | None = None
    day_low: float | None = None
    prev_close: float | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source: DataSource = DataSource.YAHOO

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "last_price": round(self.last_price, 2),
            "bid": self.bid,
            "ask": self.ask,
            "volume": self.volume,
            "avg_daily_volume": self.avg_daily_volume,
            "change": self.change,
            "change_pct": self.change_pct,
            "day_high": self.day_high,
            "day_low": self.day_low,
            "prev_close": self.prev_close,
            "timestamp": self.timestamp,
            "source": self.source.value,
        }


class MarketDataProvider:
    """Provider de dados de mercado.

    Tenta múltiplas fontes em ordem de preferência.
    """

    def __init__(self, prefer_ibkr: bool = True):
        self._prefer_ibkr = prefer_ibkr
        self._ibkr_service = None
        self._cache: dict[str, MarketData] = {}
        self._cache_time: dict[str, float] = {}
        self._cache_ttl_seconds = 5  # Cache de 5s

    def _get_ibkr_service(self):
        """Obtém serviço IBKR se disponível."""
        if self._ibkr_service is None and self._prefer_ibkr:
            try:
                from adapters.broker.ibkr_service import get_ibkr_service
                self._ibkr_service = get_ibkr_service()
            except Exception as e:
                logger.warning("IBKR service not available: %s", e)
        return self._ibkr_service

    def get_data(self, symbol: str, force_refresh: bool = False) -> MarketData | None:
        """Obtém dados de mercado para um símbolo.

        Args:
            symbol: Ticker (ex: AAPL)
            force_refresh: Ignorar cache

        Returns:
            MarketData ou None se falhar
        """
        # Checar cache
        now = time.monotonic()
        cached = self._cache.get(symbol)
        if cached and not force_refresh:
            cache_age = now - self._cache_time.get(symbol, 0)
            if cache_age < self._cache_ttl_seconds:
                logger.debug("Cache hit for %s (age %.1fs)", symbol, cache_age)
                return cached

        # Tentar IBKR primeiro
        if self._prefer_ibkr:
            service = self._get_ibkr_service()
            if service:
                status = service.get_status()
                if status.get("connected") and status.get("can_read"):
                    data = self._fetch_from_ibkr(symbol)
                    if data:
                        self._cache[symbol] = data
                        self._cache_time[symbol] = now
                        return data

        # Fallback para Yahoo Finance
        data = self._fetch_from_yahoo(symbol)
        if data:
            self._cache[symbol] = data
            self._cache_time[symbol] = now
            return data

        logger.error("Failed to fetch data for %s", symbol)
        return None

    def _fetch_from_ibkr(self, symbol: str) -> MarketData | None:
        """Busca dados do IBKR."""
        try:
            service = self._get_ibkr_service()
            if not service:
                return None

            # IBKR service tem ticker data
            ticker_data = service.get_ticker(symbol)
            if not ticker_data:
                return None

            return MarketData(
                symbol=symbol,
                last_price=ticker_data.get("last_price", 0),
                bid=ticker_data.get("bid"),
                ask=ticker_data.get("ask"),
                volume=ticker_data.get("volume"),
                avg_daily_volume=ticker_data.get("avg_volume"),
                change=ticker_data.get("change"),
                change_pct=ticker_data.get("change_pct"),
                day_high=ticker_data.get("high"),
                day_low=ticker_data.get("low"),
                prev_close=ticker_data.get("prev_close"),
                source=DataSource.IBKR,
            )
        except Exception as e:
            logger.warning("IBKR fetch failed for %s: %s", symbol, e)
            return None

    def _fetch_from_yahoo(self, symbol: str) -> MarketData | None:
        """Busca dados do Yahoo Finance (yfinance)."""
        try:
            import yfinance as yf

            ticker = yf.Ticker(symbol)
            info = ticker.info
            history = ticker.history(period="1d")

            if history.empty:
                return None

            last_row = history.iloc[-1]
            last_price = float(last_row["Close"])

            # Calcular mudança
            prev_close = info.get("previousClose")
            if prev_close:
                change = last_price - prev_close
                change_pct = (change / prev_close) * 100 if prev_close != 0 else 0
            else:
                change = None
                change_pct = None

            return MarketData(
                symbol=symbol,
                last_price=last_price,
                bid=info.get("bid"),
                ask=info.get("ask"),
                volume=info.get("volume"),
                avg_daily_volume=info.get("averageVolume"),
                change=change,
                change_pct=change_pct,
                day_high=info.get("dayHigh"),
                day_low=info.get("dayLow"),
                prev_close=prev_close,
                source=DataSource.YAHOO,
            )
        except ImportError:
            logger.warning("yfinance not installed - run: pip install yfinance")
            return None
        except Exception as e:
            logger.warning("Yahoo fetch failed for %s: %s", symbol, e)
            return None

    def get_batch_data(self, symbols: list[str]) -> dict[str, MarketData]:
        """Obtém dados para múltiplos símbolos.

        Returns:
            Dict symbol -> MarketData
        """
        result = {}
        for symbol in symbols:
            data = self.get_data(symbol)
            if data:
                result[symbol] = data
        return result

    def invalidate_cache(self, symbol: str | None = None) -> None:
        """Invalida cache para um símbolo ou todos."""
        if symbol:
            self._cache.pop(symbol, None)
            self._cache_time.pop(symbol, None)
        else:
            self._cache.clear()
            self._cache_time.clear()


def get_market_data_provider(prefer_ibkr: bool = True) -> MarketDataProvider:
    """Retorna instância singleton do MarketDataProvider."""
    # Em produção, seria um singleton global
    return MarketDataProvider(prefer_ibkr=prefer_ibkr)
