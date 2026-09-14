param(
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location -LiteralPath $ProjectRoot

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "       SUPEREZIO -- REINICIAR SERVIDORES (:8002)            " -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# 1. PARAR PROCESSO EXISTENTE VIA STOP.PS1 OFICIAL
Write-Host "[1/2] Parando servidores existentes do SuperEzio..." -ForegroundColor Yellow
$stopScript = Join-Path $ProjectRoot "stop.ps1"
if (Test-Path -LiteralPath $stopScript) {
    try {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $stopScript -ForceKill
    } catch {
        Write-Host "Aviso ao parar: $($_.Exception.Message)" -ForegroundColor Yellow
    }
}

# 2. INICIAR PROCESSO VIA START.PS1 OFICIAL
Write-Host ""
Write-Host "[2/2] Iniciando servidores do SuperEzio com codigo atual..." -ForegroundColor Cyan
$startScript = Join-Path $ProjectRoot "start.ps1"
if (Test-Path -LiteralPath $startScript) {
    $startArgs = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $startScript)
    if ($NoBrowser) {
        $startArgs += "-SkipBrowser"
    }
    & powershell.exe @startArgs
} else {
    Write-Host "[ERRO] start.ps1 nao encontrado em $startScript" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  REINICIALIZACAO CONCLUIDA!                                 " -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""
Start-Sleep -Seconds 2
