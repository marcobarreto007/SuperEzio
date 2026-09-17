"""Nasdaq Traded snapshot lines → ListingRow."""

from __future__ import annotations

import csv
from datetime import date
from io import StringIO

from core.heart.universe import IngestResult, ListingRow, UniverseRegistry, listing_exchange_to_mic


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


def ingest_nasdaqtraded_text(
    registry: UniverseRegistry,
    text: str,
    as_of: date,
) -> IngestResult:
    rows = parse_nasdaqtraded_lines(text)
    if not rows:
        return registry.ingest_snapshot(
            [],
            as_of=as_of,
            snapshot_ok=False,
            source="nasdaqtraded",
        )
    return registry.ingest_snapshot(
        rows,
        as_of=as_of,
        snapshot_ok=True,
    )
