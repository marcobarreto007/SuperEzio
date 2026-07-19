"""DataHub provider priority chain."""

from __future__ import annotations

from data.data_hub import DataHub


def test_market_price_route_order() -> None:
    hub = DataHub(register_defaults=True)
    routes = hub.list_routes("price")
    # Finnhub may be unconfigured in CI; still check relative order of fallbacks.
    ordered = [r["name"] for r in sorted(routes, key=lambda x: x["priority"])]
    assert ordered.index("finnhub") < ordered.index("twelve_data")
    assert ordered.index("twelve_data") < ordered.index("yfinance")
    assert ordered.index("yfinance") < ordered.index("stooq")


def test_finnhub_has_candles_and_news_capabilities() -> None:
    hub = DataHub(register_defaults=True)
    finn = next(r for r in hub.list_routes() if r["name"] == "finnhub")
    assert "candles" in finn["capabilities"]
    assert "fundamentals" in finn["capabilities"]
    assert "news" in finn["capabilities"]
    assert finn["priority"] == 1


def test_is_usable_result_rejects_empty_dict() -> None:
    """Empty dict {} must NOT be treated as a usable provider result.

    Regression guard: an empty dict has no "error" key, so a naive check
    of `"error" not in result` alone would wrongly accept it as success
    and silently break the fallback chain (Finnhub -> TwelveData ->
    yfinance -> Stooq) since route() stops at the first usable result.
    """
    assert DataHub._is_usable_result({}) is False


def test_is_usable_result_accepts_nonempty_dict_without_error() -> None:
    assert DataHub._is_usable_result({"price": 123.45}) is True


def test_is_usable_result_rejects_dict_with_error_key() -> None:
    assert DataHub._is_usable_result({"error": "not_found"}) is False


def test_is_usable_result_accepts_dict_with_falsy_values() -> None:
    """A dict with real keys whose values are falsy (0/False/"") is still
    usable content -- only a dict with zero keys is unusable."""
    assert DataHub._is_usable_result({"price": 0}) is True
    assert DataHub._is_usable_result({"is_open": False}) is True
    assert DataHub._is_usable_result({"note": ""}) is True


def test_is_usable_result_rejects_empty_list_and_none() -> None:
    assert DataHub._is_usable_result([]) is False
    assert DataHub._is_usable_result(None) is False


def test_is_usable_result_accepts_nonempty_list_and_scalars() -> None:
    assert DataHub._is_usable_result([1, 2, 3]) is True
    assert DataHub._is_usable_result(42) is True
    assert DataHub._is_usable_result("ok") is True
