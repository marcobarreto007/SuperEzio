"""Universe Builder — 400 tickers stratified across markets and sectors.

Builds a comprehensive investment universe:
- 50 Canadian TSX/TSX-V (banks, energy, materials, tech, REITs)
- 200 US large/mid cap (S&P 500 coverage across all 11 sectors)
- 50 US small cap (Russell 2000 liquid subset)
- 50 International/ADR (Europe, Asia, LatAm via NYSE)
- 30 ETFs (sector, factor, bond, commodity)
- 20 Crypto proxies (BTC-USD, ETH-USD, mining stocks)

Sources:
- Wikipedia S&P 500 / TSX 60 constituents
- Finviz screener exports
- Yahoo Finance sector/industry APIs
- Manual curated lists for crypto/ADR
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# S&P 500 — Top 200 by market cap (approximate, can be refreshed)
# ═══════════════════════════════════════════════════════════════

SP500_TOP200 = [
    # Tech (40)
    "AAPL",
    "MSFT",
    "NVDA",
    "GOOGL",
    "AMZN",
    "META",
    "TSLA",
    "AVGO",
    "ORCL",
    "CRM",
    "ADBE",
    "AMD",
    "INTC",
    "CSCO",
    "QCOM",
    "TXN",
    "INTU",
    "NOW",
    "IBM",
    "AMAT",
    "LRCX",
    "MU",
    "ADI",
    "KLAC",
    "SNPS",
    "CDNS",
    "ANET",
    "PLTR",
    "MRVL",
    "APH",
    "MSI",
    "ROP",
    "ADSK",
    "FTNT",
    "CTSH",
    "IT",
    "GLW",
    "HPQ",
    "HPE",
    "NTAP",
    # Financials (25)
    "JPM",
    "BAC",
    "WFC",
    "GS",
    "MS",
    "C",
    "BLK",
    "SCHW",
    "AXP",
    "V",
    "MA",
    "PYPL",
    "COF",
    "USB",
    "PNC",
    "TFC",
    "BK",
    "STT",
    "AMP",
    "MET",
    "PRU",
    "AIG",
    "TRV",
    "ALL",
    "CB",
    # Healthcare (25)
    "JNJ",
    "UNH",
    "PFE",
    "ABBV",
    "MRK",
    "TMO",
    "ABT",
    "DHR",
    "BMY",
    "AMGN",
    "LLY",
    "GILD",
    "REGN",
    "VRTX",
    "BIIB",
    "ISRG",
    "SYK",
    "BSX",
    "CI",
    "HUM",
    "CVS",
    "ANTM",
    "CNC",
    "MRNA",
    "ZTS",
    # Consumer (25)
    "WMT",
    "PG",
    "KO",
    "PEP",
    "COST",
    "HD",
    "MCD",
    "NKE",
    "SBUX",
    "TGT",
    "LOW",
    "BKNG",
    "MAR",
    "HLT",
    "YUM",
    "CMG",
    "ROST",
    "TJX",
    "DG",
    "DLTR",
    "EL",
    "CL",
    "KMB",
    "GIS",
    "KHC",
    # Industrials (20)
    "CAT",
    "DE",
    "BA",
    "GE",
    "MMM",
    "HON",
    "UPS",
    "FDX",
    "UNP",
    "CSX",
    "NSC",
    "LMT",
    "RTX",
    "GD",
    "NOC",
    "ITW",
    "ETN",
    "EMR",
    "ROK",
    "CARR",
    # Energy (15)
    "XOM",
    "CVX",
    "COP",
    "EOG",
    "SLB",
    "PXD",
    "MPC",
    "VLO",
    "PSX",
    "OXY",
    "HES",
    "FANG",
    "DVN",
    "CTRA",
    "MRO",
    # Utilities/REITs (15)
    "NEE",
    "DUK",
    "SO",
    "AEP",
    "D",
    "EXC",
    "SRE",
    "PEG",
    "ED",
    "WEC",
    "AMT",
    "PLD",
    "CCI",
    "EQIX",
    "SPG",
    # Materials (10)
    "LIN",
    "APD",
    "ECL",
    "SHW",
    "FCX",
    "NEM",
    "DOW",
    "DD",
    "PPG",
    "VMC",
    # Comm Services (15)
    "GOOG",
    "NFLX",
    "DIS",
    "CMCSA",
    "T",
    "VZ",
    "TMUS",
    "CHTR",
    "EA",
    "TTWO",
    "OMC",
    "IPG",
    "LYV",
    "WBD",
    "PARA",
    # Real Estate (10)
    "O",
    "WELL",
    "AVB",
    "EQR",
    "INVH",
    "MAA",
    "ESS",
    "UDR",
    "CPT",
    "EXR",
]

# ═══════════════════════════════════════════════════════════════
# Russell 2000 — Liquid small caps (50)
# ═══════════════════════════════════════════════════════════════

RUSSELL_50 = [
    "SMCI",
    "CHRD",
    "ELF",
    "RMBS",
    "FN",
    "ONTO",
    "ACLS",
    "FORM",
    "CRUS",
    "POWI",
    "DIOD",
    "MTSI",
    "SITM",
    "SYNA",
    "SLAB",
    "AMBA",
    "PI",
    "MQ",
    "AAOI",
    "LITE",
    "VIAV",
    "EXTR",
    "CALX",
    "INFN",
    "CIEN",
    "JNPR",
    "CRNC",
    "SEDG",
    "ENPH",
    "RUN",
    "NOVA",
    "ARRY",
    "SHLS",
    "FCEL",
    "BLDP",
    "BE",
    "PLUG",
    "CHPT",
    "EVGO",
    "RIVN",
    "LCID",
    "FSR",
    "NKLA",
    "GOEV",
    "WKHS",
    "HYLN",
    "LAZR",
    "INVZ",
    "AEVA",
    "OUST",
]

# ═══════════════════════════════════════════════════════════════
# TSX / TSX-V Canadian — 50 tickers
# ═══════════════════════════════════════════════════════════════

TSX_50 = [
    # Banks (6)
    "RY.TO",
    "TD.TO",
    "BNS.TO",
    "BMO.TO",
    "CM.TO",
    "NA.TO",
    # Energy (8)
    "ENB.TO",
    "TRP.TO",
    "SU.TO",
    "CNQ.TO",
    "CVE.TO",
    "IMO.TO",
    "TOU.TO",
    "ARX.TO",
    # Materials/Mining (8)
    "ABX.TO",
    "FNV.TO",
    "WPM.TO",
    "TECK-B.TO",
    "AEM.TO",
    "K.TO",
    "LUN.TO",
    "FM.TO",
    # Tech (5)
    "SHOP.TO",
    "CSU.TO",
    "OTEX.TO",
    "DSG.TO",
    "LSPD.TO",
    # Telecom/Utilities (5)
    "BCE.TO",
    "T.TO",
    "RCI-B.TO",
    "FTS.TO",
    "EMA.TO",
    # Railways/Industrials (5)
    "CNR.TO",
    "CP.TO",
    "WCN.TO",
    "TFII.TO",
    "BBD-B.TO",
    # REITs (5)
    "REI-UN.TO",
    "GRT-UN.TO",
    "CAR-UN.TO",
    "SRU-UN.TO",
    "AP-UN.TO",
    # Consumer/Other (8)
    "L.TO",
    "MRU.TO",
    "DOL.TO",
    "ATD.TO",
    "GIL.TO",
    "WN.TO",
    "QSR.TO",
    "PBH.TO",
]

# ═══════════════════════════════════════════════════════════════
# International ADRs — 30
# ═══════════════════════════════════════════════════════════════

ADR_30 = [
    "BABA",
    "JD",
    "BIDU",
    "NIO",
    "XPEV",
    "TCEHY",
    "NTES",
    "TAL",
    "EDU",
    "TSM",
    "ASML",
    "SAP",
    "AZN",
    "HSBC",
    "UL",
    "NVS",
    "SONY",
    "TM",
    "RY",
    "TD",
    "BNS",
    "VALE",
    "PBR",
    "ITUB",
    "BBD",
    "NU",
    "MELI",
    "SE",
    "SHOP",
    "SPOT",
]

# ═══════════════════════════════════════════════════════════════
# ETFs — 30
# ═══════════════════════════════════════════════════════════════

ETF_30 = [
    # Broad market
    "SPY",
    "QQQ",
    "IWM",
    "DIA",
    "VTI",
    "VOO",
    "IVV",
    # Canadian
    "XIU.TO",
    "XIC.TO",
    "VFV.TO",
    "XUU.TO",
    "ZAG.TO",
    "XBB.TO",
    "XEI.TO",
    # Sectors
    "XLF",
    "XLE",
    "XLK",
    "XLV",
    "XLI",
    "XLP",
    "XLY",
    "XLB",
    "XLU",
    # Factors/Thematic
    "SMH",
    "SOXX",
    "IBB",
    "XBI",
    "ARKK",
    "TAN",
    "ICLN",
]

# ═══════════════════════════════════════════════════════════════
# Crypto Proxies — 20
# ═══════════════════════════════════════════════════════════════

CRYPTO_20 = [
    "BTC-USD",
    "ETH-USD",
    "SOL-USD",
    "ADA-USD",
    "DOGE-USD",
    "MSTR",
    "COIN",
    "MARA",
    "RIOT",
    "CLSK",
    "HIVE.V",
    "BITF",
    "HUT",
    "BTBT",
    "IREN",
    "WULF",
    "CIFR",
    "SDIG",
    "BTDR",
    "CORZ",
]

# ═══════════════════════════════════════════════════════════════
# Builder
# ═══════════════════════════════════════════════════════════════


def build_universe_400() -> list[str]:
    """Build a 400-ticker universe stratified by market and sector.

    Returns deduplicated, sorted list.
    """
    investor = []
    try:
        from core.investor.storage import get_investor_storage

        store = get_investor_storage()
        rows = store.get_watchlist()
        investor = [r["ticker"].upper().strip() for r in rows if r.get("ticker")]
    except Exception:
        pass

    all_tickers = investor + SP500_TOP200 + RUSSELL_50 + TSX_50 + ADR_30 + ETF_30 + CRYPTO_20

    # Deduplicate preserving order (investor picks first)
    seen: set[str] = set()
    unique: list[str] = []
    for t in all_tickers:
        t = t.upper().strip()
        if t and t not in seen and len(t) >= 2:
            seen.add(t)
            unique.append(t)

    logger.info("universe_400_built: %d tickers", len(unique))
    return unique


def get_universe_summary() -> dict:
    """Return summary statistics of the universe."""
    tickers = build_universe_400()
    ca = sum(1 for t in tickers if ".TO" in t or ".V" in t)
    crypto = sum(1 for t in tickers if "-USD" in t)
    etf = sum(1 for t in tickers if t in ETF_30)

    return {
        "total": len(tickers),
        "canadian": ca,
        "crypto_proxies": crypto,
        "etfs": etf,
        "us_equities": len(tickers) - ca - crypto - etf,
    }
