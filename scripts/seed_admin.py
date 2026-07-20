#!/usr/bin/env python3
"""
Seed Admin — Create the initial admin user for SuperEzio.

Creates a privileged admin account in the auth database used by the
FastAPI server.  The admin user gets role='admin' and can access all
JWT-protected routes.

Usage:
    python scripts/seed_admin.py --username admin --email admin@superezio.com --password StrongPass123!

Environment variables (fallback when flags are omitted):
    SUPEREZIO_ADMIN_USERNAME    (default: admin)
    SUPEREZIO_ADMIN_EMAIL       (default: admin@superezio.com)
    SUPEREZIO_ADMIN_PASSWORD    (required if not passed via --password)

The auth database defaults to SUPEREZIO_DATA_DIR/auth.db (or runtime/auth.db
if SUPEREZIO_DATA_DIR is not set), which matches the path used by the running
server.  Use --db-path to point to a different location.

Prerequisites:
  - Python 3.11+
  - Package installed (``pip install -e .``) so that ``core.auth`` is importable.
  - ``SUPEREZIO_JWT_SECRET`` must be set in the environment or .env.local
    (otherwise AuthDB cannot create tokens, but user creation itself still works).
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Ensure src/ is on sys.path so that core.auth is importable from scripts/
# ---------------------------------------------------------------------------
_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from core.auth import AuthDB  # noqa: E402
from core.auth.models import UserRegister  # noqa: E402

# ---------------------------------------------------------------------------
# Arg parsing
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed the initial admin user for SuperEzio.",
    )
    parser.add_argument(
        "--username",
        default=None,
        help="Admin username (3-32 chars, alphanumeric+underscore). "
        "Env: SUPEREZIO_ADMIN_USERNAME. Default: admin.",
    )
    parser.add_argument(
        "--email",
        default=None,
        help="Admin email address. Env: SUPEREZIO_ADMIN_EMAIL. Default: admin@superezio.com.",
    )
    parser.add_argument(
        "--password",
        default=None,
        help="Admin password (min 8 chars). Env: SUPEREZIO_ADMIN_PASSWORD. "
        "Required if not set via env.",
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help="Path to auth.db. Defaults to SUPEREZIO_DATA_DIR/auth.db or runtime/auth.db.",
    )
    return parser.parse_args(argv)


# ---------------------------------------------------------------------------
# Credential resolution
# ---------------------------------------------------------------------------


def _resolve_credentials(args: argparse.Namespace) -> tuple[str, str, str]:
    """Resolve username / email / password from args or env, with fallback defaults."""
    username = args.username or os.getenv("SUPEREZIO_ADMIN_USERNAME") or "admin"
    email = args.email or os.getenv("SUPEREZIO_ADMIN_EMAIL") or "admin@superezio.com"
    password = args.password or os.getenv("SUPEREZIO_ADMIN_PASSWORD")

    if not password:
        print("ERROR: --password (or SUPEREZIO_ADMIN_PASSWORD) is required.", file=sys.stderr)
        print("       Run with --help for details.", file=sys.stderr)
        sys.exit(1)

    return username, email, password


# ---------------------------------------------------------------------------
# Auth DB path
# ---------------------------------------------------------------------------


def _resolve_db_path(args: argparse.Namespace) -> Path:
    if args.db_path:
        return Path(args.db_path)
    data_dir = os.getenv("SUPEREZIO_DATA_DIR", "runtime")
    return Path(data_dir) / "auth.db"


# ---------------------------------------------------------------------------
# Promote user to admin role
# ---------------------------------------------------------------------------


def _ensure_role_column(db_path: Path) -> None:
    """Add ``role`` column if it doesn't exist (schema migration for older DBs)."""
    try:
        conn = sqlite3.connect(str(db_path))
        conn.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'")
        conn.commit()
        conn.close()
    except sqlite3.OperationalError:
        # Column already exists — nothing to do.
        pass


def _promote_to_admin(db_path: Path, user_id: int) -> None:
    """Set the user's role to 'admin'."""
    _ensure_role_column(db_path)
    conn = sqlite3.connect(str(db_path))
    conn.execute("UPDATE users SET role='admin' WHERE id=?", (user_id,))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    username, email, password = _resolve_credentials(args)
    db_path = _resolve_db_path(args)

    # --- Validate credentials via Pydantic before hitting the DB ---
    try:
        payload = UserRegister(username=username, email=email, password=password)
    except Exception as exc:
        print(f"ERROR: Invalid credentials — {exc}", file=sys.stderr)
        sys.exit(1)

    # --- Summary ---
    print(f"  Auth DB : {db_path.resolve()}")
    print(f"  Username: {payload.username}")
    print(f"  Email   : {payload.email}")
    print()

    # --- Create user ---
    db = AuthDB(db_path=db_path)
    try:
        user = db.register(payload)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    # --- Promote to admin ---
    _promote_to_admin(db_path, user["id"])

    print("Admin user created successfully!")
    print(f"  ID      : {user['id']}")
    print(f"  Username: {user['username']}")
    print(f"  Email   : {user['email']}")
    print("  Role    : admin")
    print()
    print("You can now log in via POST /auth/login or the browser UI.")
    print()
    print("Tip: set SUPEREZIO_JWT_SECRET in your .env.local so the server")
    print("     runs in production mode (not dev-anon mode).")


if __name__ == "__main__":
    main()
