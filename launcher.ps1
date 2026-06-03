# SuperEzio one-click launcher.
# Starts the validated local stack, opens the UI, and stops services on Enter.

$ErrorActionPreference = "Continue"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

$startScript = Join-Path $ScriptDir "start.ps1"
$stopScript = Join-Path $ScriptDir "stop.ps1"

Clear-Host
Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  SuperEzio - AI Financial Copilot" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Path -LiteralPath $startScript) -or -not (Test-Path -LiteralPath $stopScript)) {
    Write-Host "ERROR: start.ps1 or stop.ps1 not found in $ScriptDir" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "[1/3] Stopping any service on official SuperEzio ports..." -ForegroundColor Yellow
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $stopScript | Out-Host

Write-Host "[2/3] Starting SuperEzio..." -ForegroundColor Yellow
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $startScript -SkipBrowser
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "ERROR: SuperEzio did not start cleanly." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit $LASTEXITCODE
}

Write-Host "[3/3] Opening UI..." -ForegroundColor Yellow
Start-Process "http://127.0.0.1:8002"

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  SuperEzio READY" -ForegroundColor Green
Write-Host "  UI: http://127.0.0.1:8002" -ForegroundColor White
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
Write-Host "Press Enter to stop SuperEzio services." -ForegroundColor Yellow
Read-Host | Out-Null

Write-Host ""
Write-Host "Stopping services..." -ForegroundColor Yellow
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $stopScript | Out-Host
Write-Host "SuperEzio stopped." -ForegroundColor Green
Start-Sleep -Seconds 1
