"""Questrade OAuth client restricted to read-only API operations.

This module deliberately exposes no order placement, replacement, or
cancellation method. It uses only GET requests, including token refresh.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Self

import httpx

LIVE_LOGIN_URL = "https://login.questrade.com/oauth2/token"
PRACTICE_LOGIN_URL = "https://practicelogin.questrade.com/oauth2/token"


class QuestradeReadOnlyError(RuntimeError):
    """Raised when Questrade cannot establish a verified read-only session."""


@dataclass(frozen=True)
class QuestradeSession:
    access_token: str
    api_server: str


class QuestradeReadOnlyClient:
    """Minimal Questrade client with a hard GET-only transport boundary."""

    def __init__(
        self,
        refresh_token: str,
        *,
        practice: bool = True,
        client: httpx.Client | None = None,
    ) -> None:
        token = refresh_token.strip()
        if not token:
            raise ValueError("Questrade refresh token is required for read-only access")
        self._refresh_token = token
        self._login_url = PRACTICE_LOGIN_URL if practice else LIVE_LOGIN_URL
        self._client = client or httpx.Client(timeout=15.0)
        self._session: QuestradeSession | None = None

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def refresh(self) -> QuestradeSession:
        """Exchange the user-provided refresh token without creating an order."""
        response = self._client.get(
            self._login_url,
            params={"grant_type": "refresh_token", "refresh_token": self._refresh_token},
        )
        self._raise_for_status(response, "token refresh")
        payload = self._json_object(response, "token refresh")
        access_token = str(payload.get("access_token") or "").strip()
        api_server = str(payload.get("api_server") or "").rstrip("/")
        if not access_token or not api_server.startswith("https://"):
            raise QuestradeReadOnlyError("Questrade token response is missing a valid session")
        self._session = QuestradeSession(access_token=access_token, api_server=api_server)
        return self._session

    def get_accounts(self) -> list[dict[str, Any]]:
        payload = self._get("/v1/accounts")
        accounts = payload.get("accounts")
        if not isinstance(accounts, list):
            raise QuestradeReadOnlyError("Questrade accounts response is invalid")
        return [item for item in accounts if isinstance(item, dict)]

    def get_balances(self, account_id: str) -> list[dict[str, Any]]:
        return self._list(
            f"/v1/accounts/{self._account_id(account_id)}/balances", "perCurrencyBalances"
        )

    def get_positions(self, account_id: str) -> list[dict[str, Any]]:
        return self._list(f"/v1/accounts/{self._account_id(account_id)}/positions", "positions")

    def get_orders(self, account_id: str) -> list[dict[str, Any]]:
        return self._list(f"/v1/accounts/{self._account_id(account_id)}/orders", "orders")

    def get_executions(self, account_id: str) -> list[dict[str, Any]]:
        return self._list(f"/v1/accounts/{self._account_id(account_id)}/executions", "executions")

    def search_symbols(self, prefix: str) -> list[dict[str, Any]]:
        query = prefix.strip().upper()
        if not query or len(query) > 32:
            raise ValueError("Symbol prefix must contain 1 to 32 characters")
        payload = self._get("/v1/symbols/search", params={"prefix": query})
        symbols = payload.get("symbols")
        if not isinstance(symbols, list):
            raise QuestradeReadOnlyError("Questrade symbol search response is invalid")
        return [item for item in symbols if isinstance(item, dict)]

    def readiness(self) -> dict[str, Any]:
        """Verify OAuth and account visibility, returning no credential material."""
        session = self.refresh()
        accounts = self.get_accounts()
        return {
            "provider": "questrade",
            "mode": "read_only",
            "connected": True,
            "practice": self._login_url == PRACTICE_LOGIN_URL,
            "account_count": len(accounts),
            "api_server": session.api_server,
            "can_submit_orders": False,
        }

    def _get(self, path: str, *, params: dict[str, str] | None = None) -> dict[str, Any]:
        session = self._session or self.refresh()
        response = self._client.get(
            f"{session.api_server}{path}",
            params=params,
            headers={"Authorization": f"Bearer {session.access_token}"},
        )
        self._raise_for_status(response, path)
        return self._json_object(response, path)

    def _list(self, path: str, key: str) -> list[dict[str, Any]]:
        values = self._get(path).get(key)
        if not isinstance(values, list):
            raise QuestradeReadOnlyError(f"Questrade response is missing {key}")
        return [item for item in values if isinstance(item, dict)]

    @staticmethod
    def _account_id(account_id: str) -> str:
        value = str(account_id).strip()
        if not value.isdigit() or len(value) > 20:
            raise ValueError("Questrade account id must be numeric")
        return value

    @staticmethod
    def _json_object(response: httpx.Response, operation: str) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise QuestradeReadOnlyError(f"Questrade {operation} returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise QuestradeReadOnlyError(f"Questrade {operation} returned an invalid response")
        return payload

    @staticmethod
    def _raise_for_status(response: httpx.Response, operation: str) -> None:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise QuestradeReadOnlyError(
                f"Questrade {operation} failed with HTTP {response.status_code}"
            ) from exc
