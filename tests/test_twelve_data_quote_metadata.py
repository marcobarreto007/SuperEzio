from __future__ import annotations

from unittest.mock import patch

from data.twelve_data import TwelveDataProvider


class _Response:
    def json(self):
        return {
            "symbol": "TD",
            "exchange": "TSX",
            "currency": "CAD",
            "close": "112.34",
            "timestamp": 1787112000,
        }


def test_twelve_data_price_uses_metadata_rich_quote_endpoint() -> None:
    provider = TwelveDataProvider(api_key="test")
    with patch("data.twelve_data.requests.get", return_value=_Response()) as request:
        result = provider.get_price("TD", exchange="TSX")

    assert request.call_args.args[0].endswith("/quote")
    assert request.call_args.kwargs["params"]["exchange"] == "TSX"
    assert result["price"] == 112.34
    assert result["exchange"] == "TSX"
    assert result["currency"] == "CAD"
    assert result["market_timestamp"] == 1787112000
    assert result["as_of"].endswith("+00:00")
