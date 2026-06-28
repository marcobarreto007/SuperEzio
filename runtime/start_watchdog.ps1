# SuperEzio Watchdog - Non-admin version (runs in background)
# Usage: powershell -ExecutionPolicy Bypass -File runtime\start_watchdog.ps1

$ErrorActionPreference = 'Continue'
$root = 'C:\Users\marco\Desktop\SuperEzio Financeiro'
$logFile = Join-Path $root 'runtime\logs\watchdog.log'

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

Log "=== SuperEzio Watchdog (non-admin) starting ==="
Log "PID: $PID | User: $env:USERNAME"

# Check if already running
$existing = Get-Process powershell -ErrorAction SilentlyContinue | Where-Object {
    $_.Id -ne $PID -and $_.CommandLine -like "*watchdog*"
}
if ($existing) {
    Log "WARNING: Another watchdog is already running (PID: $($existing.Id))"
}

$i = 0
$consecutive_failures = 0
$max_consecutive_failures = 3
$restart_cooldown_s = 120
$last_restart_ts = [datetime]::MinValue

while ($true) {
    $i++
    $ok8082 = $false
    $ok8002 = $false

    try {
        $r8082 = Invoke-WebRequest 'http://127.0.0.1:8082/health' -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
        $ok8082 = ($r8082.StatusCode -eq 200)
    } catch {
        $ok8082 = $false
    }

    try {
        $r8002 = Invoke-WebRequest 'http://127.0.0.1:8002/health' -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
        $ok8002 = ($r8002.StatusCode -eq 200)
    } catch {
        $ok8002 = $false
    }

    $s8082 = if ($ok8082) { 'UP' } else { 'DOWN' }
    $s8002 = if ($ok8002) { 'UP' } else { 'DOWN' }

    if (-not $ok8082 -or -not $ok8002) {
        $consecutive_failures++
        Log "Pulse #${i}: 8082=${s8082} 8002=${s8002} failures=${consecutive_failures}/${max_consecutive_failures}"
    } else {
        if ($consecutive_failures -gt 0) {
            Log "Pulse #${i}: 8082=${s8082} 8002=${s8002} (recovered)"
        }
        $consecutive_failures = 0
    }

    if ($consecutive_failures -ge $max_consecutive_failures) {
        $now = Get-Date
        $elapsed = ($now - $last_restart_ts).TotalSeconds
        if ($elapsed -lt $restart_cooldown_s) {
            Log "RESTART skipped (cooldown active)"
        } else {
            Log "RESTART triggered"
            $last_restart_ts = $now
            $restart = Join-Path $root 'runtime\do_restart.ps1'
            if (Test-Path $restart) {
                try {
                    Start-Process powershell -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File',$restart -WindowStyle Hidden
                    Log "Restart initiated"
                } catch {
                    Log "Restart FAILED: $_"
                }
            }
            $consecutive_failures = 0
        }
        Start-Sleep -Seconds 15
    }

    Start-Sleep -Seconds 30
}
