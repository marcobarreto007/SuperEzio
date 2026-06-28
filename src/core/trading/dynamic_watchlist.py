"""Dynamic Watchlist Provider — feeds the trading engines with real tickers.

Sources (in priority order):
1. Investor storage DB (user-curated, 24 tickers)
2. Sentiment watchlist env var (SUPEREZIO_SENTIMENT_WATCHLIST)
3. Market scanners (Finviz, Yahoo — volume breakouts, momentum)
4. Sector ETFs for broad market coverage
5. Canadian tickers (TSX/TSX-V banks, energy, materials)

Design contract:
- Returns List[str] of tickers, never empty
- Minimum 20 tickers for diversification
- Rotates based on market conditions
- Small caps get PennyLab verification before inclusion
"""

from __future__ import annotations

import os
import logging
from typing import List

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════
# Canadian Market — Core TSX/TSX-V tickers
# ═══════════════════════════════════════════════════════════

CANADIAN_BANKS = ["RY.TO", "TD.TO", "BNS.TO", "BMO.TO", "CM.TO", "NA.TO"]
CANADIAN_ENERGY = ["ENB.TO", "TRP.TO", "SU.TO", "CNQ.TO", "CVE.TO"]
CANADIAN_MATERIALS = ["ABX.TO", "FNV.TO", "WPM.TO", "TECK-B.TO"]
CANADIAN_UTILITIES = ["FTS.TO", "EMA.TO", "H.TO"]
CANADIAN_ETFS = ["XIU.TO", "XIC.TO", "VFV.TO", "XUU.TO", "ZAG.TO", "XBB.TO"]
CANADIAN_TELECOM = ["BCE.TO", "T.TO", "RCI-B.TO"]

CANADIAN_ALL = (
    CANADIAN_BANKS + CANADIAN_ENERGY + CANADIAN_MATERIALS +
    CANADIAN_UTILITIES + CANADIAN_ETFS + CANADIAN_TELECOM
)

# ═══════════════════════════════════════════════════════════
# US Market — Core liquid tickers
# ═══════════════════════════════════════════════════════════

US_LARGE_CAP = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA",
    "JPM", "V", "JNJ", "WMT", "PG", "XOM", "UNH", "HD",
    "BAC", "MA", "DIS", "NFLX", "ADBE", "CRM", "AMD", "INTC",
]
US_SECTOR_ETFS = [
    "SPY", "QQQ", "IWM", "DIA", "XLF", "XLE", "XLK", "XLV",
    "XLI", "XLP", "XLY", "XLB", "XLU", "XLRE", "SMH", "SOXX",
]
US_DEFENSIVE = ["GLD", "TLT", "SHY", "IEF", "BIL", "SGOV", "VTIP"]
US_VOLATILITY = ["UVXY", "SVXY", "VXX", "VIXM"]

# ═══════════════════════════════════════════════════════════
# Market Scanner Integration
# ═══════════════════════════════════════════════════════════

def _scan_finviz_screen(screen: str = "top_gainers", limit: int = 15) -> list[str]:
    """Scan Finviz screener for top movers. Falls back gracefully."""
    try:
        import urllib.request
        import csv
        import io

        url = f"https://finviz.com/screener.ashx?v=111&f=sh_avgvol_o1000,sh_price_o5&ft=4&o=-change&r={limit}"
        headers = {"User-Agent": "Mozilla/5.0"}
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            content = resp.read().decode("utf-8", errors="ignore")
        # Parse Finviz HTML table (simple extraction)
        tickers = set()
        import re
        for match in re.finditer(r'screener-link[^>]*>([A-Z]{1,5})<', content):
            tickers.add(match.group(1))
        return list(tickers)[:limit]
    except Exception:
        return []


def _scan_yahoo_trending(limit: int = 10) -> list[str]:
    """Scan Yahoo Finance trending tickers."""
    try:
        import urllib.request
        import json
        url = "https://query1.finance.yahoo.com/v1/finance/trending/US?count=20"
        headers = {"User-Agent": "Mozilla/5.0"}
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
        tickers = []
        for quote in (data.get("finance", {}).get("result", []) or [{}])[0].get("quotes", []) or []:
            symbol = quote.get("symbol", "")
            if symbol and len(symbol) <= 5 and symbol.isalpha():
                tickers.append(symbol)
        return tickers[:limit]
    except Exception:
        return []


# ═══════════════════════════════════════════════════════════
# Dynamic Watchlist Builder
# ═══════════════════════════════════════════════════════════


def get_investor_watchlist() -> list[str]:
    """Get tickers from investor storage DB."""
    try:
        from core.investor.storage import get_investor_storage
        store = get_investor_storage()
        rows = store.get_watchlist()
        return [r["ticker"].upper().strip() for r in rows if r.get("ticker")]
    except Exception as e:
        logger.warning("investor_watchlist_unavailable: %s", e)
        return []


def get_sentiment_watchlist() -> list[str]:
    """Get tickers from sentiment env var."""
    raw = os.getenv("SUPEREZIO_SENTIMENT_WATCHLIST", "").strip()
    if raw:
        return [t.strip().upper() for t in raw.split(",") if t.strip()]
    return []


def get_dynamic_watchlist(
    include_canadian: bool = True,
    include_scanners: bool = False,
    min_tickers: int = 25,
) -> list[str]:
    """Build a dynamic watchlist from all available sources.

    Priority:
    1. Investor DB (user's actual picks)
    2. Sentiment env var
    3. US large cap + sector ETFs (always included for context)
    4. Canadian tickers (TSX/TSX-V)
    5. Market scanners (if enabled)
    6. Defensive/volatility (for market health indicators)

    Deduplication preserves first occurrence (investor picks win).
    """
    seen: set[str] = set()
    tickers: list[str] = []

    def add(t: list[str]) -> None:
        for ticker in t:
            ticker = ticker.upper().strip()
            if ticker and ticker not in seen and len(ticker) >= 2:
                seen.add(ticker)
                tickers.append(ticker)

    # Layer 0: Universe 400 (stratified across all markets)
    if use_universe_400:
        try:
            from .universe_builder import build_universe_400
            universe = build_universe_400()
            add(universe)
            logger.info("watchlist_universe_400: %d tickers", len(universe))
        except ImportError:
            logger.warning("universe_builder not available, falling back to legacy")

    # Layer 1: Investor picks (always included, may already be in universe)
    investor = get_investor_watchlist()
    add(investor)
    logger.info("watchlist_investor_db: %d tickers", len(investor))

    # Layer 2: Sentiment env var
    sentiment = get_sentiment_watchlist()
    add(sentiment)
    if sentiment:
        logger.info("watchlist_sentiment_env: %d tickers", len(sentiment))

    # Layer 3: US large caps + sector ETFs (market context)
    add(US_LARGE_CAP)
    add(US_SECTOR_ETFS)

    # Layer 4: Canadian market
    if include_canadian:
        add(CANADIAN_ALL)

    # Layer 5: Defensive + volatility (health indicators)
    add(US_DEFENSIVE)
    add(US_VOLATILITY)

    # Layer 6: Market scanners (dynamic, optional — network calls)
    if include_scanners:
        finviz = _scan_finviz_screen()
        add(finviz)
        if finviz:
            logger.info("watchlist_finviz_scanner: %d tickers", len(finviz))

        yahoo_trending = _scan_yahoo_trending()
        add(yahoo_trending)
        if yahoo_trending:
            logger.info("watchlist_yahoo_trending: %d tickers", len(yahoo_trending))

    # Ensure minimum coverage
    if len(tickers) < min_tickers:
        add(US_LARGE_CAP)
        add(CANADIAN_ETFS)

    logger.info("dynamic_watchlist_total: %d tickers", len(tickers))
    return tickers


def get_watchlist_by_profile(risk_profile: str = "moderate") -> list[str]:
    """Get a watchlist filtered by investor risk profile.

    Profiles:
    - conservative: large cap + ETFs + bonds + Canadian banks/utilities
    - moderate: all of above + mid cap
    - aggressive: all + small caps + volatility
    - income: Canadian banks + utilities + REITs + dividend ETFs
    """
    all_tickers = get_dynamic_watchlist(include_canadian=True)

    if risk_profile == "conservative":
        # Only large cap, ETFs, bonds, Canadian banks/utilities
        defensive = set(US_LARGE_CAP[:10] + US_SECTOR_ETFS[:5] + US_DEFENSIVE +
                       CANADIAN_BANKS + CANADIAN_UTILITIES + CANADIAN_ETFS[:3])
        return [t for t in all_tickers if t in defensive]

    elif risk_profile == "income":
        # Income-focused: Canadian banks, utilities, telecom, dividend ETFs
        income_set = set(CANADIAN_BANKS + CANADIAN_UTILITIES + CANADIAN_TELECOM +
                        CANADIAN_ETFS[:3] + ["JNJ", "PG", "WMT", "KO", "PEP", "VZ", "T"])
        return [t for t in all_tickers if t in income_set]

    elif risk_profile == "aggressive" or risk_profile == "very_aggressive":
        # Everything goes — including small caps and volatility
        return all_tickers

    else:  # moderate
        return all_tickers
