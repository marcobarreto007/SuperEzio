# Heart ingest as its own process. Does not need FastAPI :8002.
param([switch]$Once)

$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $Repo
. (Join-Path $Repo "config.ps1")

if (-not $env:SUPEREZIO_HEART_USER_AGENT) {
    $env:SUPEREZIO_HEART_USER_AGENT = "SuperEzioHeart/1.0 (marco@example.com)"
}

$python = Join-Path $Repo ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "venv python not found: $python"
}

if ($Once) {
    & $python -m core.heart --once
    exit $LASTEXITCODE
}

$pidFile = Join-Path $RuntimeDir "heart-ingest.pid"
$logsDir = Join-Path $Repo "runtime\logs"
New-Item -ItemType Directory -Force -Path $logsDir | Out-Null

if (Test-Path -LiteralPath $pidFile) {
    $old = 0
    [void][int]::TryParse((Get-Content -LiteralPath $pidFile -ErrorAction SilentlyContinue), [ref]$old)
    if ($old -gt 0) {
        $alive = Get-Process -Id $old -ErrorAction SilentlyContinue
        if ($alive) {
            Write-Host "Heart ingest already running PID $old"
            exit 0
        }
    }
}

$stdout = Join-Path $logsDir "heart_ingest_stdout.log"
$stderr = Join-Path $logsDir "heart_ingest_stderr.log"
$proc = Start-Process -FilePath $python `
    -ArgumentList @("-m", "core.heart") `
    -WorkingDirectory $Repo `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdout `
    -RedirectStandardError $stderr `
    -PassThru
$proc.Id | Set-Content -LiteralPath $pidFile -Encoding ascii
Write-Host "Heart ingest process PID $($proc.Id) (independent of :8002)"
