"""Contract tests for the official SuperEzio runtime surface."""

from __future__ import annotations

import json
from pathlib import Path
from typing import ClassVar

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
RUNTIME_YML = ROOT / "config" / "runtime.yml"
INVENTORY = ROOT / ".f51" / "INVENTORY.json"
RUNTIME_CONTRACT = ROOT / ".f51" / "contracts" / "runtime.contract.md"
MODEL_MANIFEST = ROOT / "config" / "model_manifest.json"
AGENT_SCRIPT = ROOT / "scripts" / "serve_agent_llamacpp.ps1"
MODEL_CONFIG = ROOT / "config.ps1"
START_SCRIPT = ROOT / "start.ps1"
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
    for path in [
        RUNTIME_YML,
        MODEL_MANIFEST,
        AGENT_SCRIPT,
        AGENT_CONTRACT,
        INVENTORY,
        RUNTIME_CONTRACT,
        RUNBOOK,
    ]:
        assert path.exists(), f"Missing official runtime artifact: {path}"


def test_canonical_inventory_and_contract_match_the_official_runtime():
    cfg = _runtime_config()
    manifest = _manifest()
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    contract = RUNTIME_CONTRACT.read_text(encoding="utf-8")
    canonical_text = INVENTORY.read_text(encoding="utf-8") + "\n" + contract

    by_name = {item["name"]: item for item in inventory["entrypoints"]}
    ceo = by_name["Historical llama.cpp Server"]
    api = by_name["API Server"]
    launcher = by_name["Canonical Windows Product Launcher"]

    assert inventory["version"] == cfg["version"] == manifest["version"]
    assert ceo["canonical"] is False
    assert ceo["classification"] == "legacy_optional"
    assert launcher["port"] == 8002
    assert list(cfg["launch"]) == ["step_1"]
    assert cfg["launch"]["step_1"]["command"] == cfg["server"]["entrypoint"]
    assert all(":8080" not in item["url"] for item in cfg["health"].values())
    assert ceo["command"].endswith("serve_agent_llamacpp.ps1 -Port 8080")
    assert api["port"] == cfg["server"]["port"] == 8002
    assert api["command"] == cfg["server"]["entrypoint"]
    assert launcher["command"] == "setup_superezio.bat run"
    assert launcher["canonical"] is True
    from core.model_serving.providers import BRAIN_MODEL_ID, DEEPSEEK_MODEL_ID

    # 2026-09-12: the per-role split landed — the deciding role (CEO/agent) runs
    # deepseek-v4-pro; the supporting roles stay on deepseek-v4-flash. Until
    # 2026-09-10 every role ran deepseek-v4-flash.
    assert cfg["models"]["agent"]["model_id"] == manifest["agent"]["model"] == BRAIN_MODEL_ID
    assert (
        cfg["models"]["orchestrator"]["model_id"]
        == manifest["providers"]["local_orchestrator"]["model"]
        == BRAIN_MODEL_ID
    )
    assert (
        cfg["models"]["experts"]["model_id"]
        == manifest["providers"]["deepseek"]["model"]
        == DEEPSEEK_MODEL_ID
    )
    # `.f51/contracts/runtime.contract.md` still carries the 2026-09-10 text
    # ("deepseek-v4-flash serves every role") and is NOT owned by this change, so
    # the contract prose is not pinned here — only that the doc still names the
    # support model. The stale paragraph is flagged for a follow-up doc edit.
    assert "deepseek-v4-flash" in contract
    assert "8082" not in canonical_text
    assert "80B" not in canonical_text


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
    from agent_server.endpoints import router as endpoint_router
    from agent_server.main import app

    paths = {route.path for route in app.routes if hasattr(route, "path")}
    # FastAPI may wrap included routers and hide child paths from app.routes.
    # Merge endpoint router paths to keep the contract stable across versions.
    paths.update(route.path for route in endpoint_router.routes if hasattr(route, "path"))
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
    # The retired 1180px fixed shell (body/.app-main min-width) is exactly what
    # made every viewport below 1180px overflow, with the right rail
    # unreachable. The contract now pins the fluid, clamped columns instead.
    assert "min-width: 1180px" not in css_text
    assert "grid-template-columns: minmax(0, 1fr) minmax(0, 380px)" in css_text
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

    from core.model_serving.providers import BRAIN_MODEL_ID

    agent_cfg = cfg["models"]["agent"]
    agent_manifest = manifest["agent"]

    assert agent_cfg["provider_name"] == "agent"
    # Deciding role (2026-09-12): Bob/CEO runs the brain model, not flash.
    assert agent_cfg["model_id"] == agent_manifest["model"] == BRAIN_MODEL_ID
    assert agent_cfg["base_url"] == agent_manifest["server_url"] == "https://api.deepseek.com"
    assert agent_cfg["backend"] == "openai_compatible"
    assert agent_cfg["is_local"] is False
    assert "C:\\Users\\" not in RUNTIME_YML.read_text(encoding="utf-8")
    assert "C:\\\\Users\\\\" not in MODEL_MANIFEST.read_text(encoding="utf-8")
    assert "SUPEREZIO_MODEL_PATH" not in model_config
    assert "SUPEREZIO_LLAMA_SERVER_EXE" not in model_config
    assert 'Join-Path $SuperEzioRoot "models"' not in model_config
    assert "C:\\Users\\marco" not in model_config
    assert "llama-server.exe" in script
    assert "SUPEREZIO_LLAMA_SERVER_EXE" in script
    assert "SUPEREZIO_CUDA_BIN" in script
    assert "C:\\Users\\marco" not in script
    assert '"--port", $Port' in script
    assert "$script:CeoPort" not in model_config
    assert "8080" not in model_config
    assert "function Initialize-SuperEzioDirs" in model_config
    assert "function Get-SuperEzioPortOwner" in model_config


def test_launcher_has_isolated_fail_closed_validation_mode():
    script = START_SCRIPT.read_text(encoding="utf-8")

    assert "[switch]$IsolatedValidation" in script
    assert '$env:SUPEREZIO_VALIDATION_MODE = "0"' in script
    assert '$env:SUPEREZIO_VALIDATION_MODE = "1"' in script
    assert "SUPEREZIO_TRADING_STATE_DB = Join-Path $validationRoot" in script
    assert "SUPEREZIO_BOB_PAIN_LOG = Join-Path $validationRoot" in script
    assert '$env:F51_TRADING_EXECUTION_FREEZE = "1"' in script
    assert '$env:SUPEREZIO_LIVE_TRADING_DISABLED = "1"' in script
    assert '$env:SUPEREZIO_ENABLE_PAPER_ORDER_SUBMIT = "0"' in script


def test_public_health_exposes_validation_mode_without_sensitive_paths(monkeypatch):
    from fastapi.testclient import TestClient

    from agent_server.main import app
    from core import bob_consciousness

    class HealthyBody:
        organs: ClassVar[dict] = {}

        @staticmethod
        def is_man_at_work() -> bool:
            return False

    monkeypatch.setenv("SUPEREZIO_VALIDATION_MODE", "1")
    monkeypatch.setattr(bob_consciousness, "get_bobs_body", lambda: HealthyBody())
    original_pipeline = getattr(app.state, "pipeline", None)
    app.state.pipeline = object()
    try:
        response = TestClient(app).get("/health")
    finally:
        app.state.pipeline = original_pipeline

    assert response.status_code == 200
    payload = response.json()
    assert payload["validation_mode"] is True
    assert "validation" not in json.dumps(payload.get("paths", {})).lower()


def test_provider_factory_uses_deepseek_for_agent_and_experts(monkeypatch):
    monkeypatch.delenv("SUPEREZIO_PRIMARY_BASE_URL", raising=False)
    monkeypatch.delenv("SUPEREZIO_PRIMARY_MODEL", raising=False)
    monkeypatch.delenv("SUPEREZIO_DEEPSEEK_BASE_URL", raising=False)
    monkeypatch.delenv("SUPEREZIO_DEEPSEEK_MODEL", raising=False)
    monkeypatch.setenv("SUPEREZIO_DEEPSEEK_API_KEY", "runtime-contract-test-key")
    monkeypatch.setenv("SUPEREZIO_GLM_CODING_PLAN_API_KEY", "runtime-glm-test-key")
    monkeypatch.delenv("SUPEREZIO_AGENT_BASE_URL", raising=False)
    monkeypatch.delenv("SUPEREZIO_AGENT_MODEL", raising=False)
    monkeypatch.delenv("SUPEREZIO_AGENT_API_KEY", raising=False)

    from core.config.schema import UniversalConfig
    from core.model_serving.providers import (
        AGENT_MODEL_ID,
        AGENT_PROVIDER_NAME,
        BRAIN_MODEL_ID,
        DAYTRADE_AUDITOR_PROVIDER_NAME,
        DAYTRADE_JUDGE_PROVIDER_NAME,
        DEEPSEEK_MODEL_ID,
        DEEPSEEK_OFFICIAL_BASE_URL,
        DEEPSEEK_PROVIDER_NAME,
        GLM_CODING_PLAN_BASE_URL,
        GLM_CODING_PLAN_MODEL,
        GLM_PROVIDER_NAME,
        PRIMARY_PROVIDER_NAME,
        build_default_providers,
    )

    for name in (
        "SUPEREZIO_DEEPSEEK_MAX_TOKENS",
        "SUPEREZIO_DEEPSEEK_TIMEOUT_SEC",
        "SUPEREZIO_EXPERT_MAX_TOKENS",
        "SUPEREZIO_EXPERT_TIMEOUT",
        "SUPEREZIO_DAYTRADE_JUDGE_MODEL",
        "SUPEREZIO_DAYTRADE_AUDITOR_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)

    cfg = UniversalConfig.from_dict(_runtime_config())
    providers, gateway_config = build_default_providers(cfg)
    by_name = {provider.name: provider for provider in providers}

    assert gateway_config.timeout_s == cfg.gateway.timeout_s
    assert by_name[AGENT_PROVIDER_NAME].is_local is False
    assert by_name[AGENT_PROVIDER_NAME].backend == "openai_compatible"
    assert by_name[AGENT_PROVIDER_NAME].base_url == DEEPSEEK_OFFICIAL_BASE_URL
    # Deciding roles (2026-09-12): CEO/agent and orchestrator run the brain
    # model; the expert committee, judge and auditor stay on the support model
    # (asserted further down).
    assert by_name[AGENT_PROVIDER_NAME].model == AGENT_MODEL_ID == BRAIN_MODEL_ID
    assert by_name[AGENT_PROVIDER_NAME].max_tokens == 1800
    assert by_name[AGENT_PROVIDER_NAME].timeout_s == 180
    assert PRIMARY_PROVIDER_NAME == "local_orchestrator"
    assert by_name[PRIMARY_PROVIDER_NAME].is_local is False
    assert by_name[PRIMARY_PROVIDER_NAME].backend == "openai_compatible"
    assert by_name[PRIMARY_PROVIDER_NAME].base_url == DEEPSEEK_OFFICIAL_BASE_URL
    assert by_name[PRIMARY_PROVIDER_NAME].model == BRAIN_MODEL_ID
    assert by_name[PRIMARY_PROVIDER_NAME].max_tokens == 1800
    assert by_name[PRIMARY_PROVIDER_NAME].timeout_s == cfg.models["orchestrator"].timeout_s
    assert cfg.models["agent"].timeout_s == 180
    assert gateway_config.timeout_s == 600

    # Optional GLM path, built only because this test arms the coding-plan key.
    glm = by_name[GLM_PROVIDER_NAME]
    assert glm.is_local is False
    assert glm.base_url == GLM_CODING_PLAN_BASE_URL
    assert glm.model == GLM_CODING_PLAN_MODEL
    assert glm.max_tokens == 1800
    assert glm.timeout_s == 60
    assert glm.api_key == "runtime-glm-test-key"

    for name in (
        DEEPSEEK_PROVIDER_NAME,
        DAYTRADE_JUDGE_PROVIDER_NAME,
        DAYTRADE_AUDITOR_PROVIDER_NAME,
    ):
        provider = by_name[name]
        assert provider.is_local is False
        assert provider.base_url == DEEPSEEK_OFFICIAL_BASE_URL
        assert provider.model == DEEPSEEK_MODEL_ID
        assert provider.max_tokens == 1800
        assert provider.timeout_s == 60
        assert provider.api_key == "runtime-contract-test-key"

    raw_cfg = _runtime_config()
    experts_cfg = raw_cfg["models"]["experts"]
    assert experts_cfg["base_url"] == DEEPSEEK_OFFICIAL_BASE_URL
    assert experts_cfg["model_id"] == DEEPSEEK_MODEL_ID
    assert experts_cfg["provider_name"] == DEEPSEEK_PROVIDER_NAME
    assert experts_cfg["is_local"] is False
    assert experts_cfg["allow_fallback"] is False
    assert experts_cfg["api_key_env"] == "SUPEREZIO_DEEPSEEK_API_KEY"
    for section in ("daytrade_judge", "daytrade_auditor"):
        assert raw_cfg["models"][section]["base_url"] == DEEPSEEK_OFFICIAL_BASE_URL
        assert raw_cfg["models"][section]["model_id"] == DEEPSEEK_MODEL_ID
        assert raw_cfg["models"][section]["is_local"] is False
        assert raw_cfg["models"][section]["allow_fallback"] is False
        assert raw_cfg["models"][section]["api_key_env"] == "SUPEREZIO_DEEPSEEK_API_KEY"


# Launcher batch file has been retired/deleted.


def test_runtime_checkpoint_tracks_official_entrypoints():
    if not RUNTIME_CHECKPOINT.exists():
        pytest.skip("Operator runtime checkpoint is intentionally excluded from release packages")
    checkpoint = json.loads(RUNTIME_CHECKPOINT.read_text(encoding="utf-8"))
    params = checkpoint["runtime_parameters"]

    assert params["api_port"] == 8002
    assert params["agent_port"] == 8080
    assert params["api_entrypoint"] == "python -m agent_server.main"
    assert params["agent_entrypoint"].endswith("scripts/serve_agent_llamacpp.ps1 -Port 8080")
    assert params["model_path"] == (
        r"C:\Users\marco\Desktop\SuperEzio\models\Ornith-1.0-9B-Q4_K_M.gguf"
    )
    assert params.get("lora_path") in (None, "")


def test_runbook_documents_official_runtime_commands():
    text = RUNBOOK.read_text(encoding="utf-8")

    assert "-File start.ps1" in text
    assert "-File stop.ps1" in text
    assert "python -m agent_server.main" in text
    assert "local_orchestrator" in text
    # 2026-09-12: the runbook still carries the 2026-09-10 "flash serves every
    # role" text, which is only half true now — the deciding roles (CEO and
    # orchestrator) moved to deepseek-v4-pro. `docs/runbooks/RUNBOOK.md` is NOT
    # owned by this change, so only the support model it still documents is
    # pinned here; the stale paragraph is flagged for a follow-up doc edit.
    assert "deepseek-v4-flash" in text
    assert "http://127.0.0.1:8002/health/details" in text
    assert "http://127.0.0.1:8080" not in text
    assert "serve_agent_llamacpp" not in text
    assert "runtime/checkpoints/latest.json" in text
    assert ".f51/GITHUB_POLICY.json" in text
