"""NYSE trade-halts CSV download + EventBook ingest."""

from __future__ import annotations

import httpx

from core.heart.event_book import EventBook
from core.heart.http import request
from core.heart.nyse_halts import parse_nyse_halts_csv

NYSE_HALTS_URL = "https://www.nyse.com/api/trade-halts/historical/download"


def fetch_halts_csv(client: httpx.Client) -> str:
    response = request(client, NYSE_HALTS_URL)
    return response.body.decode("utf-8")


def ingest_halts_csv(text: str, book: EventBook) -> int:
    return book.ingest_many(parse_nyse_halts_csv(text))
