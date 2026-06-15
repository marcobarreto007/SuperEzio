#!/usr/bin/env python
"""
Popula watchlist com 15 small/nano caps com potencial para treinamento do Bob.
Pesquisa realizada em 2026-06-15.
"""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from core.investor.storage import get_investor_storage

# 15 small/nano caps com market cap baixo e catalysts identificados
SMALL_CAPS = [
    # === AI/Tech Infrastructure ===
    ("AEHR", "Aehr Test Systems — semiconductor testing for AI/quantum chips"),
    ("PLAB", "Photronics — photomasks for AI/quantum semiconductors"),
    ("SKYT", "SkyWater Technology — specialized semiconductor manufacturing"),

    # === Biotech/Pharma ===
    ("SIGA", "SIGA Technologies — smallpox/monkeypox antiviral (TPOXX)"),
    ("NEPH", "NephroSense — kidney disease diagnostic technology"),
    ("PDSB", "PDS Biotechnology — cancer immunotherapy"),
    ("IMRX", "Immuneering — precision oncology platforms"),
    ("NUVB", "Nuvation Bio — precision oncology therapies"),

    # === Finance/Insurance ===
    ("FINV", "FinVolution — fintech lending platform"),
    ("III", "Hamilton Insurance — insurance technology"),
    ("LX", "LexinFintech — digital lending"),

    # === Energy/Clean Tech ===
    ("BNRG", "Brenmiller Energy — thermal energy storage (nano cap ~$3M)"),
    ("INOD", "Innodata — AI data solutions for ESG/finance"),

    # === E-commerce/Marketplace ===
    ("DIBS", "1stdibs — luxury marketplace"),
    ("USIO", "Univest — semiconductor IP and solutions"),
]

def main() -> None:
    storage = get_investor_storage()

    # Verificar watchlist atual
    current = storage.get_watchlist()
    print(f"Watchlist atual: {len(current)} tickers")

    # Adicionar small caps
    added = 0
    for ticker, notes in SMALL_CAPS:
        exists = any(t["ticker"] == ticker for t in current)
        if exists:
            print(f"  [SKIP] {ticker} já existe")
            continue
        storage.add_to_watchlist(ticker, notes)
        added += 1
        print(f"  [ADD] {ticker}: {notes}")

    # Verificar resultado
    final = storage.get_watchlist()
    print(f"\nWatchlist final: {len(final)} tickers")

    # Resumo por setor
    sectors = {
        "AI/Tech": ["AEHR", "PLAB", "SKYT", "INOD", "USIO"],
        "Biotech/Pharma": ["SIGA", "NEPH", "PDSB", "IMRX", "NUVB"],
        "Finance/Insurance": ["FINV", "III", "LX"],
        "Energy": ["BNRG"],
        "Marketplace": ["DIBS"],
    }

    print("\nResumo por setor:")
    for sector, tickers in sectors.items():
        in_watchlist = [t for t in tickers if any(w["ticker"] == t for w in final)]
        print(f"  {sector}: {len(in_watchlist)} tickers")

if __name__ == "__main__":
    main()
