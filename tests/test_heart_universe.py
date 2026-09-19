"""Peça 1a: identidade de símbolo. Ticker sozinho nunca é chave."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from core.heart.universe import (
    DEFAULT_UNIVERSE_PATH,
    ListingRow,
    UniverseRegistry,
    listing_exchange_to_mic,
)
from core.paths import project_path


@pytest.fixture
def registry(tmp_path: Path) -> UniverseRegistry:
    return UniverseRegistry(tmp_path / "universe.sqlite3")


def _row(symbol: str, mic: str = "XNAS", **kwargs) -> ListingRow:
    payload = {
        "mic_code": mic,
        "symbol": symbol,
        "name": f"{symbol} Inc",
        "exchange": "NASDAQ",
        "source": "nasdaqtraded",
    }
    payload.update(kwargs)
    return ListingRow(**payload)


def test_default_universe_path():
    assert DEFAULT_UNIVERSE_PATH == project_path("data", "heart", "universe.sqlite")


def test_listing_exchange_codes_map_to_mic():
    assert listing_exchange_to_mic("Q") == "XNAS"
    assert listing_exchange_to_mic("N") == "XNYS"
    assert listing_exchange_to_mic("P") == "ARCX"
    assert listing_exchange_to_mic("A") == "XASE"
    assert listing_exchange_to_mic("Z") == "BATS"
    assert listing_exchange_to_mic("V") == "IEXG"


def test_first_snapshot_inserts_active_identity(registry: UniverseRegistry):
    result = registry.ingest_snapshot(
        [_row("AAPL")],
        as_of=date(2026, 9, 15),
        snapshot_ok=True,
    )
    assert result.inserted == 1
    records = registry.active()
    assert len(records) == 1
    assert records[0].identity == ("XNAS", "AAPL", date(2026, 9, 15))
    assert records[0].delisting_date is None


def test_same_symbol_next_day_does_not_duplicate(registry: UniverseRegistry):
    registry.ingest_snapshot([_row("AAPL")], as_of=date(2026, 9, 14), snapshot_ok=True)
    result = registry.ingest_snapshot([_row("AAPL")], as_of=date(2026, 9, 15), snapshot_ok=True)
    assert result.inserted == 0
    assert result.updated == 1
    records = registry.active()
    assert len(records) == 1
    assert records[0].last_seen == date(2026, 9, 15)
    assert records[0].first_seen == date(2026, 9, 14)


def test_failed_snapshot_does_not_invent_a_delisting(registry: UniverseRegistry):
    registry.ingest_snapshot([_row("AAPL")], as_of=date(2026, 9, 14), snapshot_ok=True)
    result = registry.ingest_snapshot(
        [],
        as_of=date(2026, 9, 15),
        snapshot_ok=False,
        source="nasdaqtraded",
    )
    assert result.delisted == 0
    assert registry.active()[0].delisting_date is None
    assert registry.active()[0].last_seen == date(2026, 9, 14)


def test_successful_empty_snapshot_marks_missing_symbol_delisted(registry: UniverseRegistry):
    registry.ingest_snapshot([_row("AAPL")], as_of=date(2026, 9, 14), snapshot_ok=True)
    result = registry.ingest_snapshot(
        [],
        as_of=date(2026, 9, 15),
        snapshot_ok=True,
        source="nasdaqtraded",
    )
    assert result.delisted == 1
    assert registry.active() == []
    frozen = registry.all_records()
    assert frozen[0].delisting_date == date(2026, 9, 15)
    assert frozen[0].last_seen == date(2026, 9, 14)


def test_recycled_ticker_opens_a_new_identity(registry: UniverseRegistry):
    registry.ingest_snapshot([_row("FB")], as_of=date(2012, 5, 18), snapshot_ok=True)
    registry.ingest_snapshot([], as_of=date(2022, 6, 9), snapshot_ok=True, source="nasdaqtraded")
    result = registry.ingest_snapshot(
        [_row("FB", name="ProShares ETF")],
        as_of=date(2026, 9, 15),
        snapshot_ok=True,
    )
    assert result.inserted == 1
    active = registry.active()
    assert len(active) == 1
    assert active[0].identity == ("XNAS", "FB", date(2026, 9, 15))
    history = registry.all_records()
    assert len(history) == 2
    assert {row.first_seen for row in history} == {date(2012, 5, 18), date(2026, 9, 15)}


def test_test_issues_are_ignored(registry: UniverseRegistry):
    result = registry.ingest_snapshot(
        [_row("ZTEST", is_test=True)],
        as_of=date(2026, 9, 15),
        snapshot_ok=True,
    )
    assert result.inserted == 0
    assert registry.active() == []


def test_other_source_absence_does_not_delist_nasdaq_symbol(registry: UniverseRegistry):
    registry.ingest_snapshot([_row("AAPL")], as_of=date(2026, 9, 14), snapshot_ok=True)
    registry.ingest_snapshot(
        [],
        as_of=date(2026, 9, 15),
        snapshot_ok=True,
        source="tsx_json",
    )
    assert registry.active()[0].symbol == "AAPL"
    assert registry.active()[0].delisting_date is None
