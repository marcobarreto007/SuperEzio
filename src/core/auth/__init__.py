"""
core.auth — JWT Authentication Layer
======================================
Submodules:
  - models   : Pydantic schemas (UserRegister, UserLogin, TokenResponse, RefreshRequest)
               and SQLite schema string (USERS_SCHEMA)
  - service  : AuthDB — SQLite persistence, password hashing, JWT token management

Usage:
    from core.auth import AuthDB, get_auth_db
    from core.auth.models import UserRegister, UserLogin, TokenResponse, USERS_SCHEMA

The AuthDB singleton is thread-safe and wired via get_auth_db().
JWT_SECRET must be set via SUPEREZIO_JWT_SECRET env var.
"""

from .models import RefreshRequest, TokenResponse, UserLogin, UserRegister, USERS_SCHEMA
from .service import AuthDB, get_auth_db

__all__ = [
    "AuthDB",
    "get_auth_db",
    "UserRegister",
    "UserLogin",
    "TokenResponse",
    "RefreshRequest",
    "USERS_SCHEMA",
]
