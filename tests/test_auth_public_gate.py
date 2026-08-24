"""Public-mode auth gate tests (Gate A — public deploy hardening, 2026-08-22).

Covers the acceptance criteria G1-G6 of the consolidated deploy plan:
G1 protected routes 401 anonymous in public mode; G2 login + Bearer works;
G3 boot fails closed without a strong JWT secret; G4 register 403 in public
mode; G5 /auth/me anonymous 401 (no dev_anon); G6 tightened public set.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from agent_server.auth import (
    AuthDB,
    auth_required_for_clients,
    jwt_auth_middleware,
    register_auth_routes,
    validate_public_mode_or_raise,
)

STRONG_SECRET = "x" * 64  # 64 chars — meets the >= 32 requirement


def _build_app(db_path, monkeypatch):
    monkeypatch.setenv("SUPEREZIO_JWT_SECRET", STRONG_SECRET)
    monkeypatch.setenv("SUPEREZIO_PUBLIC_MODE", "1")
    monkeypatch.setenv("SUPEREZIO_OPEN_ACCESS", "0")
    app = FastAPI()
    app.state.auth_db = AuthDB(db_path=db_path)
    register_auth_routes(app)

    @app.get("/protected")
    async def _protected(request: Request):
        return {"user_id": request.state.user.get("sub")}

    @app.get("/health")
    async def _health():
        return {"status": "ok"}

    @app.get("/")
    async def _root():
        return {"status": "ok"}

    @app.get("/metrics")
    async def _metrics():
        return {"status": "ok"}

    @app.get("/health/dashboard")
    async def _dashboard():
        return {"status": "ok"}

    @app.get("/api/health/dashboard-data")
    async def _dashboard_data():
        return {"status": "ok"}

    app.middleware("http")(jwt_auth_middleware)
    return app


@pytest.fixture
def public_client(tmp_path, monkeypatch):
    app = _build_app(tmp_path / "gate.db", monkeypatch)
    return TestClient(app)


def test_g3_boot_fails_without_strong_secret(monkeypatch):
    monkeypatch.setenv("SUPEREZIO_PUBLIC_MODE", "1")
    monkeypatch.setenv("SUPEREZIO_JWT_SECRET", "")
    with pytest.raises(RuntimeError, match="SUPEREZIO_JWT_SECRET"):
        validate_public_mode_or_raise()
    monkeypatch.setenv("SUPEREZIO_JWT_SECRET", "short")
    with pytest.raises(RuntimeError, match="32"):
        validate_public_mode_or_raise()
    monkeypatch.setenv("SUPEREZIO_JWT_SECRET", STRONG_SECRET)
    validate_public_mode_or_raise()  # no raise


def test_g1_g5_anonymous_gets_401_in_public_mode(public_client):
    assert public_client.get("/protected").status_code == 401
    assert public_client.get("/auth/me").status_code == 401


def test_g4_register_403_in_public_mode(public_client):
    resp = public_client.post(
        "/auth/register",
        json={"username": "intruder", "email": "i@x.com", "password": "p@ssw0rd123"},
    )
    assert resp.status_code == 403


def test_g4_register_reopens_with_explicit_flag(tmp_path, monkeypatch):
    monkeypatch.setenv("SUPEREZIO_PUBLIC_REGISTRATION", "1")
    app = _build_app(tmp_path / "gate2.db", monkeypatch)
    client = TestClient(app)
    resp = client.post(
        "/auth/register",
        json={"username": "oper", "email": "o@x.com", "password": "p@ssw0rd123"},
    )
    assert resp.status_code == 201


def test_g2_login_and_bearer_in_public_mode(public_client, tmp_path):
    db = public_client.app.state.auth_db
    db.create_user(username="admin", email="a@x.com", password="p@ssw0rd123")
    resp = public_client.post("/auth/login", json={"username": "admin", "password": "p@ssw0rd123"})
    assert resp.status_code == 200
    token = resp.json().get("access_token")
    assert token
    assert (
        public_client.get("/protected", headers={"Authorization": f"Bearer {token}"}).status_code
        == 200
    )


def test_g6_public_set_tightened(public_client):
    assert public_client.get("/health").status_code == 200
    assert public_client.get("/").status_code == 200
    assert public_client.get("/metrics").status_code == 401
    assert public_client.get("/health/dashboard").status_code == 401
    assert public_client.get("/api/health/dashboard-data").status_code == 401


def test_open_access_guest_passthrough(tmp_path, monkeypatch):
    """Operator flag: no login wall, registration still closed, trading untouched."""
    monkeypatch.setenv("SUPEREZIO_OPEN_ACCESS", "1")
    monkeypatch.setenv("SUPEREZIO_JWT_SECRET", STRONG_SECRET)
    monkeypatch.setenv("SUPEREZIO_PUBLIC_MODE", "1")
    assert auth_required_for_clients() is False

    app = FastAPI()
    app.state.auth_db = AuthDB(db_path=tmp_path / "open.db")
    register_auth_routes(app)

    @app.get("/protected")
    async def _protected(request: Request):
        return {"username": request.state.user.get("username")}

    app.middleware("http")(jwt_auth_middleware)
    client = TestClient(app)

    me = client.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["username"] == "guest_open"
    protected = client.get("/protected")
    assert protected.status_code == 200
    assert protected.json()["username"] == "guest_open"
    # Self-serve accounts stay closed even when the product is open.
    reg = client.post(
        "/auth/register",
        json={"username": "intruder", "email": "i@x.com", "password": "p@ssw0rd123"},
    )
    assert reg.status_code == 403


def test_open_access_off_still_requires_login(monkeypatch):
    monkeypatch.setenv("SUPEREZIO_OPEN_ACCESS", "0")
    monkeypatch.setenv("SUPEREZIO_JWT_SECRET", STRONG_SECRET)
    monkeypatch.setenv("SUPEREZIO_PUBLIC_MODE", "1")
    assert auth_required_for_clients() is True
