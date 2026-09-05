"""
Centralized secret loader for SuperEzio.

Order of precedence (first wins):
  1. OS environment variables (already set)
  2. .env.local (local overrides, never committed)
  3. .env (base config, never committed)

Usage:
    from core.config.secrets import load_local_env

    load_local_env()
    value = os.getenv("TWELVE_DATA_API_KEY")
"""

from __future__ import annotations

import os
import re
from pathlib import Path


def _find_project_root() -> Path:
    """Locate project root via known marker files."""
    candidates = [
        Path(__file__).resolve().parent.parent.parent.parent,  # src/core/config -> root
    ]
    for c in candidates:
        if (c / "pyproject.toml").exists() or (c / ".env.example").exists():
            return c

    # Fallback: walk up from this file
    p = Path(__file__).resolve().parent
    for _ in range(10):
        if (p / "pyproject.toml").exists() or (p / ".env.example").exists():
            return p
        p = p.parent
    return Path.cwd()


_PROJECT_ROOT: Path | None = None
_LOADED: bool = False


def _get_root() -> Path:
    global _PROJECT_ROOT
    if _PROJECT_ROOT is None:
        _PROJECT_ROOT = _find_project_root()
    return _PROJECT_ROOT


_RE_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")
_RE_QUOTED = re.compile(r'^["\'](.*)["\']$')


def _parse_dotenv(path: Path) -> dict[str, str]:
    """Parse a KEY=VALUE dotenv file. Handles basic quoting and comments."""
    result: dict[str, str] = {}
    if not path.is_file():
        return result
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            m = _RE_LINE.match(line)
            if not m:
                continue
            key, val = m.group(1), m.group(2).strip()
            qm = _RE_QUOTED.match(val)
            if qm:
                val = qm.group(1)
            result[key] = val
    return result


def _env_files(root: Path) -> tuple[Path, ...]:
    """Local override files, first wins. Never commit these paths.

    The GLM Coding Plan sidecar is loaded before ``.env.local`` so a stale
    DeepSeek CEO pin cannot shadow an explicit brain switch.
    """
    return (
        root / "secrets" / "glm_coding_plan.env",
        root / ".env.local",
        root / ".env",
    )


def load_local_env() -> None:
    """Load .env.local and .env into os.environ, respecting existing values."""
    global _LOADED
    if _LOADED:
        return
    _LOADED = True

    root = _get_root()

    # Try python-dotenv first (handles edge cases better)
    try:
        from dotenv import load_dotenv as _ld

        for env_file in _env_files(root):
            if env_file.is_file():
                _ld(dotenv_path=str(env_file), override=False)
        return
    except ImportError:
        pass

    # Fallback: manual parser
    for env_file in _env_files(root):
        if not env_file.is_file():
            continue
        for key, val in _parse_dotenv(env_file).items():
            if key not in os.environ:
                os.environ[key] = val
