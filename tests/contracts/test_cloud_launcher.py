"""Execute the Windows launcher against isolated process and health doubles."""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
POWERSHELL = shutil.which("powershell") or shutil.which("pwsh")
pytestmark = pytest.mark.skipif(not POWERSHELL, reason="PowerShell required")


@pytest.mark.parametrize("healthy,expected", [(True, 0), (False, 6)])
def test_cloud_start_without_local_model(tmp_path, healthy, expected):
    shutil.copy(ROOT / "start.ps1", tmp_path / "start.ps1")
    config = r"""
$RuntimeDir = $PSScriptRoot
$LogsDir = $PSScriptRoot
$ApiPort = 8002
$PythonExe = "fake-python"
function Initialize-SuperEzioDirs {}
function Get-SuperEzioPortOwner { return $null }
function Test-SuperEzioHealth { return HEALTHY }
function Start-Process { return [pscustomobject]@{Id=123; StartTime=[datetime]::UtcNow; HasExited=$false} }
function Stop-Process { param([Parameter(ValueFromPipeline=$true)]$InputObject, [switch]$Force) }
"""
    (tmp_path / "config.ps1").write_text(
        config.replace("HEALTHY", "$true" if healthy else "$false")
    )
    result = subprocess.run(
        [
            POWERSHELL,
            "-NoProfile",
            "-File",
            str(tmp_path / "start.ps1"),
            "-SkipBrowser",
            "-IsolatedValidation",
            "-HealthTimeoutMinutes",
            "1" if healthy else "0",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == expected, result.stdout + result.stderr
    assert (tmp_path / "api-process.json").exists()
    assert "llama-server" not in result.stdout


def test_stop_refuses_reused_pid(tmp_path):
    shutil.copy(ROOT / "stop.ps1", tmp_path / "stop.ps1")
    (tmp_path / "config.ps1").write_text("""
$RuntimeDir = $PSScriptRoot
function Get-Process { return [pscustomobject]@{Id=123; StartTime=[datetime]::UtcNow} }
function Stop-Process { throw "MUST NOT STOP" }
""")
    (tmp_path / "api-process.json").write_text('{"Pid":123,"StartTime":"old"}')
    result = subprocess.run(
        [POWERSHELL, "-NoProfile", "-File", str(tmp_path / "stop.ps1")],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 1
    assert "refusing to stop" in result.stdout + result.stderr
    assert "MUST NOT STOP" not in result.stdout + result.stderr
