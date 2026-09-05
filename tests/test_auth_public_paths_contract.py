"""P0 identity contract — single client identity (WS-B slice).

Pins the identity truth table in ``agent_server.auth`` (auth.py:264-299):

* dev mode (no ``SUPEREZIO_JWT_SECRET``)      -> guest ``dev_anon``,
  ``auth_required_for_clients()`` is False;
* open access (``SUPEREZIO_OPEN_ACCESS=1``)    -> guest ``guest_open``,
  ``auth_required_for_clients()`` is False;
* prod-like (secret set, open access off)      -> no guest injection,
  ``auth_required_for_clients()`` is True.

And the public-path contract: ``/health``, ``/favicon.ico``, ``/`` and the
``/auth/*`` endpoints (login, refresh, register) never demand a Bearer token
in prod-like mode, while ``/auth/me`` is never public. Every test scrubs the
``SUPEREZIO_*`` auth env vars first — the suite never depends on a real .env.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from agent_server.auth import (
    AuthDB,
    _guest_user,
    _is_dev_mode,
    _is_public_path,
    _open_access,
    auth_required_for_clients,
    jwt_auth_middleware,
    register_auth_routes,
)

STRONG_SECRET = "x" * 64  # 64 chars — meets the >= 32 requirement

# Env vars read by agent_server.auth — all scrubbed before every scenario.
_AUTH_ENV_KEYS = (
    "SUPEREZIO_JWT_SECRET",
    "SUPEREZIO_OPEN_ACCESS",
    "SUPEREZIO_PUBLIC_MODE",
    "SUPEREZIO_PUBLIC_REGISTRATION",
)


def _scrub_auth_env(monkeypatch) -> None:
    for key in _AUTH_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def _build_app(db_path: Path) -> FastAPI:
    app = FastAPI()
    app.state.auth_db = AuthDB(db_path=db_path)
    register_auth_routes(app)

    @app.get("/protected")
    async def _protected(request: Request):
        user = request.state.user
        return {"username": user.get("username"), "sub": user.get("sub")}

    @app.get("/health")
    async def _health():
        return {"status": "ok"}

    @app.get("/favicon.ico")
    async def _favicon():
        return {"status": "ok"}

    @app.get("/")
    async def _root():
        return {"status": "ok"}

    app.middleware("http")(jwt_auth_middleware)
    return app


def _login(client: TestClient, username: str = "admin", password: str = "p@ssw0rd123") -> str:
    resp = client.post("/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture
def prod_like_client(tmp_path, monkeypatch):
    """Tightest prod-like deploy: strong secret, public mode, no open access."""
    _scrub_auth_env(monkeypatch)
    monkeypatch.setenv("SUPEREZIO_JWT_SECRET", STRONG_SECRET)
    monkeypatch.setenv("SUPEREZIO_OPEN_ACCESS", "0")
    monkeypatch.setenv("SUPEREZIO_PUBLIC_MODE", "1")
    return TestClient(_build_app(tmp_path / "prod-like.db"))


@pytest.fixture
def dev_client(tmp_path, monkeypatch):
    """Dev mode: no secret at all (anonymous dev_anon guest)."""
    _scrub_auth_env(monkeypatch)
    monkeypatch.setenv("SUPEREZIO_OPEN_ACCESS", "0")
    monkeypatch.setenv("SUPEREZIO_PUBLIC_MODE", "0")
    return TestClient(_build_app(tmp_path / "dev.db"))


@pytest.fixture
def open_access_client(tmp_path, monkeypatch):
    """Operator opt-in: strong secret present but SUPEREZIO_OPEN_ACCESS=1."""
    _scrub_auth_env(monkeypatch)
    monkeypatch.setenv("SUPEREZIO_JWT_SECRET", STRONG_SECRET)
    monkeypatch.setenv("SUPEREZIO_OPEN_ACCESS", "1")
    monkeypatch.setenv("SUPEREZIO_PUBLIC_MODE", "0")
    return TestClient(_build_app(tmp_path / "open.db"))


# ---------------------------------------------------------------------------
# Identity truth table (unit level)
# ---------------------------------------------------------------------------


def test_identity_table_dev_mode(monkeypatch):
    _scrub_auth_env(monkeypatch)
    assert _is_dev_mode() is True
    assert _open_access() is False
    assert auth_required_for_clients() is False
    assert _guest_user() == {
        "id": 0,
        "sub": "0",
        "username": "dev_anon",
        "role": "dev",
        "type": "access",
    }


def test_identity_table_open_access(monkeypatch):
    _scrub_auth_env(monkeypatch)
    monkeypatch.setenv("SUPEREZIO_OPEN_ACCESS", "1")
    monkeypatch.setenv("SUPEREZIO_JWT_SECRET", STRONG_SECRET)
    assert _is_dev_mode() is False
    assert _open_access() is True
    assert auth_required_for_clients() is False
    guest = _guest_user()
    assert guest["username"] == "guest_open"
    assert guest["role"] == "guest"
    # Open access wins over dev mode when no secret is present either.
    monkeypatch.delenv("SUPEREZIO_JWT_SECRET")
    assert _guest_user()["username"] == "guest_open"


def test_identity_table_prod_like(monkeypatch):
    _scrub_auth_env(monkeypatch)
    monkeypatch.setenv("SUPEREZIO_JWT_SECRET", STRONG_SECRET)
    monkeypatch.setenv("SUPEREZIO_OPEN_ACCESS", "0")
    monkeypatch.setenv("SUPEREZIO_PUBLIC_MODE", "1")
    assert _is_dev_mode() is False
    assert _open_access() is False
    assert auth_required_for_clients() is True


# ---------------------------------------------------------------------------
# Public-path set (unit level)
# ---------------------------------------------------------------------------


def test_auth_me_is_never_in_the_public_set(monkeypatch):
    _scrub_auth_env(monkeypatch)
    monkeypatch.setenv("SUPEREZIO_PUBLIC_MODE", "1")
    for path in ("/auth/login", "/auth/refresh", "/auth/register"):
        assert _is_public_path(path) is True
    for path in ("/auth/me", "/protected"):
        assert _is_public_path(path) is False
    for path in ("/health", "/favicon.ico", "/"):
        assert _is_public_path(path) is True


# ---------------------------------------------------------------------------
# Public paths at the middleware (prod-like, no Bearer ever demanded)
# ---------------------------------------------------------------------------


def test_public_paths_never_require_bearer_in_prod_like(prod_like_client):
    # Tightened public mode keeps liveness + shell anonymous.
    assert prod_like_client.get("/health").status_code == 200
    assert prod_like_client.get("/favicon.ico").status_code == 200
    assert prod_like_client.get("/").status_code == 200


def test_auth_endpoints_reached_without_bearer_in_prod_like(prod_like_client):
    # Endpoint-level 401s (invalid credentials / expired refresh token), not
    # the middleware gate -> proves login/refresh/register are public.
    login = prod_like_client.post(
        "/auth/login",
        json={"username": "nobody", "password": "wrong-password"},
    )
    assert login.status_code == 401
    assert login.json() == {"detail": "Invalid credentials"}

    refresh = prod_like_client.post("/auth/refresh", json={"refresh_token": "junk-token"})
    assert refresh.status_code == 401
    assert refresh.json() == {"detail": "Invalid or expired refresh token"}

    # Public at the middleware; closed by registration policy (403), not auth.
    register = prod_like_client.post(
        "/auth/register",
        json={"username": "intruder", "email": "i@x.com", "password": "p@ssw0rd123"},
    )
    assert register.status_code == 403
    assert register.json() == {"detail": "Registration is disabled by the operator"}


def test_prod_like_anonymous_never_gets_a_guest_identity(prod_like_client):
    protected = prod_like_client.get("/protected")
    assert protected.status_code == 401
    assert protected.json() == {"error": "Missing or invalid Authorization header"}
    me = prod_like_client.get("/auth/me")
    assert me.status_code == 401


def test_prod_like_rejects_invalid_bearer(prod_like_client):
    resp = prod_like_client.get("/protected", headers={"Authorization": "Bearer not-a-jwt"})
    assert resp.status_code == 401
    assert resp.json() == {"error": "Invalid or expired token"}


def test_auth_me_requires_identity_in_prod_like(prod_like_client):
    db = prod_like_client.app.state.auth_db
    db.create_user(username="admin", email="a@x.com", password="p@ssw0rd123")
    assert prod_like_client.get("/auth/me").status_code == 401

    token = _login(prod_like_client)
    me = prod_like_client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["username"] == "admin"


# ---------------------------------------------------------------------------
# Guest identity injection outside prod
# ---------------------------------------------------------------------------


def test_dev_mode_injects_dev_anon(dev_client):
    protected = dev_client.get("/protected")
    assert protected.status_code == 200
    assert protected.json()["username"] == "dev_anon"
    me = dev_client.get("/auth/me")
    assert me.status_code == 200
    assert me.json() == {
        "id": 0,
        "username": "dev_anon",
        "email": "dev@local",
        "created_at": "",
    }


def test_open_access_injects_guest_open(open_access_client):
    protected = open_access_client.get("/protected")
    assert protected.status_code == 200
    assert protected.json()["username"] == "guest_open"
    me = open_access_client.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["username"] == "guest_open"
    assert me.json()["email"] == "guest@open"


def test_valid_bearer_still_honoured_outside_prod(open_access_client):
    """Guest injection must not discard a real identity when a token is sent.

    Exercised under open access: login can mint a token there (a strong
    secret is configured). In true dev mode the secret is empty and PyJWT
    refuses to sign with an empty HMAC key, so no valid token can exist.
    """
    db = open_access_client.app.state.auth_db
    db.create_user(username="admin", email="a@x.com", password="p@ssw0rd123")
    token = _login(open_access_client)
    resp = open_access_client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["username"] == "admin"
    assert resp.json()["sub"] != "0"
