# SuperEzio Watchdog Service - Self-restarting daemon
# Usage: powershell -ExecutionPolicy Bypass -File runtime\watchdog_service.ps1

$ErrorActionPreference = 'Continue'
$root = 'C:\Users\marco\Desktop\SuperEzio Financeiro'
$logFile = Join-Path $root 'runtime\logs\watchdog_service.log'

# Ensure log directory exists
New-Item -ItemType Directory -Force -Path (Split-Path $logFile) | Out-Null

function Log {
    param([string]$Message)
    $ts = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    $line = "$ts $Message"
    try {
        Add-Content -Path $logFile -Value $line -Encoding UTF8
    } catch {
        Write-Host $line
    }
    Write-Host $line
}

# Self-restart loop - watchdog NEVER exits
while ($true) {
    Log "=== Watchdog Service starting ==="
    Log "PID: $PID"

    # Run the actual watchdog
    $watchdogScript = Join-Path $root 'runtime\watchdog.ps1'
    $result = & $watchdogScript

    if ($LASTEXITCODE -eq 0) {
        Log "Watchdog exited cleanly (should never happen)"
    } else {
        Log "Watchdog crashed with exit code $LASTEXITCODE"
    }

    Log "Restarting watchdog in 10 seconds..."
    Start-Sleep -Seconds 10

    # Auto-heal: if watchdog keeps crashing, wait longer
    $restartFile = Join-Path $root 'runtime\watchdog_restart_count.txt'
    $count = 0
    if (Test-Path $restartFile) {
        $count = [int](Get-Content $restartFile)
    }
    $count++
    $count | Set-Content $restartFile

    if ($count -gt 5) {
        Log "Too many restarts ($count). Waiting 60 seconds before next attempt."
        Start-Sleep -Seconds 60
        # Reset count after long wait
        if ($count -gt 10) {
            0 | Set-Content $restartFile
        }
    }
}
