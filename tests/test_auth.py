"""
Tests for core.auth module — AuthDB (SQLite + JWT) and agent_server/auth.py endpoints.

Coverage targets:
  - src/core/auth/service.py  : AuthDB — register, authenticate, login, token ops
  - src/core/auth/models.py   : Pydantic schemas (covered implicitly)
  - src/agent_server/auth.py  : FastAPI endpoints + JWT middleware

Strategy:
  - Temp SQLite database via tmp_path (no side effects on real data/)
  - monkeypatch for SUPEREZIO_JWT_SECRET env var
  - FastAPI TestClient for endpoint tests
"""

from __future__ import annotations

import os

import jwt as pyjwt
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from core.auth.models import UserRegister, UserLogin


# ===================================================================
#  Fixtures — Core AuthDB tests
# ===================================================================


@pytest.fixture
def jwt_secret(monkeypatch):
    """Set a deterministic JWT secret for all tests that need tokens."""
    monkeypatch.setenv(
        "SUPEREZIO_JWT_SECRET",
        "test-secret-for-testing-purposes-only",
    )
    return "test-secret-for-testing-purposes-only"


@pytest.fixture
def core_db(tmp_path, jwt_secret):
    """Core AuthDB wired to a temporary SQLite file.

    Cleanup is left to tmp_path, which removes the entire directory
    after the test session. (Explicit unlink fails on Windows because
    SQLite WAL mode keeps file handles open.)
    """
    from core.auth.service import AuthDB

    db_path = tmp_path / "core_test.db"
    db = AuthDB(db_path=db_path)
    yield db


# ===================================================================
#  TestAuthDB  —  core.auth.service.AuthDB
# ===================================================================


class TestAuthDB:
    """SQLite persistence, bcrypt hashing, JWT token management."""

    # -- register ---------------------------------------------------------

    def test_register_creates_user(self, core_db):
        """Register a valid user and verify the returned dict shape."""
        payload = UserRegister(
            username="alice",
            email="alice@example.com",
            password="SecureP@ss1",
        )
        user = core_db.register(payload)

        assert user["username"] == "alice"
        assert user["email"] == "alice@example.com"
        assert "id" in user
        assert user["role"] == "user"
        assert user["is_active"] == 1
        assert "created_at" in user
        # password_hash must never leak to callers
        assert "password_hash" not in user

    def test_register_duplicate_username_fails(self, core_db):
        """Registering with an existing username must raise ValueError."""
        core_db.register(
            UserRegister(
                username="alice",
                email="alice@example.com",
                password="SecureP@ss1",
            )
        )
        with pytest.raises(ValueError, match="already exists"):
            core_db.register(
                UserRegister(
                    username="alice",
                    email="bob@example.com",
                    password="OtherP@ss1",
                )
            )

    # -- authenticate -----------------------------------------------------

    def test_authenticate_valid_credentials(self, core_db):
        """Valid username + password returns the user dict (no hash)."""
        core_db.register(
            UserRegister(
                username="bob",
                email="bob@example.com",
                password="MyP@ssw0rd",
            )
        )
        user = core_db.authenticate(
            UserLogin(username="bob", password="MyP@ssw0rd")
        )
        assert user["username"] == "bob"
        assert "password_hash" not in user
        assert user["is_active"] == 1

    def test_authenticate_wrong_password_fails(self, core_db):
        """Wrong password must raise ValueError with a generic message."""
        core_db.register(
            UserRegister(
                username="charlie",
                email="c@example.com",
                password="ValidP@ss1",
            )
        )
        with pytest.raises(ValueError, match="Invalid username or password"):
            core_db.authenticate(
                UserLogin(username="charlie", password="WrongP@ss1")
            )

    def test_authenticate_unknown_user_fails(self, core_db):
        """Non-existent username must raise ValueError."""
        with pytest.raises(ValueError, match="Invalid username or password"):
            core_db.authenticate(
                UserLogin(username="nobody", password="irrelevant")
            )

    # -- login ------------------------------------------------------------

    def test_login_returns_tokens(self, core_db):
        """Login returns a TokenResponse with access + refresh tokens."""
        core_db.register(
            UserRegister(
                username="dave",
                email="d@example.com",
                password="Str0ng!Pass",
            )
        )
        result = core_db.login(UserLogin(username="dave", password="Str0ng!Pass"))

        assert result.access_token
        assert result.refresh_token
        assert result.token_type == "bearer"
        assert result.expires_in == 3600

        # Decode the JWT to verify the payload
        decoded = pyjwt.decode(
            result.access_token,
            os.environ["SUPEREZIO_JWT_SECRET"],
            algorithms=["HS256"],
        )
        assert decoded["username"] == "dave"
        assert decoded["role"] == "user"

    # -- refresh token rotation -------------------------------------------

    def test_refresh_token_rotation(self, core_db, jwt_secret):
        """Rotating a refresh token returns a new pair and invalidates the old one."""
        core_db.register(
            UserRegister(
                username="eve",
                email="e@example.com",
                password="EveP@ss123!",
            )
        )
        tokens = core_db.login(UserLogin(username="eve", password="EveP@ss123!"))
        old_refresh = tokens.refresh_token

        new_tokens = core_db.rotate_refresh_token(old_refresh)

        # Refresh tokens are random — must always differ.
        assert new_tokens.refresh_token != old_refresh
        # Access tokens *can* be identical if issued in the same second
        # (same iat/exp payload).  Validate the decoded content instead.
        decoded_new = pyjwt.decode(
            new_tokens.access_token,
            os.environ["SUPEREZIO_JWT_SECRET"],
            algorithms=["HS256"],
        )
        assert decoded_new["username"] == "eve"

        # Old token must now be invalid (consumed / deleted)
        with pytest.raises(ValueError, match="Invalid refresh token"):
            core_db.rotate_refresh_token(old_refresh)

    def test_double_refresh_fails(self, core_db, jwt_secret):
        """Using the same refresh token twice must raise ValueError (rotation)."""
        core_db.register(
            UserRegister(
                username="frank",
                email="f@example.com",
                password="Fr@nkPass1",
            )
        )
        tokens = core_db.login(UserLogin(username="frank", password="Fr@nkPass1"))

        # First rotation succeeds
        core_db.rotate_refresh_token(tokens.refresh_token)

        # Second rotation with same token fails
        with pytest.raises(ValueError, match="Invalid refresh token"):
            core_db.rotate_refresh_token(tokens.refresh_token)

    # -- JWT encode / decode ---------------------------------------------

    def test_decode_valid_token(self, core_db, jwt_secret):
        """Decoding a valid access token returns the original payload."""
        token = core_db.create_access_token(
            {"id": 42, "username": "grace", "role": "user"}
        )
        decoded = core_db.decode_token(token)

        assert decoded["sub"] == "42"
        assert decoded["username"] == "grace"
        assert decoded["role"] == "user"

    def test_jwt_secret_missing_raises(self, monkeypatch, tmp_path):
        """Without SUPEREZIO_JWT_SECRET, creating a token raises RuntimeError."""
        monkeypatch.delenv("SUPEREZIO_JWT_SECRET", raising=False)

        from core.auth.service import AuthDB

        db_path = tmp_path / "no_secret.db"
        db = AuthDB(db_path=db_path)
        db.register(
            UserRegister(
                username="hank",
                email="h@example.com",
                password="HankP@ss1",
            )
        )

        # create_access_token must raise
        with pytest.raises(RuntimeError, match="SUPEREZIO_JWT_SECRET"):
            db.create_access_token(
                {"id": 1, "username": "hank", "role": "user"}
            )

        # login must also raise since it calls create_access_token internally
        with pytest.raises(RuntimeError, match="SUPEREZIO_JWT_SECRET"):
            db.login(UserLogin(username="hank", password="HankP@ss1"))


# ===================================================================
#  Fixtures — API endpoint tests
# ===================================================================


@pytest.fixture
def api_app(tmp_path, jwt_secret):
    """FastAPI app with the auth router + a /protected endpoint + JWT middleware."""
    from agent_server.auth import (
        AuthDB as ServerAuthDB,
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
