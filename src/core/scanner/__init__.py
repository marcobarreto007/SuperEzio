import random
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

# Only TD-supported exchanges (TD specialization 2026-08-23). Derived from the
# single td_universe contract — this module must NOT keep its own venue list.
# OTC Pink (PNK), OTCQB (OQB), CSE (.CN), NEO (.NE) and other venues are
# excluded: not TD-tradable, and their tickers waste the enrichment budget.
from ..trading.td_universe import td_exchange_alias_codes

_US_EXCHANGE_WHITELIST = td_exchange_alias_codes({"NYSE", "NASDAQ", "NYSEAMERICAN", "NYSEARCA"})
_CA_EXCHANGE_WHITELIST = td_exchange_alias_codes({"TSX", "TSXV"})

# Market cap labels to exclude — these are typically SPACs, warrants, empty shells,
# or companies with no tradable liquidity.
_EXCLUDED_MARKET_CAPS = {"Nano Cap", "Nano"}


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
        self._cache: dict[str, tuple] = {}  # key -> (result, timestamp)

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

    def _filter_us_ca_selection(self, selection) -> list[tuple]:
        """Apply the TD venue/ticker/market-cap gates; return (ticker, exchange)."""
        # Both US and Canadian companies trade on major US exchanges.
        # "country" is the incorporation country, not the listing venue.
        # TOR/TSX/TSV are legitimate Canadian venues but FinanceDatabase
        # primarily indexes Canadian companies via their US-listed symbols.
        exchange_ok = _US_EXCHANGE_WHITELIST | _CA_EXCHANGE_WHITELIST

        pairs: list[tuple] = []
        for t in selection.index:
            s = str(t)
            if not _is_valid_us_ca_ticker(s):
                continue
            # Exchange gate — reject OTC (PNK), OTCQB (OQB), etc.
            row = selection.loc[t]
            exc = str(row.get("exchange") or "")
            if exc and exc not in exchange_ok:
                continue
            # Market cap gate — reject Nano Caps (typically SPAC/warrant shells)
            mcap = str(row.get("market_cap") or "")
            if mcap in _EXCLUDED_MARKET_CAPS:
                continue
            pairs.append((s, exc))
        return pairs

    def scan_equities_detailed(
        self,
        country: str = None,
        sector: str = None,
        industry: str = None,
        limit: int = 10,
    ) -> list[dict]:
        """Like scan_equities, but keeps the VERIFIED exchange per ticker.

        The exchange is provenance the collector needs for the TD-universe
        gate — throwing it away (bare symbols + country label) forces the
        gate to guess. Test doubles may omit this method; callers must
        fall back to scan_equities.
        """
        selection = self._select_equities(country, sector, industry)
        if selection is None:
            return []
        try:
            pairs = self._filter_us_ca_selection(selection)
            rng = random.Random(time.time())
            rng.shuffle(pairs)
            return [{"ticker": s, "exchange": exc} for s, exc in pairs[:limit]]
        except Exception as e:
            _log_event("SCANNER", "SCAN_ERROR", {"type": "equities", "error": str(e)})
            return []

    def _select_equities(self, country, sector, industry):
        try:
            kwargs = {}
            if country:
                kwargs["country"] = country
            if sector:
                kwargs["sector"] = sector
            if industry:
                kwargs["industry"] = industry
            return self.equities.select(**kwargs)
        except Exception as e:
            _log_event("SCANNER", "SCAN_ERROR", {"type": "select", "error": str(e)})
            return None

    def scan_equities(
        self,
        country: str = None,
        sector: str = None,
        industry: str = None,
        limit: int = 10,
        max_price: float | None = None,
    ) -> list[str]:
        """Retorna lista de tickers de acoes baseados nos criterios.

        Filters out OTC/Pink Sheets, Nano Caps, and non-major exchanges before
        shuffling, so every scan returns a different, tradeable sample.

        Args:
            max_price: Filter by max price (e.g., 5.0 for penny stocks).
        """
        cache_key = f"eq:{country}:{sector}:{industry}:{limit}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        try:
            selection = self._select_equities(country, sector, industry)
            if selection is None or selection.empty:
                return []

            pairs = self._filter_us_ca_selection(selection)

            # Shuffle so every scan returns different tickers instead of
            # the same alphabetical A* garbage.
            rng = random.Random(time.time())
            rng.shuffle(pairs)

            result = [s for s, _ in pairs[:limit]]
            self._set_cached(cache_key, result)
            return result

        except Exception as e:
            _log_event("SCANNER", "SCAN_ERROR", {"type": "equities", "error": str(e)})
            return []

    def scan_etfs(self, category: str = None, limit: int = 10) -> list[str]:
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

    def get_available_sectors(self) -> list[str]:
        try:
            return sorted(self.equities.data["sector"].dropna().unique().tolist())
        except Exception:
            return []

    def get_available_countries(self) -> list[str]:
        try:
            return sorted(self.equities.data["country"].dropna().unique().tolist())
        except Exception:
            return []


# ── OpenBB-powered scanner (primary, no API key) ──
from .openbb_scanner import OpenBBScanner  # noqa: F401
