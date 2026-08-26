"""OpenBB-powered market scanner — real tickers, real data, no garbage.

Replaces FinanceDatabase's OTC/SPAC/warrant tickers with liquid,
exchange-listed stocks from OpenBB discovery endpoints. Each item
arrives with price, volume, exchange, market_cap, and fundamentals
already populated — no separate DataHub enrichment needed for basics.

OpenBB discovery is free (yfinance provider, no API key).
"""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

try:
    from openbb import obb

    _OPENBB_AVAILABLE = True
except ImportError:
    obb = None  # type: ignore[assignment]
    _OPENBB_AVAILABLE = False

# ── Discovery method by profile ──────────────────────────────────────────
# Maps (country_hint, sector_hint) → discovery method name.
# All methods return US-exchange-listed stocks. Canadian companies trading
# on NYSE/NASDAQ appear naturally in these lists.
_DISCOVERY_METHOD = {
    # Sector-specific
    "technology": "growth_tech",
    "tech": "growth_tech",
    # Style-specific
    "value": "undervalued_large_caps",
    "undervalued": "undervalued_large_caps",
    "growth": "undervalued_growth",
    "small_cap": "aggressive_small_caps",
    "small-cap": "aggressive_small_caps",
    "smallcap": "aggressive_small_caps",
    "penny": "aggressive_small_caps",
    "microcap": "aggressive_small_caps",
    "micro_cap": "aggressive_small_caps",
}
_DEFAULT_DISCOVERY = None  # Bob decides based on context — scanner adapts, not hardcoded


def _pick_discovery(sector: str | None, industry: str | None) -> str:
    """Resolve the best OpenBB discovery method for the given hints."""
    hints = []
    if sector:
        hints.append(sector.strip().lower())
    if industry:
        hints.append(industry.strip().lower())
    for hint in hints:
        for key, method in _DISCOVERY_METHOD.items():
            if key in hint or hint in key:
                return method
    return _DEFAULT_DISCOVERY


# ── Field mapping: OpenBB discovery item → SuperEzio candidate item ──────


def _map_item(r: Any, source_label: str) -> dict[str, Any]:
    """Convert an OpenBB discovery result into a candidate item dict.

    The output schema matches what _run_scan's gate, rank, and enrichment
    stages expect. OpenBB fields that don't exist on the discovery model
    are silently ignored.
    """
    item: dict[str, Any] = {
        "ticker": str(getattr(r, "symbol", "") or "").upper(),
        "source": source_label,
    }

    # ── Price & volume (always present in discovery) ──
    price = getattr(r, "price", None)
    if price is not None:
        item["price"] = float(price)
    volume = getattr(r, "volume", None)
    if volume is not None:
        item["volume"] = int(volume)
    change_pct = getattr(r, "percent_change", None)
    if change_pct is not None:
        item["change_pct"] = float(change_pct)

    # ── Identity ──
    name = getattr(r, "name", None)
    if name:
        item["name"] = str(name)
    exchange = getattr(r, "exchange", None)
    if exchange:
        item["exchange"] = str(exchange)
        # Map exchange to market for downstream compatibility. Codes derive
        # from the td_universe contract (TD specialization 2026-08-23) — no
        # private venue lists in this module.
        from core.trading.td_universe import td_exchange_alias_codes

        _us_exchanges = td_exchange_alias_codes({"NYSE", "NASDAQ", "NYSEAMERICAN", "NYSEARCA"})
        _ca_exchanges = td_exchange_alias_codes({"TSX", "TSXV"})
        _exc = str(exchange).upper()
        if _exc in _us_exchanges:
            item["market"] = "United States"
        elif _exc in _ca_exchanges:
            item["market"] = "Canada"

    # ── Fundamentals ──
    mcap = getattr(r, "market_cap", None)
    if mcap is not None:
        item["market_cap"] = float(mcap)
    book_val = getattr(r, "book_value", None)
    if book_val is not None:
        item["book_value"] = float(book_val)
    pb_ratio = getattr(r, "price_to_book", None)
    if pb_ratio is not None:
        item["price_to_book"] = float(pb_ratio)
    eps_ttm = getattr(r, "eps_ttm", None)
    if eps_ttm is not None:
        item["eps_ttm"] = float(eps_ttm)
    eps_fwd = getattr(r, "eps_forward", None)
    if eps_fwd is not None:
        item["eps_forward"] = float(eps_fwd)
    pe_fwd = getattr(r, "pe_forward", None)
    if pe_fwd is not None:
        item["pe_forward"] = float(pe_fwd)

    # ── Technical context ──
    ma50 = getattr(r, "ma50", None)
    if ma50 is not None:
        item["ma50"] = float(ma50)
    ma200 = getattr(r, "ma200", None)
    if ma200 is not None:
        item["ma200"] = float(ma200)
    y_high = getattr(r, "year_high", None)
    if y_high is not None:
        item["year_high"] = float(y_high)
    y_low = getattr(r, "year_low", None)
    if y_low is not None:
        item["year_low"] = float(y_low)

    # ── Catalyst hint ──
    earnings_date = getattr(r, "earnings_date", None)
    if earnings_date is not None:
        item["earnings_date"] = str(earnings_date)

    # ── Yield ──
    div_yield = getattr(r, "dividend_yield", None)
    if div_yield is not None:
        item["dividend_yield"] = float(div_yield)

    return item


# ── Scanner ──────────────────────────────────────────────────────────────


class OpenBBScanner:
    """Market scanner backed by OpenBB discovery endpoints.

    Provides the same `scan_equities` interface as MarketScanner so
    _run_scan can swap between them without downstream changes.
    """

    CACHE_TTL_S = 60  # discovery is near-real-time; short cache

    def __init__(self) -> None:
        self._cache: dict[str, tuple] = {}  # key → (result, timestamp)

    @property
    def available(self) -> bool:
        return _OPENBB_AVAILABLE

    def _cached(self, key: str) -> list[dict[str, Any]] | None:
        if key in self._cache:
            result, ts = self._cache[key]
            if time.time() - ts < self.CACHE_TTL_S:
                return result
            del self._cache[key]
        return None

    def _cache_set(self, key: str, value: list[dict[str, Any]]) -> None:
        self._cache[key] = (value, time.time())

    def scan_equities(
        self,
        country: str | None = None,
        sector: str | None = None,
        industry: str | None = None,
        limit: int = 12,
        max_price: float | None = None,
    ) -> list[dict[str, Any]]:
        """Return enriched candidate items from OpenBB discovery.

        Each item includes ticker, price, volume, exchange, market_cap,
        and fundamentals — ready for the candidate gate without requiring
        immediate DataHub enrichment.

        Args:
            max_price: Filter by max price (e.g., 5.0 for penny stocks).
        """
        if not _OPENBB_AVAILABLE:
            logger.warning("OpenBB not installed — scanner unavailable")
            return []

        method = _pick_discovery(sector, industry)
        # Adaptive fallback: try hinted method first, then small caps, then active
        fallback_chain = [
            m for m in [method, "aggressive_small_caps", "undervalued_growth", "active"] if m
        ]

        result = None
        for attempt in fallback_chain:
            cache_key = f"obb:{attempt}:{limit}:{max_price or 'all'}"
            cached = self._cached(cache_key)
            if cached is not None:
                return cached

            try:
                discover_fn = getattr(obb.equity.discovery, attempt, None)
                if discover_fn is None:
                    continue
                result = discover_fn(provider="yfinance")
                if result is not None and hasattr(result, "results") and result.results:
                    method = attempt  # use the one that worked
                    break
            except Exception as exc:
                logger.debug("OpenBB: discovery %s failed, trying fallback: %s", attempt, exc)
                continue

        if result is None or not hasattr(result, "results"):
            logger.warning("OpenBB: all discovery methods exhausted, no results")
            return []

        items: list[dict[str, Any]] = []
        source_label = f"openbb:{method}"
        for r in result.results:
            item = _map_item(r, source_label)
            ticker = item.get("ticker")
            if not ticker:
                continue

            # Price filter (penny stocks)
            if max_price is not None:
                price = item.get("price")
                if price is None or price > max_price:
                    continue

            items.append(item)
            if len(items) >= limit:
                break

        self._cache_set(cache_key, items)
        return items

    def scan_etfs(self, category: str | None = None, limit: int = 10) -> list[str]:
        """ETF scan — not implemented via OpenBB discovery (use MarketScanner)."""
        return []
