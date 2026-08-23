"""DataHub provider priority chain."""

from __future__ import annotations

from data.data_hub import DataHub, ProviderRoute


def test_market_price_route_order() -> None:
    hub = DataHub(register_defaults=True)
    routes = hub.list_routes("price")
    # Chain (2026-08-22): finnhub (priority 1) -> twelve_data -> yfinance
    # AKShare removed from price (downloads 893 stocks, 3+ min!)
    # Stooq removed — API offline (HTTP 404)
    ordered = [r["name"] for r in sorted(routes, key=lambda x: x["priority"])]
    assert ordered[0] == "finnhub"
    assert ordered.index("twelve_data") < ordered.index("yfinance")


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
    yfinance) since route() stops at the first usable result. Stooq removed 2026-07-20.
    """
    assert DataHub._is_usable_result({}) is False


def test_is_usable_result_accepts_nonempty_dict_without_error() -> None:
    assert DataHub._is_usable_result({"price": 123.45}, "price") is True


def test_is_usable_result_rejects_dict_with_error_key() -> None:
    assert DataHub._is_usable_result({"error": "not_found"}) is False


def test_is_usable_result_validates_capability_shape() -> None:
    assert DataHub._is_usable_result({"price": 0}, "price") is False
    assert DataHub._is_usable_result({"price": float("nan")}, "price") is False
    assert DataHub._is_usable_result({"note": ""}, "price") is False
    assert DataHub._is_usable_result({"candles": []}, "candles") is False
    assert DataHub._is_usable_result({"candles": [{"close": 12.0}]}, "candles") is True
    assert DataHub._is_usable_result({"name": "Acme"}, "profile") is True
    assert DataHub._is_usable_result({"is_open": False}) is True
    assert DataHub._is_usable_result({"note": ""}) is False


def test_is_usable_result_rejects_empty_list_and_none() -> None:
    assert DataHub._is_usable_result([]) is False
    assert DataHub._is_usable_result(None) is False


def test_is_usable_result_accepts_nonempty_list_and_scalars() -> None:
    assert DataHub._is_usable_result([1, 2, 3]) is True
    assert DataHub._is_usable_result(42) is True
    assert DataHub._is_usable_result("ok") is True


def test_price_route_falls_back_when_first_provider_has_no_price() -> None:
    class EmptyProvider:
        @staticmethod
        def get_price(symbol):
            return {"note": "", "symbol": symbol}

    class PriceProvider:
        @staticmethod
        def get_price(symbol):
            return {"price": 123.0, "symbol": symbol}

    hub = DataHub(register_defaults=False)
    hub.register_provider(
        ProviderRoute(
            name="empty",
            capabilities=("price",),
            factory=EmptyProvider,
            methods={"price": "get_price"},
            priority=1,
        )
    )
    hub.register_provider(
        ProviderRoute(
            name="valid",
            capabilities=("price",),
            factory=PriceProvider,
            methods={"price": "get_price"},
            priority=2,
        )
    )

    result = hub.get_price("AAPL")
    assert result["price"] == 123.0
    assert result["provider"] == "valid"


def test_quote_capability_resolves_price_capable_routes() -> None:
    """With finnhub unconfigured, "quote" must still resolve via price-capable
    routes (2026-08-23: quote died with "all providers exhausted" after the
    Finnhub key was removed)."""

    class PriceProvider:
        @staticmethod
        def get_price(symbol):
            return {"price": 42.0, "symbol": symbol}

    hub = DataHub(register_defaults=False)
    hub.register_provider(
        ProviderRoute(
            name="price_only",
            capabilities=("price",),
            factory=PriceProvider,
            methods={"price": "get_price"},
            priority=1,
        )
    )
    assert [route.name for route in hub.resolve("quote")] == ["price_only"]


def test_quote_route_falls_back_to_price_method() -> None:
    """route("quote") uses the route's price method when no dedicated quote
    method exists (capability alias fallback)."""

    class PriceProvider:
        @staticmethod
        def get_price(symbol):
            return {"price": 42.0, "symbol": symbol}

    hub = DataHub(register_defaults=False)
    hub.register_provider(
        ProviderRoute(
            name="price_only",
            capabilities=("price",),
            factory=PriceProvider,
            methods={"price": "get_price"},
            priority=1,
        )
    )
    result = hub.route("quote", "AAPL")
    assert result["price"] == 42.0
    assert result["provider"] == "price_only"


def test_quote_prefers_dedicated_quote_method_over_alias() -> None:
    """A route exposing both "quote" and "price" methods must serve quote via
    its dedicated quote method (finnhub contract preserved)."""

    class BothProvider:
        @staticmethod
        def get_quote(symbol):
            return {"price": 7.0, "symbol": symbol}

        @staticmethod
        def get_price(symbol):
            return {"price": 1.0, "symbol": symbol}

    hub = DataHub(register_defaults=False)
    hub.register_provider(
        ProviderRoute(
            name="both",
            capabilities=("quote", "price"),
            factory=BothProvider,
            methods={"quote": "get_quote", "price": "get_price"},
            priority=1,
        )
    )
    result = hub.route("quote", "AAPL")
    assert result["price"] == 7.0
    assert result["provider"] == "both"


def test_new_keyless_news_sentiment_routes_registered() -> None:
    """google_news_ca and yahoo_conversation must be registered, keyless, and
    resolvable for the gaps they fill (Canadian news, .TO sentiment)."""
    hub = DataHub(register_defaults=False)
    hub._register_default_routes()

    news = [r.name for r in hub.resolve("news")]
    assert "google_news_ca" in news
    assert "yahoo_conversation" in news

    sentiment = [r.name for r in hub.resolve("sentiment")]
    assert "yahoo_conversation" in sentiment

    for name in ("google_news_ca", "yahoo_conversation"):
        route = hub.routes[name]
        assert route.required_key is None  # keyless by design
        assert route.enabled
        assert hub.get_provider(name) is not None  # factory instantiates


def test_keyless_news_routes_precede_news_scout_crawl() -> None:
    """Order: finnhub/newsapi (keyed) → google_news_ca (20) → yahoo_conversation
    (21) → news_scout (22) — the dedicated keyless feeds win over the crawl."""
    hub = DataHub(register_defaults=False)
    hub._register_default_routes()
    ranked = [r.name for r in hub.resolve("news")]
    assert ranked.index("google_news_ca") < ranked.index("yahoo_conversation")
    assert ranked.index("yahoo_conversation") < ranked.index("news_scout")
