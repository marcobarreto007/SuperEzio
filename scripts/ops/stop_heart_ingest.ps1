# Stop the dedicated Heart ingest process recorded by start_heart_ingest.ps1.
$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
. (Join-Path $Repo "config.ps1")
$pidFile = Join-Path $RuntimeDir "heart-ingest.pid"
if (-not (Test-Path -LiteralPath $pidFile)) {
    Write-Host "No heart-ingest.pid"
    exit 0
}
$old = 0
[void][int]::TryParse((Get-Content -LiteralPath $pidFile -ErrorAction SilentlyContinue), [ref]$old)
Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
if ($old -le 0) { exit 0 }
$proc = Get-Process -Id $old -ErrorAction SilentlyContinue
if (-not $proc) {
    Write-Host "Heart ingest PID $old already gone"
    exit 0
}
if ($proc.ProcessName -notmatch '^python(w)?$') {
    Write-Host "PID $old is not python; refusing to kill."
    exit 1
}
Stop-Process -Id $old -Force
Write-Host "Stopped heart ingest PID $old"
