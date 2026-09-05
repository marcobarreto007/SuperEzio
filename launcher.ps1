# SuperEzio one-click launcher.
# Starts the official API server, verifies health, and opens the UI.

$ErrorActionPreference = "Continue"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

Clear-Host
Write-Host ""
Write-Host "  ========================================================" -ForegroundColor Cyan
Write-Host "       🦅  SUPEREZIO — QUANTITATIVE AI COPILOT  🦅       " -ForegroundColor Yellow
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

$serverProcess = $null

if ($alreadyRunning) {
    Write-Host "  [OK] SuperEzio API server já está em execução na porta 8002." -ForegroundColor Green
} else {
    Write-Host "  [1/2] Iniciando servidor SuperEzio (:8002)..." -ForegroundColor Yellow

    # Resolve Python interpreter (.venv preferred, fallback to system)
    $pyExe = Join-Path $ScriptDir ".venv\Scripts\python.exe"
    if (-not (Test-Path $pyExe)) {
        $pyExe = "python.exe"
    }

    $logsDir = Join-Path $ScriptDir "runtime\logs"
    if (-not (Test-Path $logsDir)) {
        New-Item -ItemType Directory -Path $logsDir -Force | Out-Null
    }
    $logFile = Join-Path $logsDir "server_launcher.log"

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $pyExe
    $psi.Arguments = "-m agent_server.main"
    $psi.WorkingDirectory = $ScriptDir
    $psi.EnvironmentVariables["PYTHONPATH"] = "src;" + $env:PYTHONPATH
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true

    $serverProcess = [System.Diagnostics.Process]::Start($psi)

    Write-Host "  [2/2] Aguardando prontidão da API..." -ForegroundColor Yellow
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
        Write-Host "  [FAIL] A API não respondeu a tempo em $healthUrl." -ForegroundColor Red
        Write-Host "  Verifique os logs em $logFile" -ForegroundColor Yellow
        Read-Host "Pressione Enter para sair..."
        exit 1
    }
    Write-Host "  [OK] Servidor online e saudável!" -ForegroundColor Green
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
Write-Host "  Pressione Enter para parar o servidor ou feche a janela para mantê-lo ativo." -ForegroundColor Yellow
Read-Host | Out-Null

if ($serverProcess -and -not $serverProcess.HasExited) {
    Write-Host "  Encerrando servidor SuperEzio..." -ForegroundColor Yellow
    $serverProcess.Kill()
    Write-Host "  Servidor encerrado." -ForegroundColor Green
    Start-Sleep -Seconds 1
}

