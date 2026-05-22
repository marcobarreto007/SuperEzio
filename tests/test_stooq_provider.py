"""Tests for Stooq symbol mapping and provider contract."""

from __future__ import annotations

import inspect

from data.stooq_provider import StooqProvider, stooq_symbol


def test_stooq_symbol_us_default() -> None:
    assert stooq_symbol("AAPL", "United States") == "aapl.us"


def test_stooq_symbol_canada_suffix() -> None:
    assert stooq_symbol("RY", "Canada") == "ry.to"
    assert stooq_symbol("RY.TO", "Canada") == "ry.to"


def test_stooq_get_price_accepts_market_kwarg() -> None:
    sig = inspect.signature(StooqProvider.get_price)
    assert "market" in sig.parameters


def test_data_hub_filters_market_for_twelve_data() -> None:
    from data.data_hub import DataHub

    hub = DataHub(register_defaults=False)
    from data.twelve_data import TwelveDataProvider

    method = TwelveDataProvider.get_price
    filtered = hub._kwargs_for_method(method, {"market": "United States"})
    assert filtered == {}
