"""
JWT Auth — SQLite persistence, password hashing, token management
==================================================================
Thread-safe AuthDB singleton wired via get_auth_db().

REGRAS DE SEGURANCA:
  - Senhas nunca sao armazenadas em texto puro (bcrypt).
  - Refresh tokens armazenados como hash SHA-256.
  - Refresh token eh rotated (consumido e substituido) a cada uso.
  - JWT_SECRET deve vir de variavel de ambiente, nunca hardcoded.
  - Se SUPEREZIO_JWT_SECRET nao estiver configurado: RuntimeError na inicializacao.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
import threading as _threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import jwt
from passlib.context import CryptContext

from core.auth.models import TokenResponse, UserLogin, UserRegister

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ACCESS_TOKEN_TTL_MINUTES = 60  # 1 hour
_REFRESH_TOKEN_TTL_DAYS = 30
_JWT_ALGORITHM = "HS256"

# ---------------------------------------------------------------------------
# Password context (bcrypt)
# ---------------------------------------------------------------------------

_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _get_jwt_secret() -> str:
    secret = os.environ.get("SUPEREZIO_JWT_SECRET")
    if not secret:
        raise RuntimeError(
            "SUPEREZIO_JWT_SECRET environment variable is not set. "
            "Set a strong random secret before using JWT auth."
        )
    return secret


def _db_path() -> Path:
    base = Path(os.getenv("SUPEREZIO_DATA_DIR", "data"))
    base.mkdir(parents=True, exist_ok=True)
    return base / "auth.db"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# ---------------------------------------------------------------------------
# AuthDB
# ---------------------------------------------------------------------------


class AuthDB:
    """
    SQLite-backed authentication store.

    Thread-safe (connections are not shared across threads; each call
    opens its own connection via _connect).
    """

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = db_path or _db_path()
        self._init_db()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self) -> None:
        """Create tables if they don't exist."""
        # Import here to avoid circular dependency at package level
        from core.auth.models import USERS_SCHEMA  # noqa: F811

        with self._connect() as conn:
            conn.executescript(USERS_SCHEMA)

    # ------------------------------------------------------------------
    # User registration & authentication
    # ------------------------------------------------------------------

    def register(self, payload: UserRegister) -> Dict[str, Any]:
        """
        Register a new user.

        Raises ValueError if username or email already exists.
        Returns the created user row as a dict (without password_hash).
        """
        password_hash = _pwd_ctx.hash(payload.password)
        now = _now_iso()

        with self._connect() as conn:
            try:
                cur = conn.execute(
                    """
                    INSERT INTO users (username, email, password_hash, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (payload.username, payload.email, password_hash, now),
                )
            except sqlite3.IntegrityError as exc:
                msg = str(exc).lower()
                if "username" in msg:
                    raise ValueError(f"Username '{payload.username}' already exists") from exc
                if "email" in msg:
                    raise ValueError(f"Email '{payload.email}' already exists") from exc
                raise

            row = conn.execute(
                "SELECT id, username, email, role, is_active, created_at, last_login "
                "FROM users WHERE id=?",
                (cur.lastrowid,),
            ).fetchone()

        return dict(row)

    def authenticate(self, payload: UserLogin) -> Dict[str, Any]:
        """
        Verify credentials and return user dict (without password_hash).

        Raises ValueError on invalid username or password.
        Raises RuntimeError if user account is inactive.
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE username=?",
                (payload.username,),
            ).fetchone()

        if row is None:
            raise ValueError("Invalid username or password")

        user = dict(row)

        if not _pwd_ctx.verify(payload.password, user["password_hash"]):
            raise ValueError("Invalid username or password")

        if not user["is_active"]:
            raise RuntimeError("Account is disabled")

        # Update last_login
        now = _now_iso()
        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET last_login=? WHERE id=?",
                (now, user["id"]),
            )

        user.pop("password_hash", None)
        return user

    def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Return user dict (without password_hash) or None."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, username, email, role, is_active, created_at, last_login "
                "FROM users WHERE id=?",
                (user_id,),
            ).fetchone()
        return dict(row) if row else None

    # ------------------------------------------------------------------
    # JWT access tokens
    # ------------------------------------------------------------------

    def create_access_token(self, user: Dict[str, Any]) -> str:
        """
        Create a short-lived JWT access token.

        The token encodes: sub (user_id), username, role, exp, iat.
        """
        secret = _get_jwt_secret()
        now = datetime.now(timezone.utc)
        payload = {
            "sub": str(user["id"]),
            "username": user["username"],
            "role": user.get("role", "user"),
            "iat": now,
            "exp": now + timedelta(minutes=_ACCESS_TOKEN_TTL_MINUTES),
        }
        return jwt.encode(payload, secret, algorithm=_JWT_ALGORITHM)

    def decode_token(self, token: str) -> Dict[str, Any]:
        """
        Decode and validate a JWT access token.

        Returns the decoded payload.
        Raises jwt.PyJWTError on invalid/expired token.
        """
        secret = _get_jwt_secret()
        return jwt.decode(token, secret, algorithms=[_JWT_ALGORITHM])

    # ------------------------------------------------------------------
    # Refresh tokens (rotation-based)
    # ------------------------------------------------------------------

    def _generate_refresh_token(self) -> str:
        """Generate a cryptographically secure random token."""
        return secrets.token_urlsafe(48)

    def create_refresh_token(self, user_id: int) -> str:
        """
        Create a new refresh token, store its SHA-256 hash in the database.

        Returns the raw token string (only returned once at creation time).
        """
        raw = self._generate_refresh_token()
        token_hash = _hash_token(raw)
        now = _now_iso()
        expires_at = (
            datetime.now(timezone.utc) + timedelta(days=_REFRESH_TOKEN_TTL_DAYS)
        ).isoformat()

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO refresh_tokens (user_id, token_hash, expires_at, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, token_hash, expires_at, now),
            )

        return raw

    def consume_refresh_token(self, raw_token: str) -> Dict[str, Any]:
        """
        Validate and consume (delete) a refresh token.

        This enforces refresh token rotation: a token can only be used once.
        Returns the associated user dict (without password_hash).

        Raises ValueError if token is invalid, expired, or not found.
        """
        token_hash = _hash_token(raw_token)

        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM refresh_tokens WHERE token_hash=?",
                (token_hash,),
            ).fetchone()

            if row is None:
                raise ValueError("Invalid refresh token")

            token_data = dict(row)

            # Check expiry
            expires_at = datetime.fromisoformat(token_data["expires_at"])
            if expires_at < datetime.now(timezone.utc):
                # Clean up expired token
                conn.execute("DELETE FROM refresh_tokens WHERE id=?", (token_data["id"],))
                raise ValueError("Refresh token has expired")

            # Delete the consumed token (rotation)
            conn.execute("DELETE FROM refresh_tokens WHERE id=?", (token_data["id"],))

        # Fetch user
        user = self.get_user_by_id(token_data["user_id"])
        if user is None:
            raise ValueError("User not found")
        if not user["is_active"]:
            raise RuntimeError("Account is disabled")

        return user

    def rotate_refresh_token(self, raw_token: str) -> TokenResponse:
        """
        Consume the old refresh token and issue a new access + refresh pair.

        This is the primary method for token refresh endpoints.
        """
        user = self.consume_refresh_token(raw_token)
        access_token = self.create_access_token(user)
        new_refresh_token = self.create_refresh_token(user["id"])

        return TokenResponse(
            access_token=access_token,
            refresh_token=new_refresh_token,
        )

    def login(self, payload: UserLogin) -> TokenResponse:
        """
        Authenticate user and return a full token pair.

        Convenience wrapper around authenticate + create_access_token +
        create_refresh_token.
        """
        user = self.authenticate(payload)
        access_token = self.create_access_token(user)
        refresh_token = self.create_refresh_token(user["id"])

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
        )

    def register_and_login(self, payload: UserRegister) -> TokenResponse:
        """
        Register a new user and immediately return a token pair.

        Convenience wrapper for signup flows.
        """
        user = self.register(payload)
        access_token = self.create_access_token(user)
        refresh_token = self.create_refresh_token(user["id"])

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
        )


# ---------------------------------------------------------------------------
# Thread-safe singleton
# ---------------------------------------------------------------------------

_db: AuthDB | None = None
_db_lock: _threading.Lock = _threading.Lock()


def get_auth_db() -> AuthDB:
    """Return the shared AuthDB singleton (thread-safe)."""
    global _db
    if _db is None:
        with _db_lock:
            if _db is None:
                _db = AuthDB()
    return _db
