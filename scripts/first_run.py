#!/usr/bin/env python3
"""Retired bootstrap shim.

The supported setup is ``setup_superezio.bat`` followed by ``check.ps1``.
Authentication helpers remain importable for compatibility with existing
operators and tests, but this module never configures or contacts a cloud LLM.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

_PROJECT_ROOT: Path | None = None


def _find_project_root() -> Path:
    candidate = Path(__file__).resolve().parent.parent
    for _ in range(10):
        if (candidate / "pyproject.toml").exists():
            return candidate
        candidate = candidate.parent
    return Path.cwd()


def _project_root() -> Path:
    global _PROJECT_ROOT
    if _PROJECT_ROOT is None:
        _PROJECT_ROOT = _find_project_root()
    return _PROJECT_ROOT


def _resolve_auth_db() -> Path:
    """Use the same authentication database as the official runtime."""
    import os

    data_dir = os.getenv("SUPEREZIO_DATA_DIR", "")
    if data_dir:
        return Path(data_dir) / "auth.db"
    return _project_root() / "runtime" / "auth.db"


def _create_admin_user(username: str, email: str, password: str) -> dict:
    """Create an operator through the runtime authentication authority."""
    from agent_server.auth import AuthDB, UserCreate

    db = AuthDB(db_path=_resolve_auth_db())
    payload = UserCreate(username=username, email=email, password=password)
    return db.create_user(
        username=payload.username,
        email=payload.email,
        password=payload.password,
    )


def _check_auth_db() -> dict:
    """Report whether the official authentication database has operators."""
    result: dict = {"status": "ok", "detail": ""}
    try:
        auth_db = _resolve_auth_db()
        if not auth_db.is_file():
            return {"status": "missing", "detail": f"Auth DB not found at {auth_db}"}
        with sqlite3.connect(str(auth_db)) as conn:
            count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        result["user_count"] = count
        if count == 0:
            result["status"] = "empty"
            result["detail"] = "No users in auth database"
        else:
            result["detail"] = f"{count} operator account(s)"
    except Exception as exc:
        result["status"] = "error"
        result["detail"] = str(exc)[:120]
    return result


def main(argv: list[str] | None = None) -> None:
    """Fail closed instead of running the obsolete interactive wizard."""
    del argv
    root = _project_root()
    print("RETIRED: scripts/first_run.py no longer owns setup or model configuration.")
    print(f"Run: {root / 'setup_superezio.bat'}")
    print(f"Then: {root / 'check.ps1'}")
    print("Official runtime: local Qwen3.8-27B-Q4_K_M on :8080; API on :8002.")
    raise SystemExit(2)


if __name__ == "__main__":
    main()
