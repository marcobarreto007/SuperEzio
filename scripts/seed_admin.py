#!/usr/bin/env python3
"""
Seed Admin — Create the initial local operator for SuperEzio.

Creates the first account in the same auth database and schema used by the
FastAPI server. The V1 is single-operator; it does not claim role-based access
control that the active middleware does not enforce.

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
  - Package installed (``pip install -e .``) so that ``agent_server`` is importable.
  - ``SUPEREZIO_JWT_SECRET`` must be set in the environment or .env.local
    (otherwise AuthDB cannot create tokens, but user creation itself still works).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import pydantic

# ---------------------------------------------------------------------------
# Ensure src/ is on sys.path so that agent_server.auth is importable from scripts/
# ---------------------------------------------------------------------------
_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from fastapi import HTTPException

from agent_server.auth import AuthDB, UserCreate

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
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    username, email, password = _resolve_credentials(args)
    db_path = _resolve_db_path(args)

    # --- Validate credentials via Pydantic before hitting the DB ---
    try:
        payload = UserCreate(username=username, email=email, password=password)
    except pydantic.ValidationError as exc:
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
        user = db.create_user(
            username=payload.username,
            email=payload.email,
            password=payload.password,
        )
    except HTTPException as exc:
        print(f"ERROR: {exc.detail}", file=sys.stderr)
        sys.exit(1)

    print("Initial operator created successfully!")
    print(f"  ID      : {user['id']}")
    print(f"  Username: {user['username']}")
    print(f"  Email   : {user['email']}")
    print()
    print("You can now log in via POST /auth/login or the browser UI.")
    print()
    print("Tip: set SUPEREZIO_JWT_SECRET in your .env.local so the server")
    print("     runs in production mode (not dev-anon mode).")


if __name__ == "__main__":
    main()
