from __future__ import annotations

import httpx
import pytest

from adapters.broker.questrade_readonly import PRACTICE_LOGIN_URL, QuestradeReadOnlyClient


def _client(handler) -> QuestradeReadOnlyClient:
    return QuestradeReadOnlyClient(
        "refresh-token", client=httpx.Client(transport=httpx.MockTransport(handler))
    )


def test_readiness_uses_only_get_and_never_exposes_tokens():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if str(request.url).startswith(PRACTICE_LOGIN_URL):
            return httpx.Response(
                200,
                json={"access_token": "access-secret", "api_server": "https://api.example.test"},
            )
        assert request.headers["Authorization"] == "Bearer access-secret"
        assert request.url.path == "/v1/accounts"
        return httpx.Response(200, json={"accounts": [{"number": "12345678"}]})

    with _client(handler) as client:
        result = client.readiness()

    assert result["connected"] is True
    assert result["can_submit_orders"] is False
    assert all(request.method == "GET" for request in requests)
    assert "access-secret" not in str(result)
    assert "refresh-token" not in str(result)


def test_read_only_client_fetches_positions_and_rejects_invalid_account_id():
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).startswith(PRACTICE_LOGIN_URL):
            return httpx.Response(
                200, json={"access_token": "access", "api_server": "https://api.example.test"}
            )
        assert request.method == "GET"
        assert request.url.path == "/v1/accounts/12345678/positions"
        return httpx.Response(200, json={"positions": [{"symbol": "SHOP.TO"}]})

    with _client(handler) as client:
        assert client.get_positions("12345678") == [{"symbol": "SHOP.TO"}]
        with pytest.raises(ValueError, match="numeric"):
            client.get_positions("123/../456")
