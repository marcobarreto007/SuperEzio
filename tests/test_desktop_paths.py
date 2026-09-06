import os
import subprocess
import sys
from pathlib import Path


def test_desktop_paths_and_secret_search_stay_in_customer_workspace(monkeypatch, tmp_path):
    from core.config.secrets import _find_project_root
    from core.paths import find_project_root

    customer = tmp_path / "Cliente com espaços"
    monkeypatch.setenv("SUPEREZIO_DESKTOP_DATA_DIR", str(customer))
    assert find_project_root(Path(__file__)) == customer.resolve()
    assert _find_project_root() == customer.resolve()


def test_desktop_auth_database_is_outside_installation(tmp_path):
    customer = tmp_path / "customer"
    env = {**os.environ, "SUPEREZIO_DESKTOP_DATA_DIR": str(customer)}
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    result = subprocess.run(
        [sys.executable, "-c", "from agent_server.auth import _AUTH_DB_PATH; print(_AUTH_DB_PATH)"],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    assert str(customer / "runtime" / "auth.db") in result.stdout
