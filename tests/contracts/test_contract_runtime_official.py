"""Contract tests for the official SuperEzio runtime surface."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
RUNTIME_YML = ROOT / "config" / "runtime.yml"
MODEL_MANIFEST = ROOT / "config" / "model_manifest.json"
CEO_SCRIPT = ROOT / "scripts" / "serve_ceo_llamacpp.ps1"
LAUNCHER = ROOT / "desktop" / "SuperEzio.bat"
AGENT_CONTRACT = ROOT / ".f51" / "contracts" / "agent-server.contract.md"
RUNTIME_CHECKPOINT = ROOT / "runtime" / "checkpoints" / "latest.json"
RUNBOOK = ROOT / "docs" / "runbooks" / "RUNBOOK.md"


def _runtime_config() -> dict:
    return yaml.safe_load(RUNTIME_YML.read_text(encoding="utf-8"))


def _manifest() -> dict:
    return json.loads(MODEL_MANIFEST.read_text(encoding="utf-8"))


def test_official_runtime_files_exist():
    for path in [RUNTIME_YML, MODEL_MANIFEST, CEO_SCRIPT, LAUNCHER, AGENT_CONTRACT, RUNBOOK]:
        assert path.exists(), f"Missing official runtime artifact: {path}"


def test_runtime_server_contract_matches_agent_server_import(monkeypatch):
    monkeypatch.delenv("SUPEREZIO_PORT", raising=False)
    monkeypatch.delenv("SUPEREZIO_HOST", raising=False)
    cfg = _runtime_config()

    assert cfg["server"]["host"] == "127.0.0.1"
    assert cfg["server"]["port"] == 8002
    assert cfg["server"]["entrypoint"] == "python -m agent_server.main"
    assert cfg["server"]["pythonpath"] == "src"
    assert cfg["storage"]["logs_dir"] == "runtime/logs"
    assert cfg["storage"]["runtime_checkpoints_dir"] == "runtime/checkpoints"

    from agent_server.main import HOST, PORT, app

    assert HOST == "127.0.0.1"
    assert PORT == 8002
    assert app is not None


def test_runtime_registers_public_contract_routes():
    from agent_server.main import app

    paths = {route.path for route in app.routes if hasattr(route, "path")}
    expected = {
        "/",
        "/health",
        "/health/details",
        "/metrics",
        "/neural/logs",
        "/api/chart-data/{ticker}",
        "/api/chart-sse/{ticker}",
        "/task/submit",
        "/capabilities",
        "/product/manifest",
        "/api/sdca/evaluate",
        "/experts/neural-decision/predict",
    }
    assert expected.issubset(paths)


def test_frontend_static_assets_are_mounted():
    from agent_server.main import app

    paths = {route.path for route in app.routes if hasattr(route, "path")}
    assert "/frontend" in paths
    assert "/css" in paths
    assert "/js" in paths


def test_ceo_runtime_config_matches_manifest_and_script():
    cfg = _runtime_config()
    manifest = _manifest()
    script = CEO_SCRIPT.read_text(encoding="utf-8")

    ceo_cfg = cfg["models"]["ceo"]
    ceo_manifest = manifest["ceo"]
    model_path = ROOT / ceo_cfg["path"]

    assert ceo_cfg["provider_name"] == "ceo"
    assert ceo_cfg["model_id"] == ceo_manifest["model"]
    assert ceo_cfg["path"] == ceo_manifest["path"]
    assert ceo_cfg["server_url"] == ceo_manifest["server_url"]
    assert ceo_cfg["backend"] == "openai_compatible"
    assert ceo_cfg["is_local"] is True
    assert model_path.exists(), f"Official CEO GGUF is missing: {model_path}"
    assert model_path.name in script
    assert "llama-server.exe" in script
    assert "--port $Port" in script


def test_provider_factory_keeps_ceo_local_only(monkeypatch):
    monkeypatch.delenv("SUPEREZIO_PRIMARY_BASE_URL", raising=False)
    monkeypatch.delenv("SUPEREZIO_PRIMARY_MODEL", raising=False)
    monkeypatch.delenv("SUPEREZIO_DEEPSEEK_BASE_URL", raising=False)
    monkeypatch.delenv("SUPEREZIO_DEEPSEEK_MODEL", raising=False)
    monkeypatch.delenv("SUPEREZIO_CEO_BASE_URL", raising=False)

    from core.config.schema import UniversalConfig
    from core.model_serving.providers import (
        CEO_MODEL_ID,
        CEO_PROVIDER_NAME,
        PRIMARY_PROVIDER_NAME,
        build_default_providers,
    )

    cfg = UniversalConfig.from_dict(_runtime_config())
    providers, gateway_config = build_default_providers(cfg)
    by_name = {provider.name: provider for provider in providers}

    assert gateway_config.timeout_s == cfg.gateway.timeout_s
    assert by_name[CEO_PROVIDER_NAME].is_local is True
    assert by_name[CEO_PROVIDER_NAME].backend == "openai_compatible"
    assert by_name[CEO_PROVIDER_NAME].base_url == "http://127.0.0.1:8082/v1"
    assert by_name[CEO_PROVIDER_NAME].model == CEO_MODEL_ID
    assert PRIMARY_PROVIDER_NAME == "local_orchestrator"
    assert by_name[PRIMARY_PROVIDER_NAME].is_local is True
    assert by_name[PRIMARY_PROVIDER_NAME].backend == "openai_compatible"
    assert by_name[PRIMARY_PROVIDER_NAME].base_url == "http://127.0.0.1:8082/v1"
    assert by_name[PRIMARY_PROVIDER_NAME].model == CEO_MODEL_ID


def test_launcher_check_mode_validates_without_starting_servers():
    if os.name != "nt":
        pytest.skip("Windows batch launcher contract is only executable on Windows")

    env = os.environ.copy()
    env["SUPEREZIO_LAUNCHER_CHECK"] = "1"
    env["SUPEREZIO_NO_BROWSER"] = "1"

    result = subprocess.run(
        ["cmd", "/c", str(LAUNCHER)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Launcher checks passed" in result.stdout


def test_runtime_checkpoint_tracks_official_entrypoints():
    checkpoint = json.loads(RUNTIME_CHECKPOINT.read_text(encoding="utf-8"))
    params = checkpoint["runtime_parameters"]

    assert params["api_port"] == 8002
    assert params["ceo_port"] == 8082
    assert params["api_entrypoint"] == "python -m agent_server.main"
    assert params["ceo_entrypoint"].endswith("scripts/serve_ceo_llamacpp.ps1 -Port 8082")
    assert params["model_path"] == "models/superezio-ceo-intent-merged.Q4_K_M.gguf"


def test_runbook_documents_official_runtime_commands():
    text = RUNBOOK.read_text(encoding="utf-8")

    assert (
        "powershell -ExecutionPolicy Bypass -File scripts/serve_ceo_llamacpp.ps1 -Port 8082" in text
    )
    assert "python -m agent_server.main" in text
    assert "local_orchestrator" in text
    assert "https://api.deepseek.com" in text
    assert "http://127.0.0.1:8082/health" in text
    assert "http://127.0.0.1:8082/v1/models" in text
    assert "http://127.0.0.1:8002/health/details" in text
    assert "runtime/checkpoints/latest.json" in text
    assert ".f51/GITHUB_POLICY.json" in text
