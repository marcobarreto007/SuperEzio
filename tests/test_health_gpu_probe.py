"""T3 — deterministic unit tests for the GPU readiness probe.

Covers the torch-CUDA primary probe and the nvidia-smi fallback parser added
to fix the false-negative gpu.available=false reported by /health/details while
llama-server was using the GPU. No network, no live API, no real subprocess:
all subprocess calls are monkeypatched.
"""

import subprocess

from agent_server.main import (
    _parse_nvidia_smi,
    _probe_gpu,
    _probe_gpu_nvidia_smi,
    _probe_gpu_torch,
)

# Real output shape captured from the machine (2026-08-21, RTX 3060 in use by llama-server).
REAL_NVIDIA_SMI_OUTPUT = (
    "name, memory.used [MiB], memory.free [MiB]\nNVIDIA GeForce RTX 3060, 9195 MiB, 2921 MiB\n"
)


# ---------------------------------------------------------------------------
# Parser (pure function)
# ---------------------------------------------------------------------------
def test_parse_nvidia_smi_units_header():
    devices = _parse_nvidia_smi(REAL_NVIDIA_SMI_OUTPUT)
    assert len(devices) == 1
    dev = devices[0]
    assert dev["name"] == "NVIDIA GeForce RTX 3060"
    assert dev["memory_used_mb"] == 9195
    assert dev["memory_free_mb"] == 2921
    assert dev["vram_mb"] == 9195 + 2921
    assert dev["id"] == 0


def test_parse_nvidia_smi_multiple_gpus_without_units():
    out = "NVIDIA GeForce RTX 3060, 9195, 2921\nNVIDIA GeForce RTX 2070, 1000, 7000\n"
    devices = _parse_nvidia_smi(out)
    assert len(devices) == 2
    assert devices[1]["name"] == "NVIDIA GeForce RTX 2070"
    assert devices[1]["id"] == 1
    assert devices[1]["memory_used_mb"] == 1000


def test_parse_nvidia_smi_na_and_garbage_lines():
    out = (
        "name, memory.used [MiB], memory.free [MiB]\n"
        "NVIDIA GeForce RTX 3060, N/A, 2921 MiB\n"
        "\n"
        "broken line\n"
    )
    devices = _parse_nvidia_smi(out)
    assert len(devices) == 1
    assert devices[0]["memory_used_mb"] is None
    assert devices[0]["memory_free_mb"] == 2921
    assert devices[0]["vram_mb"] == 2921


def test_parse_nvidia_smi_empty_or_header_only():
    assert _parse_nvidia_smi("") == []
    assert _parse_nvidia_smi("name, memory.used [MiB], memory.free [MiB]\n") == []


# ---------------------------------------------------------------------------
# Probe orchestration
# ---------------------------------------------------------------------------
def test_probe_gpu_torch_primary_wins_without_subprocess(monkeypatch):
    torch_info = {
        "available": True,
        "devices": [{"id": 0, "name": "torch-gpu", "vram_mb": 8192}],
        "status": "ok",
        "source": "torch",
    }
    monkeypatch.setattr("agent_server.main._probe_gpu_torch", lambda: torch_info)

    def _forbidden(*args, **kwargs):
        raise AssertionError("subprocess.run must not run when the torch probe succeeds")

    monkeypatch.setattr("agent_server.main.subprocess.run", _forbidden)
    assert _probe_gpu() == torch_info


def test_probe_gpu_falls_back_to_nvidia_smi_when_torch_unavailable(monkeypatch):
    monkeypatch.setattr("agent_server.main._probe_gpu_torch", lambda: None)
    fake_proc = subprocess.CompletedProcess(
        args=[], returncode=0, stdout=REAL_NVIDIA_SMI_OUTPUT, stderr=""
    )
    monkeypatch.setattr("agent_server.main.subprocess.run", lambda *a, **k: fake_proc)

    info = _probe_gpu()
    assert info["available"] is True
    assert info["status"] == "ok"
    assert info["source"] == "nvidia-smi"
    assert info["devices"][0]["name"] == "NVIDIA GeForce RTX 3060"
    assert info["devices"][0]["memory_used_mb"] == 9195


def test_probe_gpu_honest_unavailable_when_nvidia_smi_missing(monkeypatch):
    monkeypatch.setattr("agent_server.main._probe_gpu_torch", lambda: None)

    def _missing(*args, **kwargs):
        raise FileNotFoundError("nvidia-smi")

    monkeypatch.setattr("agent_server.main.subprocess.run", _missing)

    info = _probe_gpu()
    assert info["available"] is False
    assert info["devices"] == []
    assert info["status"] == "unavailable"
    assert "nvidia-smi not found" in info["reason"]
    assert "torch" in info["reason"]


def test_probe_gpu_honest_unavailable_when_nvidia_smi_fails(monkeypatch):
    monkeypatch.setattr("agent_server.main._probe_gpu_torch", lambda: None)
    fake_proc = subprocess.CompletedProcess(
        args=[], returncode=2, stdout="", stderr="nvml: driver/library mismatch"
    )
    monkeypatch.setattr("agent_server.main.subprocess.run", lambda *a, **k: fake_proc)

    info = _probe_gpu()
    assert info["available"] is False
    assert "rc=2" in info["reason"]
    assert "nvml: driver/library mismatch" in info["reason"]


def test_probe_gpu_honest_unavailable_when_nvidia_smi_reports_no_rows(monkeypatch):
    monkeypatch.setattr("agent_server.main._probe_gpu_torch", lambda: None)
    fake_proc = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="name, memory.used [MiB], memory.free [MiB]\n", stderr=""
    )
    monkeypatch.setattr("agent_server.main.subprocess.run", lambda *a, **k: fake_proc)

    info = _probe_gpu()
    assert info["available"] is False
    assert "no GPU rows" in info["reason"]


# ---------------------------------------------------------------------------
# Sub-probes
# ---------------------------------------------------------------------------
def test_probe_gpu_torch_returns_none_when_torch_missing(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def _blocking_torch(name, *args, **kwargs):
        if name == "torch":
            raise ImportError("No module named 'torch'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _blocking_torch)
    assert _probe_gpu_torch() is None


def test_probe_gpu_nvidia_smi_never_raises_on_timeout(monkeypatch):
    def _timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="nvidia-smi", timeout=3)

    monkeypatch.setattr("agent_server.main.subprocess.run", _timeout)
    info, reason = _probe_gpu_nvidia_smi()
    assert info is None
    assert "timed out" in reason
