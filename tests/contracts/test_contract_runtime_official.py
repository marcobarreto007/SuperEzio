"""Contract tests for the official SuperEzio runtime surface."""

from __future__ import annotations

import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
RUNTIME_YML = ROOT / "config" / "runtime.yml"
MODEL_MANIFEST = ROOT / "config" / "model_manifest.json"
AGENT_SCRIPT = ROOT / "scripts" / "serve_agent_llamacpp.ps1"
MODEL_CONFIG = ROOT / "config.ps1"
AGENT_CONTRACT = ROOT / ".f51" / "contracts" / "agent-server.contract.md"
RUNTIME_CHECKPOINT = ROOT / "runtime" / "checkpoints" / "latest.json"
RUNBOOK = ROOT / "docs" / "runbooks" / "RUNBOOK.md"
FRONTEND_INDEX = ROOT / "frontend" / "index.html"
FRONTEND_CHAT = ROOT / "frontend" / "js" / "chat.js"
FRONTEND_INIT = ROOT / "frontend" / "js" / "init.js"


def _runtime_config() -> dict:
    return yaml.safe_load(RUNTIME_YML.read_text(encoding="utf-8"))


def _manifest() -> dict:
    return json.loads(MODEL_MANIFEST.read_text(encoding="utf-8"))


def test_official_runtime_files_exist():
    for path in [RUNTIME_YML, MODEL_MANIFEST, AGENT_SCRIPT, AGENT_CONTRACT, RUNBOOK]:
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


def test_frontend_contract_uses_bob_unified_workspace_without_retired_panels():
    html = FRONTEND_INDEX.read_text(encoding="utf-8")
    chat_js = FRONTEND_CHAT.read_text(encoding="utf-8")
    init_js = FRONTEND_INIT.read_text(encoding="utf-8")

    assert "Bob" in html
    assert "bob-welcome" in html
    assert "ops-board" not in html
    assert "mode-tabs" not in html
    assert "telemetry-hud" not in html
    assert "ask-chips" not in html
    assert "bob-orb" not in html
    assert "portfolio-drawer" not in html
    assert "pf-btn" not in html
    assert "market-rail" not in html
    assert "rail-btn" not in html
    assert "Crosshair" not in html
    assert "Trendline" not in html
    assert "detail ||" in (ROOT / "frontend" / "js" / "events.js").read_text(encoding="utf-8")
    assert "returned no stream body" in (ROOT / "frontend" / "js" / "api.js").read_text(
        encoding="utf-8"
    )
    events_js = (ROOT / "frontend" / "js" / "events.js").read_text(encoding="utf-8")
    assert "SZ_SHOW_DEBUG_CARDS" in events_js
    assert "showDebugCards() && SZ.renderPipeline" in events_js
    assert "showDebugCards() && SZ.renderExplanation" in events_js
    css_files = [
        ROOT / "frontend" / "css" / "base.css",
        ROOT / "frontend" / "css" / "charts.css",
        ROOT / "frontend" / "css" / "chat.css",
        ROOT / "frontend" / "css" / "topbar.css",
        ROOT / "frontend" / "css" / "sdca.css",
        ROOT / "frontend" / "css" / "pennylab.css",
        ROOT / "frontend" / "css" / "data-quality.css",
        ROOT / "frontend" / "css" / "crisis.css",
        ROOT / "frontend" / "css" / "experts.css",
    ]
    css_text = "\n".join(path.read_text(encoding="utf-8") for path in css_files)
    assert "max-width: 768px" not in css_text
    assert "min-width: 1180px" in css_text
    assert "panel-drawer" not in html
    assert "data-panel" not in html
    assert "css/panels.css" not in html
    for old_script in [
        "js/metrics.js",
        "js/manifest.js",
        "js/neural-logs.js",
        "js/capabilities.js",
        "js/journal.js",
    ]:
        assert old_script not in html
    assert 'session_id: "sz-session"' not in init_js
    assert "getBrowserSessionId()" in init_js
    assert "window.SZ.esc = esc" in chat_js


def test_agent_runtime_config_matches_manifest_and_script():
    cfg = _runtime_config()
    manifest = _manifest()
    script = AGENT_SCRIPT.read_text(encoding="utf-8")
    model_config = MODEL_CONFIG.read_text(encoding="utf-8")

    agent_cfg = cfg["models"]["agent"]
    agent_manifest = manifest["agent"]
    model_path = ROOT / agent_cfg["path"]

    assert agent_cfg["provider_name"] == "agent"
    assert agent_cfg["model_id"] == agent_manifest["model"]
    assert agent_cfg["path"] == agent_manifest["path"]
    assert agent_cfg["server_url"] == agent_manifest["server_url"]
    assert agent_cfg["backend"] == "openai_compatible"
    assert agent_cfg["is_local"] is True
    assert agent_cfg["preferred_llama_server"] == r"C:\llama.cpp\build\bin\llama-server.exe"
    assert agent_cfg["fallback_llama_server"] == "llama.cpp\\bin\\llama-server.exe"
    assert model_path.exists(), f"Official agent GGUF is missing: {model_path}"
    assert model_path.name in model_config
    assert "llama-server.exe" in script
    assert "SUPEREZIO_LLAMA_SERVER_EXE" in script
    assert r"C:\llama.cpp\build\bin\llama-server.exe" in model_config
    assert '"--port", $Port' in script


def test_provider_factory_keeps_agent_local_only(monkeypatch):
    monkeypatch.delenv("SUPEREZIO_PRIMARY_BASE_URL", raising=False)
    monkeypatch.delenv("SUPEREZIO_PRIMARY_MODEL", raising=False)
    monkeypatch.delenv("SUPEREZIO_DEEPSEEK_BASE_URL", raising=False)
    monkeypatch.delenv("SUPEREZIO_DEEPSEEK_MODEL", raising=False)
    monkeypatch.delenv("SUPEREZIO_AGENT_BASE_URL", raising=False)

    from core.config.schema import UniversalConfig
    from core.model_serving.providers import (
        AGENT_MODEL_ID,
        AGENT_PROVIDER_NAME,
        PRIMARY_PROVIDER_NAME,
        build_default_providers,
    )

    cfg = UniversalConfig.from_dict(_runtime_config())
    providers, gateway_config = build_default_providers(cfg)
    by_name = {provider.name: provider for provider in providers}

    assert gateway_config.timeout_s == cfg.gateway.timeout_s
    assert by_name[AGENT_PROVIDER_NAME].is_local is True
    assert by_name[AGENT_PROVIDER_NAME].backend == "openai_compatible"
    assert by_name[AGENT_PROVIDER_NAME].base_url == "http://127.0.0.1:8082/v1"
    assert by_name[AGENT_PROVIDER_NAME].model == AGENT_MODEL_ID
    assert PRIMARY_PROVIDER_NAME == "local_orchestrator"
    assert by_name[PRIMARY_PROVIDER_NAME].is_local is True
    assert by_name[PRIMARY_PROVIDER_NAME].backend == "openai_compatible"
    assert by_name[PRIMARY_PROVIDER_NAME].base_url == "http://127.0.0.1:8082/v1"
    assert by_name[PRIMARY_PROVIDER_NAME].model == AGENT_MODEL_ID


# Launcher batch file has been retired/deleted.


def test_runtime_checkpoint_tracks_official_entrypoints():
    checkpoint = json.loads(RUNTIME_CHECKPOINT.read_text(encoding="utf-8"))
    params = checkpoint["runtime_parameters"]

    assert params["api_port"] == 8002
    assert params["agent_port"] == 8082
    assert params["api_entrypoint"] == "python -m agent_server.main"
    assert params["agent_entrypoint"].endswith("scripts/serve_agent_llamacpp.ps1 -Port 8082")
    assert params["model_path"] == r"C:\llama.cpp\models\bob-core-local.gguf"
    assert params["lora_path"] == r"C:\llama.cpp\models\bob-lora-best.gguf"


def test_runbook_documents_official_runtime_commands():
    text = RUNBOOK.read_text(encoding="utf-8")

    assert (
        "powershell -ExecutionPolicy Bypass -File scripts/serve_agent_llamacpp.ps1 -Port 8082"
        in text
    )
    assert "python -m agent_server.main" in text
    assert "local_orchestrator" in text
    assert "https://api.deepseek.com" in text
    assert "http://127.0.0.1:8082/health" in text
    assert "http://127.0.0.1:8082/v1/models" in text
    assert "http://127.0.0.1:8002/health/details" in text
    assert "runtime/checkpoints/latest.json" in text
    assert ".f51/GITHUB_POLICY.json" in text
