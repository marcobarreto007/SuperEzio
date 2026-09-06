"""Customer data isolation and packaged resource installation contracts."""

import json
from pathlib import Path

import pytest

from scripts.desktop_backend import prepare_workspace

REPO = Path(__file__).resolve().parents[1]


def resources(tmp_path: Path) -> Path:
    root = tmp_path / "bundle"
    for name in ("config", "frontend", "templates"):
        (root / name).mkdir(parents=True)
    (root / "config/runtime.yml").write_text("version: 1", encoding="utf-8")
    (root / "frontend/index.html").write_text("new frontend", encoding="utf-8")
    (root / "config/secret.env").write_text("must not copy", encoding="utf-8")
    return root


def test_resources_preserve_customer_config_and_refresh_frontend(tmp_path):
    source = resources(tmp_path)
    target = prepare_workspace(source, tmp_path / "customer")
    (target / "config/runtime.yml").write_text("customer settings", encoding="utf-8")
    (target / "frontend/index.html").write_text("old frontend", encoding="utf-8")
    prepare_workspace(source, target)
    assert (target / "config/runtime.yml").read_text() == "customer settings"
    assert (target / "frontend/index.html").read_text() == "new frontend"
    assert not (target / "config/secret.env").exists()
    assert (target / "runtime").is_dir()


def test_missing_resources_fail_before_starting_server(tmp_path):
    with pytest.raises(FileNotFoundError, match="config"):
        prepare_workspace(tmp_path / "missing", tmp_path / "customer")


def test_cannot_use_installation_as_customer_data(tmp_path):
    source = resources(tmp_path)
    with pytest.raises(ValueError, match="separate"):
        prepare_workspace(source, source)


def test_electron_package_ships_autoprovision_and_injects_full_dotenv():
    pkg = json.loads((REPO / "desktop" / "package.json").read_text(encoding="utf-8"))
    assert "autoprovision.cjs" in pkg["build"]["files"]
    main = (REPO / "desktop" / "main.cjs").read_text(encoding="utf-8")
    assert "loadDotenv(dotenvDirs())" in main
    assert "...dotenvEnv" in main
    assert "hasLaunchKeys(dotenvEnv)" in main
