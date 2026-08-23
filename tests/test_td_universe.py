"""TD tradable universe contract tests (operator decision 2026-08-23)."""

from __future__ import annotations

from core.trading.td_universe import (
    commission_free_universe,
    is_commission_free,
    is_td_tradable_exchange,
    td_universe_summary,
)


def test_manifest_loads_108_symbols() -> None:
    universe = commission_free_universe()
    total = len(universe["CAN"]) + len(universe["US"])
    assert total == 108, f"expected 108 commission-free ETFs, got {total}"
    assert "TBAL" in universe["CAN"]  # TD Balanced ETF
    assert "VEQT" in universe["CAN"]  # Vanguard CA
    assert "SPY" in universe["US"]


def test_is_commission_free() -> None:
    assert is_commission_free("tbal") is True  # case-insensitive
    assert is_commission_free("SPY") is True
    assert is_commission_free("CSU") is False  # TSX-only, not in the manifest
    assert is_commission_free("") is False


def test_is_td_tradable_exchange() -> None:
    assert is_td_tradable_exchange("TSE") is True  # Toronto (yfinance code)
    assert is_td_tradable_exchange("NASDAQ") is True
    assert is_td_tradable_exchange("NYSE") is True
    assert is_td_tradable_exchange("OTC Markets") is False
    assert is_td_tradable_exchange("PNK") is False
    assert is_td_tradable_exchange("") is False
    assert is_td_tradable_exchange(None) is False


def test_td_universe_summary() -> None:
    summary = td_universe_summary()
    assert summary["commission_free_total"] == 108
    assert summary["commission_free_can"] + summary["commission_free_us"] == 108
