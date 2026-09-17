# Stops the API process recorded by start.ps1. When no record exists (or the
# record is stale), it falls back to the verified owner of $ApiPort — a process
# started by hand still has to stop, or start.ps1 refuses to start ("Run stop.ps1
# first") while the old process keeps serving. Never a blind kill by name: every
# PID must pass the identity check below.
param([switch]$ForceKill)
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "config.ps1")
$recordPath = Join-Path $RuntimeDir "api-process.json"

# Identity of the API: a Python interpreter running agent_server.main. The port
# owner is only killed when it answers yes; Get-CimInstance answers nothing
# (permissions, or the process is gone) means "not verified", not "go ahead".
function Test-SuperEzioApiProcess {
    param([Parameter(Mandatory = $true)][int]$ProcessId)
    $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if (-not $process) { return $false }
    if ($process.ProcessName -notmatch '^python(w)?$') { return $false }
    try {
        $commandLine = (Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction Stop).CommandLine
    } catch { return $false }
    if (-not $commandLine) { return $false }
    return ($commandLine -match 'agent_server\.main')
}

$stopped = $false
if (Test-Path -LiteralPath $recordPath) {
    try {
        $record = Get-Content -LiteralPath $recordPath -Raw | ConvertFrom-Json
        $apiProcess = Get-Process -Id $record.Pid -ErrorAction SilentlyContinue
        if ($apiProcess) {
            $started = $apiProcess.StartTime.ToUniversalTime().ToString("o")
            if ($started -ne $record.StartTime) {
                Write-Host "Recorded PID $($record.Pid) was reused by '$($apiProcess.ProcessName)'; refusing to stop it." -ForegroundColor Yellow
            } else {
                Stop-Process -Id $apiProcess.Id -Force -ErrorAction Stop
                Write-Host "Stopped managed API PID $($apiProcess.Id)."
                $stopped = $true
            }
        } else {
            Write-Host "Recorded API PID $($record.Pid) no longer exists."
        }
        Remove-Item -LiteralPath $recordPath -Force
    } catch {
        Write-Host "Could not stop the managed API: $($_.Exception.Message)"
        exit 1
    }
} else {
    Write-Host "No managed API process is recorded."
}

# Stop Bridge MIKE <-> Ezio (:8009)
$bridgeStop = Join-Path $PSScriptRoot "bridge\stop.ps1"
if (Test-Path -LiteralPath $bridgeStop) {
    try { & $bridgeStop } catch {}
}

$heartIngestStop = Join-Path $PSScriptRoot "scripts\ops\stop_heart_ingest.ps1"
if (Test-Path -LiteralPath $heartIngestStop) {
    try { & $heartIngestStop } catch {}
}

$owner = Get-SuperEzioPortOwner -Port $ApiPort
if (-not $owner) {
    if ($stopped) { Write-Host "Port $ApiPort is free." }
    else { Write-Host "Nothing to stop: port $ApiPort is free." }
    exit 0
}

Write-Host "Port $ApiPort is held by PID $($owner.Pid) ($($owner.ProcessName))." -ForegroundColor Yellow
if (Test-SuperEzioApiProcess -ProcessId $owner.Pid) {
    Stop-Process -Id $owner.Pid -Force -ErrorAction Stop
    Write-Host "Stopped unmanaged API PID $($owner.Pid) ($($owner.ProcessName)) holding port $ApiPort." -ForegroundColor Green
    exit 0
}

if ($ForceKill) {
    Stop-Process -Id $owner.Pid -Force -ErrorAction Stop
    Write-Host "Stopped PID $($owner.Pid) ($($owner.ProcessName)) on port $ApiPort (-ForceKill)." -ForegroundColor Yellow
    exit 0
}

Write-Host "PID $($owner.Pid) ($($owner.ProcessName)) does not look like the SuperEzio API (not python running agent_server.main); refusing to stop it." -ForegroundColor Red
Write-Host "If it is yours, stop it yourself: Stop-Process -Id $($owner.Pid) -Force" -ForegroundColor Yellow
Write-Host "Or re-run: .\stop.ps1 -ForceKill" -ForegroundColor Yellow
exit 1
