"""Launcher fails closed without venv/health; copy is DeepSeek-first."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_launcher_ps1_requires_venv_and_health() -> None:
    text = (ROOT / "launcher.ps1").read_text(encoding="utf-8")
    assert r".venv\Scripts\python.exe" in text
    assert "Nao esta operacional" in text
    assert "/health nao respondeu ok" in text
    assert "OPERACIONAL" in text
    assert "DeepSeek V4 Flash" in text
    assert "Z.ai (GLM-5.3) + DeepSeek (V4 Pro)" not in text
    fail_chunk = text[text.index("/health nao respondeu ok") :]
    assert "exit 1" in fail_chunk.split("Write-OperationalBanner")[0]


def test_launch_bat_requires_venv_and_health() -> None:
    text = (ROOT / "launch.bat").read_text(encoding="utf-8")
    assert r".venv\Scripts\python.exe" in text
    assert "Nao esta operacional" in text
    assert "/health nao respondeu ok" in text
    assert "DeepSeek V4 Flash" in text


def test_env_example_defaults_to_deepseek_not_glm() -> None:
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "SUPEREZIO_PRIMARY_MODEL=glm-5.3\n" not in text
    assert "deepseek-v4-flash" in text
    assert "GLM-5.3 is optional" in text or "GLM-5.3 opcional" in text or "optional" in text.lower()
