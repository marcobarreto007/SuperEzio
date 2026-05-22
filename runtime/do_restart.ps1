# SuperEzio hard restart: kill stale servers, start CEO+API, verify health.
$ErrorActionPreference = 'Continue'
$root = 'C:\Users\marco\Desktop\SuperEzio'
$logPath = Join-Path $root 'runtime\restart_log.txt'
New-Item -ItemType Directory -Force -Path (Join-Path $root 'runtime') | Out-Null

$lines = [System.Collections.Generic.List[string]]::new()
function Log([string]$m) {
    $lines.Add("$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $m")
}

Log '=== SuperEzio restart ==='
$killed = [System.Collections.Generic.List[string]]::new()
$errors = [System.Collections.Generic.List[string]]::new()

function Kill-Port([int]$port) {
    Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue | ForEach-Object {
        $pid = [int]$_.OwningProcess
        if ($pid -le 0) { return }
        try {
            $name = (Get-Process -Id $pid -ErrorAction SilentlyContinue).ProcessName
            Stop-Process -Id $pid -Force -ErrorAction Stop
            $killed.Add("Port $port PID $pid ($name)")
        }
        catch {
            $errors.Add("Port $port PID $pid : $($_.Exception.Message)")
        }
    }
}

foreach ($p in 8082, 8002, 5173, 3000) { Kill-Port $p }

$patterns = @('SuperEzio', 'agent_server', 'serve_ceo_llamacpp', 'llama-server', 'llama.cpp')
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | ForEach-Object {
    $cmd = $_.CommandLine
    if (-not $cmd) { return }
    foreach ($pat in $patterns) {
        if ($cmd -like "*$pat*") {
            try {
                Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop
                $killed.Add("Pattern '$pat' PID $($_.ProcessId)")
            }
            catch {
                $errors.Add("PID $($_.ProcessId) : $($_.Exception.Message)")
            }
            break
        }
    }
}

Start-Sleep -Seconds 2

Log "PIDs killed ($($killed.Count)):"
($killed | Sort-Object -Unique) | ForEach-Object { Log "  $_" }
if ($errors.Count -gt 0) {
    Log 'Errors:'
    $errors | ForEach-Object { Log "  $_" }
}

function Get-PortStatus([int]$port) {
    $l = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if ($l) { return "IN_USE PID $($l[0].OwningProcess)" }
    return 'FREE'
}

Log "Port 8082: $(Get-PortStatus 8082)"
Log "Port 8002: $(Get-PortStatus 8002)"

Set-Location $root
$env:PYTHONPATH = Join-Path $root 'src'
$env:SUPEREZIO_NO_BROWSER = '1'
$env:SUPEREZIO_PROFESSIONAL_COLLECTOR = 'true'

try {
    $bat = Join-Path $root 'desktop\SuperEzio.bat'
    $p = Start-Process cmd.exe -ArgumentList '/c', "`"$bat`"" -WorkingDirectory $root -PassThru -WindowStyle Normal
    Log "Started desktop\SuperEzio.bat launcher PID $($p.Id)"
}
catch {
    Log "BAT failed: $($_.Exception.Message) — starting CEO + API manually"
    Start-Process powershell -ArgumentList '-ExecutionPolicy', 'Bypass', '-File', 'scripts\serve_ceo_llamacpp.ps1', '-Port', '8082' -WorkingDirectory $root -WindowStyle Normal
    $py = Join-Path $root '.venv\Scripts\python.exe'
    if (-not (Test-Path $py)) { $py = 'python' }
    Start-Process -FilePath $py -ArgumentList '-m', 'agent_server.main' -WorkingDirectory $root -WindowStyle Normal
}

$h8082 = 'NOT OK'
$h8002 = 'NOT OK'
$deadline = (Get-Date).AddMinutes(6)
while ((Get-Date) -lt $deadline) {
    try {
        $r = Invoke-WebRequest 'http://127.0.0.1:8082/health' -UseBasicParsing -TimeoutSec 8
        $h8082 = "$($r.StatusCode) $($r.Content)"
    }
    catch {
        $h8082 = "pending: $($_.Exception.Message)"
    }
    try {
        $r = Invoke-WebRequest 'http://127.0.0.1:8002/health' -UseBasicParsing -TimeoutSec 8
        $h8002 = "$($r.StatusCode) $($r.Content)"
    }
    catch {
        $h8002 = "pending: $($_.Exception.Message)"
    }
    if (($h8082 -match '^\s*200\b') -and ($h8002 -match '^\s*200\b')) { break }
    Start-Sleep -Seconds 4
}

Log "Health 8082: $h8082"
Log "Health 8002: $h8002"
$up = ($h8082 -match '^\s*200\b') -and ($h8002 -match '^\s*200\b')
Log "Servers up: $up"
Log "UI: http://127.0.0.1:8002"

$lines | Set-Content -Path $logPath -Encoding UTF8
Write-Host ''
Write-Host '--- restart_log.txt ---'
Get-Content $logPath
if (-not $up) { exit 1 }
exit 0
