# SuperEzio START script.
# Starts CEO (llama-server :8080) and API (FastAPI :8002), verifies health,
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

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  SuperEzio - AI Financial Copilot" -ForegroundColor Cyan
Write-Host "  Starting services..." -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

$blockedPorts = @()
foreach ($port in @($CeoPort, $ApiPort)) {
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

$bobLog = Join-Path $LogsDir "bob-$CeoPort-latest.log"
$bobErrLog = Join-Path $LogsDir "bob-$CeoPort-latest.err.log"
Remove-Item -LiteralPath $bobLog, $bobErrLog -Force -ErrorAction SilentlyContinue

if (-not $LlamaServerPath) {
    Log "ERROR: llama-server.exe not found. Set `$env:SUPEREZIO_LLAMA_SERVER_EXE or install llama.cpp." "Red"
    Log "Cannot start CEO without llama-server." "Red"
    exit 2
}

if (-not (Test-Path $ModelPath)) {
    Log "ERROR: Model not found at $ModelPath" "Red"
    Log "Download the model .gguf file to the models/ folder." "Yellow"
    exit 3
}

Log "Starting CEO (llama-server) on port $CeoPort..." "Cyan"
Log "Model: $ModelPath" "Gray"
try {
    $gpuSnap = & nvidia-smi --query-gpu=index,name,memory.total --format=csv,noheader 2>$null
    if ($gpuSnap) {
        Log "Live GPUs: $(($gpuSnap | ForEach-Object { $_.Trim() }) -join '; ')" "Gray"
    } else {
        Log "WARNING: nvidia-smi returned no live GPU. CEO may run CPU-only." "Yellow"
    }
} catch {
    Log "WARNING: nvidia-smi unavailable — CEO may fall back to CPU." "Yellow"
}

$ceoScript = Join-Path $ScriptsDir "serve_agent_llamacpp.ps1"
$ceoArgs = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", "`"$ceoScript`"",
    "-Port", "$CeoPort",
    "-LlamaServerPath", "`"$LlamaServerPath`""
)

Start-Process -FilePath "powershell.exe" `
    -ArgumentList $ceoArgs `
    -WorkingDirectory $ScriptDir `
    -WindowStyle Hidden `
    -RedirectStandardOutput $bobLog `
    -RedirectStandardError $bobErrLog

Log "Waiting for CEO (port $CeoPort)..." "Yellow"
$ceoUp = $false
$deadline = (Get-Date).AddMinutes($HealthTimeoutMinutes)
while ((Get-Date) -lt $deadline) {
    if (Test-SuperEzioHealth -Port $CeoPort -TimeoutSec 5) {
        $ceoUp = $true
        break
    }
    Write-Host "." -NoNewline -ForegroundColor Yellow
    Start-Sleep -Seconds 5
}
Write-Host ""

if ($ceoUp) {
    Log "CEO healthy on port $CeoPort" "Green"
} else {
    Log "ERROR: CEO did not become healthy within $HealthTimeoutMinutes minutes." "Red"
    Log "Check logs: $bobErrLog" "Yellow"
    exit 4
}

$apiLog = Join-Path $LogsDir "api-8002-latest.log"
$apiErrLog = Join-Path $LogsDir "api-8002-latest.err.log"
Remove-Item -LiteralPath $apiLog, $apiErrLog -Force -ErrorAction SilentlyContinue

if (-not $PythonExe) {
    Log "ERROR: Python not found. Install Python 3.12 or 3.11 and ensure it is in PATH." "Red"
    exit 5
}

Log "Starting API on port $ApiPort..." "Cyan"
Log "Python: $PythonExe" "Gray"

Start-Process -FilePath $PythonExe `
    -ArgumentList @("-m", "agent_server.main") `
    -WorkingDirectory $ScriptDir `
    -WindowStyle Hidden `
    -RedirectStandardOutput $apiLog `
    -RedirectStandardError $apiErrLog

Log "Waiting for API (port $ApiPort)..." "Yellow"
$apiUp = $false
$deadline = (Get-Date).AddMinutes(3)
while ((Get-Date) -lt $deadline) {
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
} else {
    Log "ERROR: API did not become healthy within 3 minutes." "Red"
    Log "Check logs: $apiErrLog" "Yellow"
    exit 6
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  SuperEzio is running" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host "  CEO  : http://127.0.0.1:$CeoPort/v1" -ForegroundColor White
Write-Host "  API  : http://127.0.0.1:$ApiPort" -ForegroundColor White
Write-Host "  UI   : http://127.0.0.1:$ApiPort" -ForegroundColor White
Write-Host "  Logs : $LogsDir" -ForegroundColor Gray
Write-Host "============================================" -ForegroundColor Green
Write-Host ""

if (-not $SkipBrowser) {
    $uiUrl = "http://127.0.0.1:$ApiPort"
    Log "Opening browser: $uiUrl" "Cyan"
    Start-Process $uiUrl
}

Log "Startup complete. Run stop.ps1 to shut down." "Green"
exit 0
