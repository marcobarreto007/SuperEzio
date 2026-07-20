"""
JWT Auth — Pydantic schemas and SQLite schema
==============================================
Request/response models for user registration, login, and token refresh.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class UserRegister(BaseModel):
    """Payload for POST /auth/register."""

    username: str = Field(min_length=3, max_length=32, pattern=r"^[a-zA-Z0-9_]+$")
    email: str = Field(min_length=5, max_length=128)
    password: str = Field(min_length=8, max_length=128)


class UserLogin(BaseModel):
    """Payload for POST /auth/login."""

    username: str
    password: str


class TokenResponse(BaseModel):
    """Response returned after successful login or token refresh."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 3600


class RefreshRequest(BaseModel):
    """Payload for POST /auth/refresh."""

    refresh_token: str


# ---------------------------------------------------------------------------
# SQLite schema
# ---------------------------------------------------------------------------

USERS_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    last_login TEXT
);
CREATE TABLE IF NOT EXISTS refresh_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""
