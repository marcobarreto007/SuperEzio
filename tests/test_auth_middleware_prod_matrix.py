"""WS-A slice (P0 auth): prod-like auth matrix against the REAL agent_server.main.

Contract pinned here (the single auth source lives in the middleware
registration of src/agent_server/main.py plus the /health identity block
there, with the public-route set and the guest/dev passthrough decided in
src/agent_server/auth.py):

* Protected GET routes (/auth/me, /cockpit/summary, /task/active,
  /trades/history) return 401 without a Bearer token and 200 with a valid
  one in prod-like mode (SUPEREZIO_JWT_SECRET >= 32 chars, no open access).
* /health reports ``auth_required`` honestly per mode: false in dev mode /
  open access, true in prod-like / public mode.
* Public routes (/health, /auth/login, /auth/refresh, /favicon.ico) never
  401 because of a missing Bearer in prod-like; /auth/me is never public.

Why the real app: the value of this slice is pinning that main.py's actual
middleware chain keeps every non-public route fail-closed and that the route
surface registered on the real app is what the contract says it is. A
synthetic FastAPI app would prove nothing about the production registration
order.

The app lifespan is NOT entered (plain TestClient, no context manager — same
as tests/test_api_routes_sync.py): no pipeline/broker services are needed to
pin an HTTP auth contract, and /health probes stay deterministic. The
app.state entries used by the handlers under test are pointed at test doubles
and restored afterwards, so sibling test modules are unaffected.
"""

from __future__ import annotations

import time
from typing import Any

import jwt as pyjwt
import pytest
from fastapi.testclient import TestClient

# >= 32 chars, as required for prod-like deployments.
STRONG_SECRET = "pytest-prod-like-secret-" + ("x" * 48)
ALGORITHM = "HS256"

PROTECTED_GET_ROUTES = [
    "/auth/me",
    "/cockpit/summary",
    "/task/active",
    "/trades/history",
]
# Routes that must never be gated by the JWT wall in any prod-like mode.
PUBLIC_ROUTES_NOT_401 = [
    ("/health", "get", None),
    ("/favicon.ico", "get", None),
    ("/auth/login", "post", {}),
    ("/auth/refresh", "post", {}),
]


# ---------------------------------------------------------------------------
# Mode fixtures — auth policy is read from the environment on every request,
# so per-test monkeypatching is enough (no module import-order coupling).
# ---------------------------------------------------------------------------


def _set_auth_mode(
    monkeypatch: pytest.MonkeyPatch,
    *,
    secret: str,
    open_access: str,
    public: str,
) -> None:
    monkeypatch.setenv("SUPEREZIO_JWT_SECRET", secret)
    monkeypatch.setenv("SUPEREZIO_OPEN_ACCESS", open_access)
    monkeypatch.setenv("SUPEREZIO_PUBLIC_MODE", public)


@pytest.fixture
def dev_mode(monkeypatch) -> None:
    """No secret: dev passthrough with a guest identity."""
    _set_auth_mode(monkeypatch, secret="", open_access="0", public="0")


@pytest.fixture
def open_access_mode(monkeypatch) -> None:
    """Operator opt-in anonymous access: no login wall."""
    _set_auth_mode(monkeypatch, secret=STRONG_SECRET, open_access="1", public="0")


@pytest.fixture
def prod_like_mode(monkeypatch) -> None:
    """Strong secret, no open access: the auth wall is up."""
    _set_auth_mode(monkeypatch, secret=STRONG_SECRET, open_access="0", public="0")


@pytest.fixture
def public_mode(monkeypatch) -> None:
    """Public-facing deployment: strong secret, tightened anonymous surface."""
    _set_auth_mode(monkeypatch, secret=STRONG_SECRET, open_access="0", public="1")


@pytest.fixture(params=["prod_like", "public_mode"])
def wall_mode(request: pytest.FixtureRequest, monkeypatch) -> None:
    """One of the two prod-like modes (wall up), parametrized."""
    _set_auth_mode(
        monkeypatch,
        secret=STRONG_SECRET,
        open_access="0",
        public="1" if request.param == "public_mode" else "0",
    )


# ---------------------------------------------------------------------------
# Real-app client fixture
# ---------------------------------------------------------------------------


class _NoopPipeline:
    """Stand-in for app.state.pipeline: /health only checks it is not None."""

    def get_status(self) -> dict[str, Any]:
        return {"status": "ok", "nodes": []}


class _HealthyBody:
    """Stand-in for Bob's body during the /health consciousness probe."""

    def is_man_at_work(self) -> bool:
        return False

    @property
    def organs(self) -> dict[str, Any]:
        return {}


@pytest.fixture
def real_client(tmp_path, monkeypatch):
    """TestClient bound to the real agent_server.main app, no lifespan.

    app.state.auth_db points at a throwaway SQLite (never the operator's
    runtime/auth.db); app.state.pipeline and the /health consciousness probe
    are test doubles; both are restored on teardown.
    """
    from agent_server.auth import AuthDB
    from agent_server.main import app

    original_auth_db = getattr(app.state, "auth_db", None)
    had_pipeline = hasattr(app.state, "pipeline")
    original_pipeline = getattr(app.state, "pipeline", None)

    app.state.auth_db = AuthDB(db_path=tmp_path / "auth-matrix.db")
    app.state.pipeline = _NoopPipeline()

    import core.bob_consciousness as consciousness

    monkeypatch.setattr(consciousness, "get_bobs_body", lambda: _HealthyBody())

    yield TestClient(app)

    if original_auth_db is None:
        if hasattr(app.state, "auth_db"):
            delattr(app.state, "auth_db")
    else:
        app.state.auth_db = original_auth_db
    if had_pipeline:
        app.state.pipeline = original_pipeline
    elif hasattr(app.state, "pipeline"):
        delattr(app.state, "pipeline")


def _seed_user(client: TestClient) -> dict[str, Any]:
    """Create one user directly in the throwaway AuthDB (no /auth/* call)."""
    db = client.app.state.auth_db
    return db.create_user(
        username="alice",
        email="alice@example.com",
        password="AliceP@ssw0rd!",
    )


def _mint_access_token(*, user_id: int, username: str) -> str:
    """Mint an access JWT with the same claims auth.py uses."""
    now = int(time.time())
    return pyjwt.encode(
        {
            "sub": str(user_id),
            "username": username,
            "iat": now,
            "exp": now + 30 * 60,
            "type": "access",
        },
        STRONG_SECRET,
        algorithm=ALGORITHM,
    )


# ---------------------------------------------------------------------------
# (a) Prod-like: protected routes 401 without Bearer / 200 with valid Bearer
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", PROTECTED_GET_ROUTES)
class TestProdLikeProtectedRoutes:
    @pytest.fixture(autouse=True)
    def _prod_like(self, prod_like_mode) -> None:
        pass

    def test_returns_401_without_bearer(self, real_client: TestClient, path: str) -> None:
        resp = real_client.get(path)
        assert resp.status_code == 401, (
            f"{path} must be fail-closed in prod-like mode, got {resp.status_code}"
        )

    def test_returns_200_with_valid_bearer(self, real_client: TestClient, path: str) -> None:
        profile = _seed_user(real_client)
        token = _mint_access_token(user_id=profile["id"], username=profile["username"])
        resp = real_client.get(path, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200, (
            f"{path} with a valid Bearer must pass the wall, got {resp.status_code}: "
            f"{resp.text[:200]}"
        )

    def test_returns_401_with_invalid_bearer(self, real_client: TestClient, path: str) -> None:
        resp = real_client.get(path, headers={"Authorization": "Bearer not-a-real-jwt-token"})
        assert resp.status_code == 401


@pytest.mark.parametrize("path", PROTECTED_GET_ROUTES)
class TestPublicModeProtectedRoutes:
    """Same wall under SUPEREZIO_PUBLIC_MODE=1 (tightened anonymous surface)."""

    @pytest.fixture(autouse=True)
    def _public(self, public_mode) -> None:
        pass

    def test_returns_401_without_bearer(self, real_client: TestClient, path: str) -> None:
        assert real_client.get(path).status_code == 401


# ---------------------------------------------------------------------------
# (c) Public routes never 401 for a missing Bearer in prod-like
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path,method,body",
    PUBLIC_ROUTES_NOT_401,
    ids=[row[0] for row in PUBLIC_ROUTES_NOT_401],
)
class TestPublicSurfaceNever401ProdLike:
    """Login/refresh reach the handler (422 on empty body beats any 401)."""

    @pytest.fixture(autouse=True)
    def _prod_like(self, prod_like_mode) -> None:
        pass

    def test_public_route_not_blocked(
        self, real_client: TestClient, path: str, method: str, body: dict | None
    ) -> None:
        kwargs = {"json": body} if body is not None else {}
        resp = getattr(real_client, method)(path, **kwargs)
        assert resp.status_code != 401, f"{method.upper()} {path} must never 401 on auth"


@pytest.mark.parametrize(
    "path,method,body",
    PUBLIC_ROUTES_NOT_401,
    ids=[row[0] for row in PUBLIC_ROUTES_NOT_401],
)
class TestPublicSurfaceNever401PublicMode:
    """The tightened public set still keeps auth paths + liveness + favicon open."""

    @pytest.fixture(autouse=True)
    def _public(self, public_mode) -> None:
        pass

    def test_public_route_not_blocked(
        self, real_client: TestClient, path: str, method: str, body: dict | None
    ) -> None:
        kwargs = {"json": body} if body is not None else {}
        resp = getattr(real_client, method)(path, **kwargs)
        assert resp.status_code != 401, f"{method.upper()} {path} must never 401 on auth"


# ---------------------------------------------------------------------------
# (c) /auth/me is never public — only a valid Bearer opens it
# ---------------------------------------------------------------------------


class TestAuthMeNeverPublic:
    """Runs under both prod-like and public mode (wall_mode parametrization)."""

    def test_anonymous_401(self, real_client: TestClient, wall_mode) -> None:
        assert real_client.get("/auth/me").status_code == 401

    def test_invalid_bearer_401(self, real_client: TestClient, wall_mode) -> None:
        resp = real_client.get("/auth/me", headers={"Authorization": "Bearer garbage-token"})
        assert resp.status_code == 401

    def test_wrong_secret_bearer_401(self, real_client: TestClient, wall_mode) -> None:
        # Signed with another key: same wall as a missing token.
        now = int(time.time())
        forged = pyjwt.encode(
            {"sub": "1", "username": "alice", "iat": now, "exp": now + 1800, "type": "access"},
            "forged-secret-not-the-server-one",
            algorithm=ALGORITHM,
        )
        resp = real_client.get("/auth/me", headers={"Authorization": f"Bearer {forged}"})
        assert resp.status_code == 401

    def test_valid_bearer_200(self, real_client: TestClient, wall_mode) -> None:
        profile = _seed_user(real_client)
        token = _mint_access_token(user_id=profile["id"], username=profile["username"])
        resp = real_client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["username"] == "alice"


# ---------------------------------------------------------------------------
# (b) /health.auth_required is honest per mode (main.py /health identity)
# ---------------------------------------------------------------------------


class TestHealthAuthRequiredSignal:
    @pytest.mark.parametrize(
        "mode_fixture,expected",
        [
            pytest.param("dev_mode", False, id="dev_mode"),
            pytest.param("open_access_mode", False, id="open_access_mode"),
            pytest.param("prod_like_mode", True, id="prod_like_mode"),
            pytest.param("public_mode", True, id="public_mode"),
        ],
    )
    def test_health_signal_honest(
        self,
        real_client: TestClient,
        request: pytest.FixtureRequest,
        mode_fixture: str,
        expected: bool,
    ) -> None:
        request.getfixturevalue(mode_fixture)
        resp = real_client.get("/health")
        assert resp.status_code == 200, resp.text[:200]
        data = resp.json()
        assert data["status"] == "ok"
        assert data["auth_required"] is expected, (
            f"/health must report auth_required={expected} in this mode, "
            f"got {data['auth_required']}"
        )


# ---------------------------------------------------------------------------
# Wall toggles off in dev / open access (same real middleware, no secret / opt-in)
# ---------------------------------------------------------------------------


class TestWallDownDevAndOpenAccess:
    def test_dev_mode_guest_passthrough(self, real_client: TestClient, dev_mode) -> None:
        resp = real_client.get("/auth/me")
        assert resp.status_code == 200
        assert resp.json()["username"] == "dev_anon"

    def test_open_access_guest_passthrough(self, real_client: TestClient, open_access_mode) -> None:
        resp = real_client.get("/auth/me")
        assert resp.status_code == 200
        assert resp.json()["username"] == "guest_open"
