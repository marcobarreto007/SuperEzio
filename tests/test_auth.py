"""
Tests for agent_server/auth.py — FastAPI endpoints + JWT middleware.

The legacy core.auth package (AuthDB in core/auth/service.py) was removed
2026-08-26 as dead code (zero product importers); the live auth surface is
agent_server/auth.py.

Strategy:
  - Temp SQLite database via tmp_path (no side effects on real data/)
  - monkeypatch for SUPEREZIO_JWT_SECRET env var
  - FastAPI TestClient for endpoint tests
"""

from __future__ import annotations

import jwt as pyjwt
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

# ===================================================================
#  Fixtures — JWT secret for endpoint tests
# ===================================================================


@pytest.fixture
def jwt_secret(monkeypatch):
    """Set a deterministic JWT secret for all tests that need tokens.

    Also pins PUBLIC_MODE=0: other test modules import agent_server.main,
    which loads .env.local into the shared process env — with the operator's
    SUPEREZIO_PUBLIC_MODE=1 that would silently flip these dev-mode auth
    tests (register 201 -> 403). These tests own the dev contract.
    """
    monkeypatch.setenv(
        "SUPEREZIO_JWT_SECRET",
        "test-secret-for-testing-purposes-only",
    )
    monkeypatch.setenv("SUPEREZIO_PUBLIC_MODE", "0")
    monkeypatch.setenv("SUPEREZIO_OPEN_ACCESS", "0")
    return "test-secret-for-testing-purposes-only"


# ===================================================================
#  Fixtures — API endpoint tests
# ===================================================================


@pytest.fixture
def api_app(tmp_path, jwt_secret):
    """FastAPI app with the auth router + a /protected endpoint + JWT middleware."""
    from agent_server.auth import (
        AuthDB as ServerAuthDB,
    )
    from agent_server.auth import (
        jwt_auth_middleware,
        register_auth_routes,
    )

    app = FastAPI()
    app.state.auth_db = ServerAuthDB(db_path=tmp_path / "api_test.db")

    # -- routes --
    register_auth_routes(app)

    @app.get("/protected")
    async def _protected(request: Request):
        user = request.state.user
        return {
            "user_id": user.get("sub"),
            "username": user.get("username"),
        }

    # -- middleware (must be last so it wraps all routes) --
    app.middleware("http")(jwt_auth_middleware)
    return app


@pytest.fixture
def api_client(api_app):
    """TestClient bound to the test auth app."""
    return TestClient(api_app)


@pytest.fixture
def api_user(api_client):
    """Register a user via the API and return the credentials dict."""
    creds = {
        "username": "apiuser",
        "email": "apiuser@test.com",
        "password": "ApiUserP@ss1",
    }
    resp = api_client.post("/auth/register", json=creds)
    assert resp.status_code == 201, f"register failed: {resp.json()}"
    return creds


# ===================================================================
#  TestAuthAPI  —  agent_server/auth.py FastAPI endpoints
# ===================================================================


class TestAuthAPI:
    """FastAPI endpoints: register, login, refresh, me, protected route."""

    # -- POST /auth/register --------------------------------------------

    def test_register_endpoint(self, api_client):
        """POST /auth/register returns 201 with public user profile."""
        body = {
            "username": "newuser",
            "email": "new@test.com",
            "password": "Str0ng!Pass",
        }
        resp = api_client.post("/auth/register", json=body)

        assert resp.status_code == 201
        data = resp.json()
        assert data["username"] == "newuser"
        assert data["email"] == "new@test.com"
        assert "id" in data
        assert "created_at" in data
        # sensitive fields must never leak
        assert "password" not in data
        assert "password_hash" not in data

    def test_register_duplicate_fails(self, api_client, api_user):
        """POST /auth/register with duplicate username returns 409."""
        body = {
            "username": "apiuser",
            "email": "other@test.com",
            "password": "OtherP@ss1",
        }
        resp = api_client.post("/auth/register", json=body)
        assert resp.status_code == 409

    # -- POST /auth/login ------------------------------------------------

    def test_login_endpoint(self, api_client, api_user):
        """POST /auth/login returns 200 with a token pair."""
        resp = api_client.post(
            "/auth/login",
            json={"username": "apiuser", "password": "ApiUserP@ss1"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    def test_login_invalid_credentials(self, api_client, api_user):
        """POST /auth/login with wrong password returns 401."""
        resp = api_client.post(
            "/auth/login",
            json={"username": "apiuser", "password": "WrongPassword!"},
        )
        assert resp.status_code == 401

    # -- POST /auth/refresh ----------------------------------------------

    def test_refresh_endpoint(self, api_client, api_user, jwt_secret):
        """POST /auth/refresh rotates the token pair; old token is rejected."""
        # 1) login to obtain a fresh token pair
        login_resp = api_client.post(
            "/auth/login",
            json={"username": "apiuser", "password": "ApiUserP@ss1"},
        )
        tokens = login_resp.json()
        old_refresh = tokens["refresh_token"]

        # 2) refresh — must return a new pair
        refresh_resp = api_client.post(
            "/auth/refresh",
            json={"refresh_token": old_refresh},
        )
        assert refresh_resp.status_code == 200
        new = refresh_resp.json()
        # Refresh tokens are random — must always differ.
        assert new["refresh_token"] != old_refresh
        # Access tokens *can* be identical if issued in the same second.
        # Validate the decoded content instead.
        decoded_new = pyjwt.decode(
            new["access_token"],
            jwt_secret,
            algorithms=["HS256"],
        )
        assert decoded_new["username"] == "apiuser"

        # 3) reusing the old refresh token must fail (rotation)
        retry = api_client.post(
            "/auth/refresh",
            json={"refresh_token": old_refresh},
        )
        assert retry.status_code == 401
        assert "already used" in retry.json().get("detail", "").lower()

    def test_refresh_invalid_token_fails(self, api_client, api_user):
        """POST /auth/refresh with a garbage token returns 401."""
        resp = api_client.post(
            "/auth/refresh",
            json={"refresh_token": "this-is-not-a-valid-refresh-token"},
        )
        assert resp.status_code == 401

    # -- GET /auth/me ----------------------------------------------------

    def test_me_endpoint_requires_auth(self, api_client):
        """GET /auth/me without auth returns 401.

        The JWT middleware now enforces auth on /auth/me (it is not in
        _PUBLIC_AUTH_PATHS), so missing Authorization header -> 401.
        """
        resp = api_client.get("/auth/me")
        assert resp.status_code == 401

    # -- /protected (non-public route guarded by JWT middleware) ----------

    def test_protected_route_requires_auth(self, api_client):
        """Accessing a protected route without auth header returns 401."""
        resp = api_client.get("/protected")
        assert resp.status_code == 401

    def test_protected_route_with_valid_token(self, api_client, api_user, jwt_secret):
        """Accessing a protected route with valid Bearer token succeeds."""
        login_resp = api_client.post(
            "/auth/login",
            json={"username": "apiuser", "password": "ApiUserP@ss1"},
        )
        token = login_resp.json()["access_token"]

        resp = api_client.get(
            "/protected",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "apiuser"

    def test_expired_token_returns_401(self, api_client, api_user, jwt_secret):
        """An expired access token must be rejected with 401."""
        import time

        payload = {
            "sub": "1",
            "username": "apiuser",
            "iat": int(time.time()) - 7200,
            "exp": int(time.time()) - 3600,
            "type": "access",
        }
        expired = pyjwt.encode(payload, jwt_secret, algorithm="HS256")

        # Test both /auth/me (which checks user internally)
        # and /protected (which relies on middleware)
        for path in ("/auth/me", "/protected"):
            resp = api_client.get(
                path,
                headers={"Authorization": f"Bearer {expired}"},
            )
            assert resp.status_code == 401, f"{path} should reject expired token"

    def test_malformed_token_returns_401(self, api_client, api_user, jwt_secret):
        """A completely bogus token must be rejected with 401."""
        resp = api_client.get(
            "/protected",
            headers={"Authorization": "Bearer not-a-jwt-at-all"},
        )
        assert resp.status_code == 401
