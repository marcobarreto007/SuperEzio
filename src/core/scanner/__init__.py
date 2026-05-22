import re
import time
from typing import Dict, List

import financedatabase as fd

# Hard US/CA ticker whitelist — no config toggle, no env var.
# FinanceDatabase returns garbage exchange suffixes (-F, -BE, -SG, -MU, -HM, ...)
# even when filtering by "United States". These suffixes map to Frankfurt, Berlin,
# Singapore, Munich, Hamburg and other venues whose tickers Yahoo/Finnhub can't
# price. The whitelist rejects everything except legitimate US and Canadian
# exchange symbols.
_US_TICKER_RE = re.compile(r"^[A-Z]{1,5}([.-][A-Z])?$")
_CA_TICKER_RE = re.compile(r"^[A-Z]{1,5}\.(TO|V)$")


def _is_valid_us_ca_ticker(symbol: str) -> bool:
    """Return True only for US (NYSE/NASDAQ) and Canadian (TSX/TSX-V) tickers."""
    s = symbol.strip().upper()
    return bool(_US_TICKER_RE.match(s) or _CA_TICKER_RE.match(s))

try:
    from ..observability.neural_log import log_event as _log_event
except Exception:

    def _log_event(phase, event, data=None):  # type: ignore[misc]
        pass


class MarketScanner:
    """
    Wrapper para o FinanceDatabase (JerBouma) para escanear o mercado.
    Permite encontrar tickers baseados em setor, pais, industria, etc.
    Cache de consultas com TTL para evitar reprocessar a base inteira.
    """

    CACHE_TTL_S = 3600  # 1 hora

    def __init__(self):
        _log_event("SCANNER", "INIT", {"mode": "lazy_load"})
        self._equities = None
        self._etfs = None
        self._cache: Dict[str, tuple] = {}  # key -> (result, timestamp)

    @property
    def equities(self):
        if self._equities is None:
            _log_event("SCANNER", "LOADING", {"source": "equities"})
            self._equities = fd.Equities()
        return self._equities

    @property
    def etfs(self):
        if self._etfs is None:
            _log_event("SCANNER", "LOADING", {"source": "etfs"})
            self._etfs = fd.ETFs()
        return self._etfs

    def _get_cached(self, key: str):
        """Retorna valor do cache se ainda valido, senao None."""
        if key in self._cache:
            result, ts = self._cache[key]
            if time.time() - ts < self.CACHE_TTL_S:
                return result
            del self._cache[key]
        return None

    def _set_cached(self, key: str, value):
        """Salva resultado no cache."""
        self._cache[key] = (value, time.time())

    def scan_equities(
        self,
        country: str = None,
        sector: str = None,
        industry: str = None,
        limit: int = 10,
    ) -> List[str]:
        """Retorna lista de tickers de acoes baseados nos criterios."""
        cache_key = f"eq:{country}:{sector}:{industry}:{limit}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        try:
            kwargs = {}
            if country:
                kwargs["country"] = country
            if sector:
                kwargs["sector"] = sector
            if industry:
                kwargs["industry"] = industry

            selection = self.equities.select(**kwargs)

            if selection is None or selection.empty:
                return []

            tickers = [t for t in selection.index if _is_valid_us_ca_ticker(str(t))]
            result = tickers[:limit]
            self._set_cached(cache_key, result)
            return result

        except Exception as e:
            _log_event("SCANNER", "SCAN_ERROR", {"type": "equities", "error": str(e)})
            return []

    def scan_etfs(self, category: str = None, limit: int = 10) -> List[str]:
        """Retorna lista de tickers de ETFs."""
        cache_key = f"etf:{category}:{limit}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        try:
            selection = self.etfs.select(category=category)
            if selection is None or selection.empty:
                return []
            result = list(selection.index)[:limit]
            self._set_cached(cache_key, result)
            return result
        except Exception as e:
            _log_event("SCANNER", "SCAN_ERROR", {"type": "etfs", "error": str(e)})
            return []

    def get_available_sectors(self) -> List[str]:
        try:
            return sorted(self.equities.data["sector"].dropna().unique().tolist())
        except Exception:
            return []

    def get_available_countries(self) -> List[str]:
        try:
            return sorted(self.equities.data["country"].dropna().unique().tolist())
        except Exception:
            return []
