# Bridge MIKE <-> SuperEzio START.
# Sobe o bridge (uvicorn) em 127.0.0.1:8009 via `python -m bridge.main`.
# Padrao de PID copiado do SuperEzio/start.ps1:103 - PID + StartTime em JSON,
# para o stop.ps1 conseguir recusar matar PID reutilizado.

param(
    [int]$HealthTimeoutMinutes = 2
)

$ErrorActionPreference = "Continue"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir
Set-Location $ScriptDir

$RuntimeDir = Join-Path $ScriptDir "runtime"
$LogsDir = Join-Path $RuntimeDir "logs"
foreach ($directory in @($RuntimeDir, $LogsDir)) {
    if (-not (Test-Path -LiteralPath $directory)) {
        New-Item -ItemType Directory -Force -Path $directory | Out-Null
    }
}

# Bind: loopback, sempre. Nao existe parametro nem env para mudar isso.
$BindHost = "127.0.0.1"
$Port = if ($env:BRIDGE_PORT) { [int]$env:BRIDGE_PORT } else { 8009 }

function Log {
    param([string]$Msg, [string]$Color = "White")
    $line = "$(Get-Date -Format 'HH:mm:ss') $Msg"
    Write-Host $line -ForegroundColor $Color
    Add-Content -Path (Join-Path $LogsDir "bridge-startup.log") -Value $line -ErrorAction SilentlyContinue
}

function Resolve-BridgePython {
    $candidates = @(
        @{ Command = (Join-Path $RepoRoot ".venv\Scripts\python.exe"); Arguments = @() },
        @{ Command = "python"; Arguments = @() },
        @{ Command = "py"; Arguments = @("-3.12") },
        @{ Command = "py"; Arguments = @("-3") }
    )
    foreach ($candidate in $candidates) {
        try {
            $probe = & $candidate.Command @($candidate.Arguments) -c "import sys; print(sys.executable); raise SystemExit(0 if sys.version_info >= (3, 12) else 42)" 2>&1
            if ($LASTEXITCODE -ne 0) { continue }
            $exe = ($probe | Select-Object -First 1).ToString().Trim()
            if ($exe -and (Test-Path -LiteralPath $exe)) { return (Resolve-Path -LiteralPath $exe).Path }
        } catch {}
    }
    return $null
}

$pythonExe = Resolve-BridgePython
if (-not $pythonExe) {
    Log "ERROR: Python 3.12+ nao encontrado." "Red"
    exit 5
}

$owner = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($owner) {
    Log "ERROR: porta $Port ja esta em uso (PID $($owner.OwningProcess)). Rode stop.ps1 antes." "Red"
    exit 7
}

$outLog = Join-Path $LogsDir "bridge-latest.log"
$errLog = Join-Path $LogsDir "bridge-latest.err.log"
Remove-Item -LiteralPath $outLog, $errLog -Force -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  MIKE <-> SuperEzio bridge" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Log "Python: $pythonExe" "Gray"
Log "Subindo bridge em http://${BindHost}:$Port ..." "Cyan"

$process = Start-Process -FilePath $pythonExe `
    -ArgumentList @("-m", "bridge.main") `
    -WorkingDirectory $RepoRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput $outLog `
    -RedirectStandardError $errLog `
    -PassThru -ErrorAction Stop

@{ Pid = $process.Id; StartTime = $process.StartTime.ToUniversalTime().ToString("o") } |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $RuntimeDir "bridge-process.json")

Log "Aguardando /health na porta $Port ..." "Yellow"
$up = $false
$deadline = (Get-Date).AddMinutes($HealthTimeoutMinutes)
while ((Get-Date) -lt $deadline) {
    if ($process.HasExited) { break }
    try {
        $response = Invoke-WebRequest "http://${BindHost}:$Port/health" -UseBasicParsing -TimeoutSec 5
        if ($response.StatusCode -eq 200) { $up = $true; break }
    } catch {}
    Write-Host "." -NoNewline -ForegroundColor Yellow
    Start-Sleep -Seconds 2
}
Write-Host ""

if (-not $up) {
    if (-not $process.HasExited) { $process | Stop-Process -Force }
    Log "ERROR: bridge nao ficou saudavel em $HealthTimeoutMinutes minuto(s)." "Red"
    Log "Veja: $errLog" "Yellow"
    exit 6
}

Log "Bridge no ar (PID $($process.Id))." "Green"
Log "Sem credencial (decisao 12/09/2026): fronteira = bind 127.0.0.1 + allowlist default-deny." "Gray"
Log "Logs: $LogsDir" "Gray"
exit 0
