from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_compose_uses_local_ceo_and_required_deepseek_experts() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    services = compose["services"]
    ceo = services["bob-ceo"]
    api = services["api-server"]

    assert ceo["image"] == "ghcr.io/ggml-org/llama.cpp:server-cuda"
    assert ceo["ports"] == ["8080:8080"]
    assert "/models/Qwen3.8-27B-Q4_K_M.gguf" in ceo["command"]
    for expected in ("all", "layer", "12,8", "8192"):
        assert expected in ceo["command"]

    env = set(api["environment"])
    assert "SUPEREZIO_HOST=0.0.0.0" in env
    assert "SUPEREZIO_RUNTIME_PROFILE=docker" in env
    assert "SUPEREZIO_AGENT_BASE_URL=http://bob-ceo:8080/v1" in env
    assert "SUPEREZIO_PRIMARY_BASE_URL=http://bob-ceo:8080/v1" in env
    assert "SUPEREZIO_DEEPSEEK_BASE_URL=https://api.deepseek.com" in env
    assert "SUPEREZIO_DEEPSEEK_MODEL=deepseek-v4-pro" in env
    key_binding = next(item for item in env if item.startswith("SUPEREZIO_DEEPSEEK_API_KEY="))
    assert key_binding == (
        "SUPEREZIO_DEEPSEEK_API_KEY="
        "${SUPEREZIO_DEEPSEEK_API_KEY:?SUPEREZIO_DEEPSEEK_API_KEY is required}"
    )
    assert "sk-" not in key_binding


def test_dockerfile_installs_the_real_project_without_silent_fallback() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY . ." in dockerfile
    assert "python -m pip install --no-cache-dir ." in dockerfile
    install_line = next(
        line for line in dockerfile.splitlines() if "pip install --no-cache-dir ." in line
    )
    assert "||" not in install_line


def test_retired_lifecycle_scripts_fail_closed_and_are_project_relative() -> None:
    for relative in (
        "runtime/do_restart.ps1",
        "runtime/install_watchdog.ps1",
        "runtime/start_watchdog.ps1",
        "runtime/watchdog.ps1",
        "runtime/watchdog_service.ps1",
    ):
        script = (ROOT / relative).read_text(encoding="utf-8")
        assert "RETIRED" in script
        assert "exit 2" in script
        assert "$PSScriptRoot" in script
        assert "8082" not in script
        assert "C:\\Users\\" not in script


def test_retired_first_run_has_no_cloud_wizard_or_external_model_endpoint() -> None:
    script = (ROOT / "scripts/first_run.py").read_text(encoding="utf-8").lower()
    assert "deepseek" not in script
    assert "https://" not in script
    assert "setup_superezio.bat" in script
    assert "check.ps1" in script
    assert "raise systemexit(2)" in script
