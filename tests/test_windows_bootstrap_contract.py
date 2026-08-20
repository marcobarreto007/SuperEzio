from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_windows_bootstrap_is_relative_locked_and_uses_official_launcher() -> None:
    bootstrap = (ROOT / "setup_superezio.bat").read_text(encoding="utf-8")
    lowered = bootstrap.lower()

    assert 'cd /d "%~dp0"' in lowered
    assert "pip install -r requirements-lock.txt" in lowered
    assert "pip install --no-deps --no-build-isolation -e ." in lowered
    assert re.search(r"(?m)^:step_playwright\s*$", lowered)
    assert "-m playwright install chromium" in lowered
    assert '-file "%~dp0start.ps1"' in lowered
    assert "python -m agent_server.main" not in lowered


def test_windows_bootstrap_has_no_known_or_command_line_admin_password() -> None:
    bootstrap = (ROOT / "setup_superezio.bat").read_text(encoding="utf-8")
    lowered = bootstrap.lower()

    assert "superezioadmin2024" not in lowered
    assert "if not defined superezio_admin_password" in lowered
    assert "seed_admin.py --username admin --email admin@superezio.com --password" not in lowered


def test_windows_lock_contains_runtime_and_browser_dependencies() -> None:
    locked = (ROOT / "requirements-lock.txt").read_text(encoding="utf-8")

    for package in (
        "fastapi",
        "langgraph",
        "llama-cpp-python",
        "playwright",
        "pyjwt",
        "torch",
        "transformers",
        "uvicorn",
    ):
        assert re.search(rf"(?m)^{re.escape(package)}==[^\s]+$", locked), package
