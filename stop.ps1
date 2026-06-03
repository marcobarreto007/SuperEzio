# SuperEzio STOP script.
# Stops only the official SuperEzio services listening on the configured ports.

param([switch]$ForceKill)

$ErrorActionPreference = "Continue"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

$configPath = Join-Path $ScriptDir "config.ps1"
if (Test-Path $configPath) {
    . $configPath
} else {
    $CeoPort = 8082
    $ApiPort = 8002
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  SuperEzio - Stopping services" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

$stopped = 0

foreach ($port in @($ApiPort, $CeoPort)) {
    $conns = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
    if (-not $conns) {
        Write-Host "  Port $port : already free" -ForegroundColor Gray
        continue
    }

    $pids = $conns | ForEach-Object { $_.OwningProcess } | Sort-Object -Unique
    foreach ($pidOwner in $pids) {
        if ($pidOwner -le 0) {
            continue
        }

        try {
            $proc = Get-Process -Id $pidOwner -ErrorAction SilentlyContinue
            if (-not $proc) {
                continue
            }

            $name = $proc.ProcessName
            if ($ForceKill) {
                Stop-Process -Id $pidOwner -Force -ErrorAction Stop
            } else {
                $proc.CloseMainWindow() | Out-Null
                Start-Sleep -Milliseconds 500
                if (-not $proc.HasExited) {
                    Stop-Process -Id $pidOwner -Force -ErrorAction Stop
                }
            }

            Write-Host "  Port $port : stopped $name (PID $pidOwner)" -ForegroundColor Green
            $stopped++
        } catch {
            Write-Host "  Port $port : FAILED PID $pidOwner" -ForegroundColor Red
        }
    }
}

Start-Sleep -Seconds 2

Write-Host ""
$allFree = $true
foreach ($port in @($ApiPort, $CeoPort)) {
    $owner = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($owner) {
        Write-Host "  Port $port : STILL IN USE" -ForegroundColor Yellow
        $allFree = $false
    } else {
        Write-Host "  Port $port : free" -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "============================================" -ForegroundColor $(if ($allFree) { "Green" } else { "Yellow" })
Write-Host "  Stopped: $stopped processes" -ForegroundColor White
Write-Host "============================================" -ForegroundColor $(if ($allFree) { "Green" } else { "Yellow" })
Write-Host ""

if (-not $allFree) {
    Write-Host "  Run 'stop.ps1 -ForceKill' to force the official ports only." -ForegroundColor Yellow
    exit 1
}

exit 0
