"""
JWT Authentication Module for SuperEzio F51 Bootstrap.

Provides:
  - JWT middleware for request authentication
  - /auth/* endpoints (register, login, refresh, me)
  - SQLite-backed user and refresh token storage
  - Dev mode fallback when SUPEREZIO_JWT_SECRET is not configured
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import jwt as _jwt
from fastapi import HTTPException, Request, Response
from passlib.context import CryptContext
from pydantic import BaseModel, field_validator

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7

_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

_AUTH_DB_DIR = Path(__file__).resolve().parent.parent.parent / "runtime"
_AUTH_DB_PATH = _AUTH_DB_DIR / "auth.db"

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class UserCreate(BaseModel):
    """Payload for POST /auth/register."""

    username: str
    email: str
    password: str

    @field_validator("username")
    @classmethod
    def _validate_username(cls, v: str) -> str:
        stripped = v.strip()
        if len(stripped) < 3 or len(stripped) > 64:
            raise ValueError("username must be 3-64 characters")
        return stripped

    @field_validator("email")
    @classmethod
    def _validate_email(cls, v: str) -> str:
        if "@" not in v or len(v) > 120:
            raise ValueError("invalid email")
        return v.strip()

    @field_validator("password")
    @classmethod
    def _validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("password must be at least 8 characters")
        return v


class LoginRequest(BaseModel):
    """Payload for POST /auth/login."""

    username: str
    password: str


class UserResponse(BaseModel):
    """Public user representation (no password hash)."""

    id: int
    username: str
    email: str
    created_at: str


class TokenResponse(BaseModel):
    """JWT token pair response."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = ACCESS_TOKEN_EXPIRE_MINUTES * 60


class TokenRefresh(BaseModel):
    """Payload for POST /auth/refresh."""

    refresh_token: str


# ---------------------------------------------------------------------------
# Auth DB — SQLite store for users and refresh tokens
# ---------------------------------------------------------------------------


class AuthDB:
    """SQLite-backed store for users and refresh tokens.

    Path defaults to ``runtime/auth.db`` relative to the project root.
    Thread-safe for single-process use; not designed for multi-worker
    deployments without a shared SQLite or a real RDBMS.
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or _AUTH_DB_PATH
        self._ensure_db()

    # -- internals ----------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _ensure_db(self) -> None:
        conn = self._connect()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL COLLATE NOCASE,
                    email TEXT UNIQUE NOT NULL COLLATE NOCASE,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
                );
                CREATE TABLE IF NOT EXISTS refresh_tokens (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    token_hash TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    used INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
                    FOREIGN KEY (user_id) REFERENCES users(id)
                );
                CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
                CREATE INDEX IF NOT EXISTS idx_refresh_tokens_hash ON refresh_tokens(token_hash);
            """)
            conn.commit()
        finally:
            conn.close()

    # -- users --------------------------------------------------------------

    def create_user(self, username: str, email: str, password: str) -> dict[str, Any]:
        """Insert a new user. Raises HTTPException 409 on duplicate."""
        password_hash = _pwd_ctx.hash(password)
        conn = self._connect()
        try:
            cur = conn.execute(
                "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
                (username, email, password_hash),
            )
            conn.commit()
            row = conn.execute(
                "SELECT id, username, email, created_at FROM users WHERE id = ?",
                (cur.lastrowid,),
            ).fetchone()
            return dict(row)
        except sqlite3.IntegrityError as exc:
            detail = str(exc)
            if "username" in detail:
                raise HTTPException(status_code=409, detail="Username already exists")
            if "email" in detail:
                raise HTTPException(status_code=409, detail="Email already registered")
            raise HTTPException(status_code=409, detail="Registration conflict")
        finally:
            conn.close()

    def get_user_by_username(self, username: str) -> dict[str, Any] | None:
        """Lookup user by username (case-insensitive). Returns None if not found."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT id, username, email, password_hash, created_at FROM users WHERE username = ?",
                (username,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_user_by_id(self, user_id: int) -> dict[str, Any] | None:
        """Lookup user by primary key. Returns None if not found."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT id, username, email, created_at FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    # -- refresh tokens -----------------------------------------------------

    def store_refresh_token(self, user_id: int, token_hash: str, expires_at: str) -> None:
        conn = self._connect()
        try:
            conn.execute(
                "INSERT INTO refresh_tokens (user_id, token_hash, expires_at) VALUES (?, ?, ?)",
                (user_id, token_hash, expires_at),
            )
            conn.commit()
        finally:
            conn.close()

    def consume_refresh_token(self, token_hash: str) -> dict[str, Any] | None:
        """Consume (mark used) a refresh token.

        Returns token data dict on success, ``{"already_used": True}`` if the
        token was already consumed (potential theft), or ``None`` if the token
        does not exist or has expired.
        """
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT id, user_id, token_hash, expires_at, used FROM refresh_tokens WHERE token_hash = ?",
                (token_hash,),
            ).fetchone()
            if not row:
                return None
            token = dict(row)
            if token["used"]:
                return {"already_used": True, "user_id": token["user_id"]}
            if datetime.fromisoformat(token["expires_at"]) < datetime.now(timezone.utc):
                return None
            conn.execute("UPDATE refresh_tokens SET used = 1 WHERE id = ?", (token["id"],))
            conn.commit()
            return token
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------


def _get_secret() -> str:
    return os.getenv("SUPEREZIO_JWT_SECRET", "")


def _is_dev_mode() -> bool:
    return not bool(_get_secret())


def _create_access_token(user_id: int, username: str) -> str:
    secret = _get_secret()
    payload = {
        "sub": str(user_id),
        "username": username,
        "iat": int(time.time()),
        "exp": int(time.time()) + ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "type": "access",
    }
    return _jwt.encode(payload, secret, algorithm=ALGORITHM)


def _create_refresh_token(user_id: int) -> tuple[str, str, str]:
    """Generate a single-use refresh token.

    Returns ``(raw_token, sha256_hash, expires_at_iso)``.
    """
    token = secrets.token_urlsafe(48)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    expires_at = (datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    return token, token_hash, expires_at


def _decode_access_token(token: str) -> dict[str, Any] | None:
    """Decode and validate an access token. Returns the payload or None."""
    secret = _get_secret()
    try:
        payload = _jwt.decode(token, secret, algorithms=[ALGORITHM])
        if payload.get("type") != "access":
            return None
        return payload
    except _jwt.ExpiredSignatureError:
        return None
    except _jwt.InvalidTokenError:
        return None


# ---------------------------------------------------------------------------
# Public-path check (mirrors the set in main.py)
# ---------------------------------------------------------------------------
_PUBLIC_EXACT = frozenset({"/health", "/favicon.ico", "/", "/metrics"})
_PUBLIC_PREFIXES = frozenset({"/frontend", "/css", "/js"})
# /auth/register, /auth/login, and /auth/refresh are public (no JWT needed).
# /auth/me requires authentication and is NOT included here.
_PUBLIC_AUTH_PATHS = frozenset({"/auth/register", "/auth/login", "/auth/refresh"})


def _is_public_path(path: str) -> bool:
    """Return True if *path* is a public route that requires no auth."""
    if path in _PUBLIC_EXACT:
        return True
    if any(path == p or path.startswith(p + "/") for p in _PUBLIC_PREFIXES):
        return True
    if path in _PUBLIC_AUTH_PATHS:
        return True
    return False


# ---------------------------------------------------------------------------
# JWT middleware
# ---------------------------------------------------------------------------


async def jwt_auth_middleware(request: Request, call_next):
    """JWT authentication middleware.

    Behaviour
    ---------
    * Public routes (same set as ``api_key_auth_middleware`` plus ``/auth/*``):
      pass through without authentication.
    * Dev mode (``SUPEREZIO_JWT_SECRET`` empty / not set): inject an anonymous
      user into ``request.state.user`` and pass through.
    * Production: extract the ``Bearer`` token from the ``Authorization``
      header, validate it, and inject the decoded payload into
      ``request.state.user``.

    Expected to be added **after** ``api_key_auth_middleware`` so that routes
    protected by the API key still run first.
    """
    path = request.url.path

    # Public routes — skip auth entirely.
    if _is_public_path(path):
        return await call_next(request)

    # Dev mode — inject anonymous user.
    if _is_dev_mode():
        request.state.user = {
            "id": 0,
            "sub": "0",
            "username": "dev_anon",
            "role": "dev",
            "type": "access",
        }
        return await call_next(request)

    # Extract Bearer token.
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return Response(
            status_code=401,
            content=json.dumps({"error": "Missing or invalid Authorization header"}),
            media_type="application/json",
        )

    token = auth_header.removeprefix("Bearer ").strip()
    if not token:
        return Response(
            status_code=401,
            content=json.dumps({"error": "Empty token"}),
            media_type="application/json",
        )

    payload = _decode_access_token(token)
    if payload is None:
        return Response(
            status_code=401,
            content=json.dumps({"error": "Invalid or expired token"}),
            media_type="application/json",
        )

    request.state.user = payload
    return await call_next(request)


# ---------------------------------------------------------------------------
# Auth routes — /auth/* endpoints
# ---------------------------------------------------------------------------
# NOTE: We do NOT use APIRouter here because FastAPI 0.139.0 + Starlette 1.3.1
# has a known _IncludedRouter bug that causes all prefixed included routes to
# return 404 at runtime. Instead we register routes directly on the app object
# via register_auth_routes().
# See: https://github.com/fastapi/fastapi/issues/12692


def _get_auth_db(request: Request) -> AuthDB:
    db = getattr(request.app.state, "auth_db", None)
    if db is None:
        raise HTTPException(status_code=500, detail="AuthDB not initialized")
    return db


def register_auth_routes(app: "FastAPI") -> None:
    """Register /auth/* routes directly on the FastAPI application.

    This bypasses the ``_IncludedRouter`` bug in FastAPI 0.139.0 /
    Starlette 1.3.1 by adding each route via the standard ``@app.xxx``
    decorator pattern instead of ``app.include_router(APIRouter(prefix=...))``.
    """

    # Import FastAPI here to avoid circular imports at module level
    from fastapi import FastAPI as _FastAPI

    # Use a local app reference to satisfy the type checker
    _app: _FastAPI = app

    @_app.post("/auth/register", status_code=201)
    async def register(body: UserCreate, request: Request) -> UserResponse:
        """Register a new user account.

        Returns 201 with the public user profile on success.
        Returns 409 if the username or email is already taken.
        """
        db = _get_auth_db(request)
        user = db.create_user(
            username=body.username,
            email=body.email,
            password=body.password,
        )
        return UserResponse(
            id=user["id"],
            username=user["username"],
            email=user["email"],
            created_at=user["created_at"],
        )

    @_app.post("/auth/login")
    async def login(body: LoginRequest, request: Request) -> TokenResponse:
        """Authenticate with username and password.

        Returns an access token (short-lived) and a single-use refresh token.
        """
        db = _get_auth_db(request)
        user = db.get_user_by_username(body.username)
        if user is None:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        # Constant-time comparison for password verification (handled by passlib).
        if not _pwd_ctx.verify(body.password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid credentials")

        access_token = _create_access_token(user["id"], user["username"])
        refresh_token, refresh_hash, expires_at = _create_refresh_token(user["id"])
        db.store_refresh_token(user["id"], refresh_hash, expires_at)

        return TokenResponse(access_token=access_token, refresh_token=refresh_token)

    @_app.post("/auth/refresh")
    async def refresh(body: TokenRefresh, request: Request) -> TokenResponse:
        """Rotate a refresh token (single-use).

        On success returns a new access token **and** a new refresh token.
        The old refresh token is revoked. If the same refresh token is presented
        twice, the request is rejected (potential theft indicator).
        """
        db = _get_auth_db(request)
        token_hash = hashlib.sha256(body.refresh_token.encode()).hexdigest()
        token_data = db.consume_refresh_token(token_hash)

        if token_data is None:
            raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

        if token_data.get("already_used"):
            logger.warning(
                "Refresh token reuse detected for user_id=%s — possible token theft",
                token_data.get("user_id"),
            )
            raise HTTPException(status_code=401, detail="Refresh token already used")

        user = db.get_user_by_id(token_data["user_id"])
        if user is None:
            raise HTTPException(status_code=401, detail="User not found")

        access_token = _create_access_token(user["id"], user["username"])
        new_refresh_token, new_refresh_hash, new_expires_at = _create_refresh_token(user["id"])
        db.store_refresh_token(user["id"], new_refresh_hash, new_expires_at)

        return TokenResponse(access_token=access_token, refresh_token=new_refresh_token)

    @_app.get("/auth/me")
    async def me(request: Request) -> UserResponse:
        """Return the currently authenticated user's public profile."""
        user = getattr(request.state, "user", None)
        if user is None:
            raise HTTPException(status_code=401, detail="Not authenticated")

        raw_id = user.get("id") or user.get("sub")
        try:
            user_id = int(raw_id) if raw_id is not None else 0
        except (ValueError, TypeError):
            user_id = 0

        if user_id == 0:
            # Dev-mode anonymous user.
            return UserResponse(
                id=0,
                username=str(user.get("username", "dev_anon")),
                email="dev@local",
                created_at="",
            )

        db = _get_auth_db(request)
        db_user = db.get_user_by_id(user_id)
        if db_user is None:
            raise HTTPException(status_code=404, detail="User not found")

        return UserResponse(
            id=db_user["id"],
            username=db_user["username"],
            email=db_user["email"],
            created_at=db_user["created_at"],
        )
