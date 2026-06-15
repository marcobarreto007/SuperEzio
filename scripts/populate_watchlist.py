#!/usr/bin/env python
"""
Popula investor_watchlist com tickers populares para sentiment monitor.
"""

from pathlib import Path
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from core.investor.storage import get_investor_storage

# Tickers populares para demo
TICKERS = [
    ("AAPL", "Apple — tech leader"),
    ("MSFT", "Microsoft — cloud/AI"),
    ("GOOGL", "Alphabet — search/ads"),
    ("AMZN", "Amazon — e-commerce/cloud"),
    ("TSLA", "Tesla — EV/energy"),
    ("NVDA", "NVIDIA — semiconductors/AI"),
    ("TLRY", "Tilray — cannabis"),
    ("META", "Meta — social/VR"),
    ("BTC-USD", "Bitcoin — crypto"),
]

def main() -> None:
    storage = get_investor_storage()

    # Verificar watchlist atual
    current = storage.get_watchlist()
    print(f"Watchlist atual: {len(current)} tickers")
    for t in current:
        print(f"  - {t['ticker']}: {t['notes']}")

    # Adicionar tickers
    added = 0
    for ticker, notes in TICKERS:
        # Verificar se já existe
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
    for t in final:
        print(f"  - {t['ticker']}: {t['notes']}")

if __name__ == "__main__":
    main()
