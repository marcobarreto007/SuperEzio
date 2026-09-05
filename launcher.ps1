# SuperEzio one-click launcher.
# Starts the official API server, verifies health, and opens the UI.

$ErrorActionPreference = "Continue"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

Clear-Host
Write-Host ""
Write-Host "  ========================================================" -ForegroundColor Cyan
Write-Host "       SUPEREZIO -- QUANTITATIVE AI COPILOT               " -ForegroundColor Yellow
Write-Host "  ========================================================" -ForegroundColor Cyan
Write-Host ""

$healthUrl = "http://127.0.0.1:8002/health"
$uiUrl = "http://127.0.0.1:8002"

# 1. Check if already running
$alreadyRunning = $false
try {
    $resp = Invoke-RestMethod -Uri $healthUrl -Method Get -TimeoutSec 2 -ErrorAction SilentlyContinue
    if ($resp.status -eq "ok") {
        $alreadyRunning = $true
    }
} catch {}

if ($alreadyRunning) {
    Write-Host "  [OK] SuperEzio API server ja esta em execucao na porta 8002." -ForegroundColor Green
} else {
    Write-Host "  [1/2] Iniciando servidor SuperEzio (:8002)..." -ForegroundColor Yellow

    $pyExe = "python.exe"
    $venvPy = Join-Path $ScriptDir ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $venvPy) {
        $pyExe = $venvPy
    }

    $logsDir = Join-Path $ScriptDir "runtime\logs"
    if (-not (Test-Path $logsDir)) {
        New-Item -ItemType Directory -Path $logsDir -Force | Out-Null
    }

    $env:PYTHONPATH = "src;" + $env:PYTHONPATH

    Start-Process -FilePath $pyExe `
        -ArgumentList "-m agent_server.main" `
        -WorkingDirectory $ScriptDir `
        -WindowStyle Minimized

    Write-Host "  [2/2] Aguardando prontidao da API..." -ForegroundColor Yellow
    $healthy = $false
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Seconds 1
        try {
            $check = Invoke-RestMethod -Uri $healthUrl -Method Get -TimeoutSec 1 -ErrorAction SilentlyContinue
            if ($check.status -eq "ok") {
                $healthy = $true
                break
            }
        } catch {}
        Write-Host "." -NoNewline -ForegroundColor Yellow
    }
    Write-Host ""

    if (-not $healthy) {
        Write-Host ""
        Write-Host "  [AVISO] A API esta demorando para responder em $healthUrl." -ForegroundColor Yellow
        Write-Host "  Tentando abrir a interface no navegador..." -ForegroundColor Gray
    } else {
        Write-Host "  [OK] Servidor online e saudavel!" -ForegroundColor Green
    }
}

# 2. Open browser UI
Write-Host "  [>>] Abrindo interface no navegador..." -ForegroundColor Cyan
Start-Process $uiUrl

Write-Host ""
Write-Host "  ========================================================" -ForegroundColor Green
Write-Host "    SuperEzio OPERACIONAL" -ForegroundColor Green
Write-Host "    Cockpit UI: $uiUrl" -ForegroundColor White
Write-Host "    Modelos:    Z.ai (GLM-5.3) + DeepSeek (V4 Pro)" -ForegroundColor Gray
Write-Host "  ========================================================" -ForegroundColor Green
Write-Host ""
Start-Sleep -Seconds 2
