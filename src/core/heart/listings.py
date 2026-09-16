"""Nasdaq Traded snapshot lines → ListingRow."""

from __future__ import annotations

import csv
from io import StringIO

from core.heart.universe import ListingRow, listing_exchange_to_mic


def parse_nasdaqtraded_lines(text: str) -> list[ListingRow]:
    rows: list[ListingRow] = []
    reader = csv.DictReader(StringIO(text), delimiter="|")
    for row in reader:
        if (row.get("Nasdaq Traded") or "").strip() != "Y":
            continue
        if (row.get("Test Issue") or "").strip() == "Y":
            continue
        exchange = (row.get("Listing Exchange") or "").strip()
        rows.append(
            ListingRow(
                mic_code=listing_exchange_to_mic(exchange),
                symbol=(row.get("Symbol") or "").strip(),
                name=(row.get("Security Name") or "").strip(),
                exchange=exchange,
                source="nasdaqtraded",
                is_etf=(row.get("ETF") or "").strip() == "Y",
                is_test=False,
            )
        )
    return rows
