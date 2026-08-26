"""TD tradable universe contract tests (operator decision 2026-08-23)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from core.trading import td_universe
from core.trading.td_universe import (
    commission_free_universe,
    exchange_currency,
    has_otc_marker,
    is_commission_free,
    is_td_tradable,
    is_td_tradable_exchange,
    normalize_td_exchange,
    td_canonical_exchanges,
    td_exchange_alias_codes,
    td_universe_summary,
    tradable_universe_state,
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
    assert summary["tradable_manifest_state"] in {
        "fresh",
        "stale",
        "missing",
        "invalid",
    }


# ── Allowlist semantics (TD lock, 2026-08-23) ───────────────────────────────


@pytest.mark.parametrize(
    ("raw", "canonical"),
    [
        # canonical spellings
        ("TSX", "TSX"),
        ("tsxv", "TSXV"),
        ("NYSE", "NYSE"),
        ("nasdaq", "NASDAQ"),
        ("NYSEAMERICAN", "NYSEAMERICAN"),
        ("NYSEARCA", "NYSEARCA"),
        # Yahoo / FinanceDatabase codes
        ("TOR", "TSX"),
        ("TSE", "TSX"),
        ("TSV", "TSXV"),
        ("NYQ", "NYSE"),
        ("NMS", "NASDAQ"),
        ("NGM", "NASDAQ"),
        ("NCM", "NASDAQ"),
        ("ASE", "NYSEAMERICAN"),
        ("PCX", "NYSEARCA"),
        # Twelve Data ISO MIC
        ("XTSE", "TSX"),
        ("XTSX", "TSXV"),
        # common spellings with separators
        ("AMEX", "NYSEAMERICAN"),
        ("NYSE American", "NYSEAMERICAN"),
        ("NYSE-MKT", "NYSEAMERICAN"),
        ("ARCA", "NYSEARCA"),
        ("NYSE Arca", "NYSEARCA"),
        ("TSX-V", "TSXV"),
        ("TSX Venture", "TSXV"),
    ],
)
def test_normalize_td_exchange_supported(raw: str, canonical: str) -> None:
    assert normalize_td_exchange(raw) == canonical


@pytest.mark.parametrize(
    "raw",
    [
        "LSE",  # London
        "BVMF",  # B3/Brazil
        "CSE",  # Canadian Securities Exchange (not TD-confirmed)
        "NEO",  # Cboe Canada (not TD-confirmed)
        "US",  # generic Finnhub bucket — cannot prove a listed venue
        "IEXG",
        "BZX",
        "JPX",
        "OTCBB",
        "",
        None,
    ],
)
def test_normalize_td_exchange_rejects(raw: str | None) -> None:
    assert normalize_td_exchange(raw) is None
    assert is_td_tradable_exchange(raw) is False


def test_has_otc_marker() -> None:
    assert has_otc_marker("OTC Markets") is True
    assert has_otc_marker("pink sheets") is True  # substring, case-insensitive
    assert has_otc_marker("OTCM") is True
    assert has_otc_marker("NYSE") is False
    assert has_otc_marker("") is False
    assert has_otc_marker(None) is False


def test_exchange_currency() -> None:
    assert exchange_currency("TSX") == "CAD"
    assert exchange_currency("TOR") == "CAD"
    assert exchange_currency("XTSX") == "CAD"
    assert exchange_currency("NYSE") == "USD"
    assert exchange_currency("AMEX") == "USD"
    assert exchange_currency("PCX") == "USD"  # NYSE Arca
    assert exchange_currency("LSE") is None
    assert exchange_currency(None) is None


def test_canonical_exchanges_are_six() -> None:
    assert td_canonical_exchanges() == frozenset(
        {"TSX", "TSXV", "NYSE", "NASDAQ", "NYSEAMERICAN", "NYSEARCA"}
    )


def test_alias_codes_cover_scanner_needs() -> None:
    us = td_exchange_alias_codes({"NYSE", "NASDAQ", "NYSEAMERICAN", "NYSEARCA"})
    ca = td_exchange_alias_codes({"TSX", "TSXV"})
    # FinanceDatabase/Yahoo codes the scanner compares against
    assert {"NYQ", "NMS", "NCM", "ASE", "NGM", "PCX"} <= us
    assert {"TOR", "TSX", "TSV"} <= ca
    # Non-TD venues must not leak into any alias set
    assert not ({"CSE", "NEO", "LSE", "US"} & (us | ca))


# ── Full tradable manifest (schema v2, TTL fail-closed) ─────────────────────


@pytest.fixture()
def isolated_manifest(tmp_path, monkeypatch):
    """Point the module at a temp manifest and reset the symbol cache."""
    manifest_path = tmp_path / "td_tradable_universe.json"
    monkeypatch.setattr(td_universe, "_TRADABLE_MANIFEST_PATH", manifest_path)
    td_universe._tradable_symbols_cached.cache_clear()
    yield manifest_path
    td_universe._tradable_symbols_cached.cache_clear()


def _write_manifest(path, *, generated_at: str, symbols_by_exchange: dict) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "generated_at": generated_at,
                "ttl_days": 7,
                "sources": {"test": "https://example.test"},
                "exchanges": symbols_by_exchange,
            }
        ),
        encoding="utf-8",
    )


def test_manifest_state_missing(isolated_manifest) -> None:
    assert tradable_universe_state()["state"] == "missing"
    assert is_td_tradable("AAPL") is False  # no manifest, no venue -> fail closed


def test_manifest_state_fresh(isolated_manifest) -> None:
    now = datetime.now(UTC).isoformat()
    _write_manifest(
        isolated_manifest,
        generated_at=now,
        symbols_by_exchange={"NYSE": ["BRK.B"], "TSX": ["TD.TO"]},
    )
    state = tradable_universe_state()
    assert state["state"] == "fresh"
    assert state["symbol_total"] == 2
    assert is_td_tradable("TD.TO") is True  # symbol-only, vouched by manifest
    assert is_td_tradable("brk.b") is True  # case-insensitive membership
    assert is_td_tradable("ZZZZZZ") is False


def test_manifest_state_stale_degrades_to_allowlist(isolated_manifest) -> None:
    old = (datetime.now(UTC) - timedelta(days=30)).isoformat()
    _write_manifest(
        isolated_manifest,
        generated_at=old,
        symbols_by_exchange={"NYSE": ["BRK.B"]},
    )
    state = tradable_universe_state()
    assert state["state"] == "stale"
    assert state["age_days"] > 7
    # Stale manifest does not vouch for symbols...
    assert is_td_tradable("BRK.B") is False
    # ...but the exchange allowlist still works (explicit degradation).
    assert is_td_tradable("BRK.B", exchange="NYSE") is True


def test_manifest_state_invalid_schema(isolated_manifest) -> None:
    isolated_manifest.write_text(
        json.dumps({"schema_version": 1, "exchanges": {}}), encoding="utf-8"
    )
    assert tradable_universe_state()["state"] == "invalid"
    assert is_td_tradable("AAPL") is False


def test_is_td_tradable_venue_route_beats_manifest(isolated_manifest) -> None:
    # Even with no manifest at all, a TD venue passes; a foreign venue never does.
    assert is_td_tradable("AAPL", exchange="NASDAQ") is True
    assert is_td_tradable("SOME.SA", exchange="BVMF") is False
    assert is_td_tradable("XYZ", exchange="CSE") is False
