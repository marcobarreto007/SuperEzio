# SuperEzio START script.
# Starts API (FastAPI :8002) with the configured external model providers,
# then opens the browser unless -SkipBrowser is provided.

param(
    [switch]$SkipBrowser,
    [switch]$IsolatedValidation,
    [int]$HealthTimeoutMinutes = 6
)

$ErrorActionPreference = "Continue"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

$configPath = Join-Path $ScriptDir "config.ps1"
if (-not (Test-Path $configPath)) {
    Write-Host "ERROR: config.ps1 not found. Run this from the SuperEzio root folder." -ForegroundColor Red
    exit 1
}
. $configPath

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$env:SUPEREZIO_VALIDATION_MODE = "0"
if ($IsolatedValidation) {
    $env:SUPEREZIO_VALIDATION_MODE = "1"
    $validationRoot = Join-Path $RuntimeDir "validation\$timestamp"
    $script:LogsDir = Join-Path $validationRoot "logs"
    $env:SUPEREZIO_DATA_DIR = Join-Path $validationRoot "data"
    $env:SUPEREZIO_TRACE_DIR = Join-Path $validationRoot "traces"
    $env:SUPEREZIO_DECISION_TRACE_DB = Join-Path $validationRoot "decision-traces.sqlite3"
    $env:SUPEREZIO_SENTIMENT_DB = Join-Path $validationRoot "sentiment.sqlite3"
    $env:SUPEREZIO_TRADING_STATE_DB = Join-Path $validationRoot "trading-state.sqlite3"
    $env:SUPEREZIO_DEDUP_DIR = Join-Path $validationRoot "dedup"
    $env:SUPEREZIO_DEAD_LETTER_DIR = Join-Path $validationRoot "dead-letter"
    $env:SUPEREZIO_FEEDBACK_DIR = Join-Path $validationRoot "feedback"
    $env:SUPEREZIO_CACHE_DIR = Join-Path $validationRoot "cache"
    $env:SUPEREZIO_RAG_INDEX_DIR = Join-Path $validationRoot "rag-index"
    $env:SUPEREZIO_BOB_PAIN_LOG = Join-Path $validationRoot "bob-pain-log.jsonl"
    $env:SUPEREZIO_ANS_SCAN = "0"
    $env:SUPEREZIO_MANGALA_SCAN = "0"
    $env:SUPEREZIO_CORPO_HEARTBEAT = "0"
    $env:SUPEREZIO_HEART_INGEST = "0"
    $env:F51_TRADING_EXECUTION_FREEZE = "1"
    $env:SUPEREZIO_LIVE_TRADING_DISABLED = "1"
    $env:SUPEREZIO_ENABLE_PAPER_ORDER_SUBMIT = "0"
    Write-Host "Validation storage: $validationRoot" -ForegroundColor Yellow
}

Initialize-SuperEzioDirs

$startupLog = Join-Path $LogsDir "startup-$timestamp.log"

function Log {
    param([string]$Msg, [string]$Color = "White")
    $line = "$(Get-Date -Format 'HH:mm:ss') $Msg"
    Write-Host $line -ForegroundColor $Color
    Add-Content -Path $startupLog -Value $line
}

if (-not $env:SUPEREZIO_HEART_USER_AGENT) {
    foreach ($envFile in @((Join-Path $ScriptDir ".env"), (Join-Path $ScriptDir ".env.local"))) {
        if (Test-Path -LiteralPath $envFile) {
            $uaLine = Select-String -Path $envFile -Pattern '^SUPEREZIO_HEART_USER_AGENT=(.+)$' | Select-Object -First 1
            if ($uaLine) {
                $uaVal = $uaLine.Matches[0].Groups[1].Value.Trim().Trim('"').Trim("'")
                if ($uaVal) {
                    $env:SUPEREZIO_HEART_USER_AGENT = $uaVal
                    break
                }
            }
        }
    }
}
if (-not $env:SUPEREZIO_HEART_USER_AGENT) {
    $env:SUPEREZIO_HEART_USER_AGENT = "SuperEzioHeart/1.0 (marco@example.com)"
    Log "Heart UA: default local contact (override SUPEREZIO_HEART_USER_AGENT)" "Yellow"
}
if (-not $IsolatedValidation) {
    # Dedicated python -m core.heart process owns ingest; API embed must not duplicate it.
    $env:SUPEREZIO_HEART_INGEST = "0"
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  SuperEzio - AI Financial Copilot" -ForegroundColor Cyan
Write-Host "  Starting services..." -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

$blockedPorts = @()
foreach ($port in @($ApiPort)) {
    $owner = Get-SuperEzioPortOwner -Port $port
    if ($owner) {
        $blockedPorts += $owner
    }
}

if ($blockedPorts.Count -gt 0) {
    Log "ERROR: Required port(s) are already in use." "Red"
    foreach ($owner in $blockedPorts) {
        Log "Port $($owner.Port): PID $($owner.Pid) ($($owner.ProcessName))" "Red"
    }
    Log "Run stop.ps1 first, then run start.ps1 again." "Yellow"
    exit 7
}

$apiLog = Join-Path $LogsDir "api-$ApiPort-latest.log"
$apiErrLog = Join-Path $LogsDir "api-$ApiPort-latest.err.log"
Remove-Item -LiteralPath $apiLog, $apiErrLog -Force -ErrorAction SilentlyContinue

if (-not $PythonExe) {
    Log "ERROR: Python not found. Install Python 3.12 or 3.11 and ensure it is in PATH." "Red"
    exit 5
}

Log "Starting API on port $ApiPort..." "Cyan"
Log "Python: $PythonExe" "Gray"

# IBKR Gateway paper nesta maquina (:4002). So process env — nunca reescrever .env.
if (-not $env:IBKR_PORT) { $env:IBKR_PORT = "4002" }
if (-not $env:IBKR_HOST) { $env:IBKR_HOST = "127.0.0.1" }

$apiProcess = Start-Process -FilePath $PythonExe `
    -ArgumentList @("-m", "agent_server.main") `
    -WorkingDirectory $ScriptDir `
    -WindowStyle Hidden `
    -RedirectStandardOutput $apiLog `
    -RedirectStandardError $apiErrLog `
    -PassThru -ErrorAction Stop

@{ Pid = $apiProcess.Id; StartTime = $apiProcess.StartTime.ToUniversalTime().ToString("o") } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $RuntimeDir "api-process.json")

Log "Waiting for API (port $ApiPort)..." "Yellow"
$apiUp = $false
$deadline = (Get-Date).AddMinutes($HealthTimeoutMinutes)
while ((Get-Date) -lt $deadline) {
    if ($apiProcess.HasExited) { break }
    if (Test-SuperEzioHealth -Port $ApiPort -TimeoutSec 5) {
        $apiUp = $true
        break
    }
    Write-Host "." -NoNewline -ForegroundColor Yellow
    Start-Sleep -Seconds 3
}
Write-Host ""

if ($apiUp) {
    Log "API healthy on port $ApiPort" "Green"
    
    # Bridge MIKE <-> Ezio (:8009)
    $bridgeStart = Join-Path $ScriptDir "bridge\start.ps1"
    if (Test-Path -LiteralPath $bridgeStart) {
        try {
            & $bridgeStart -HealthTimeoutMinutes 1
        } catch {
            Log "Bridge em standby: $($_.Exception.Message)" "Yellow"
        }
    }

    if (-not $IsolatedValidation) {
        $heartIngestStart = Join-Path $ScriptDir "scripts\ops\start_heart_ingest.ps1"
        if (Test-Path -LiteralPath $heartIngestStart) {
            try {
                & $heartIngestStart
            } catch {
                Log "Heart ingest process em standby: $($_.Exception.Message)" "Yellow"
            }
        }
    }
} else {
    if (-not $apiProcess.HasExited) { $apiProcess | Stop-Process -Force }
    Log "ERROR: API did not become healthy within $HealthTimeoutMinutes minutes." "Red"
    Log "Check logs: $apiErrLog" "Yellow"
    exit 6
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  SuperEzio is running" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host "  AI     : configured external APIs" -ForegroundColor White
Write-Host "  API    : http://127.0.0.1:$ApiPort" -ForegroundColor White
Write-Host "  UI     : http://127.0.0.1:$ApiPort" -ForegroundColor White
Write-Host "  Bridge : http://127.0.0.1:8009" -ForegroundColor White
Write-Host "  Logs   : $LogsDir" -ForegroundColor Gray
Write-Host "============================================" -ForegroundColor Green
Write-Host ""

if (-not $SkipBrowser) {
    $uiUrl = "http://127.0.0.1:$ApiPort"
    Log "Opening browser: $uiUrl" "Cyan"
    Start-Process $uiUrl
}

Log "Startup complete. Run stop.ps1 to shut down." "Green"
exit 0
