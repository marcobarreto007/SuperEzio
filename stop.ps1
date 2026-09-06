# Stops only the API process recorded by start.ps1, never an arbitrary port owner.
param([switch]$ForceKill)
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "config.ps1")
$recordPath = Join-Path $RuntimeDir "api-process.json"
if (-not (Test-Path -LiteralPath $recordPath)) {
    Write-Host "No managed API process. Nothing to stop."
    exit 0
}
try {
    $record = Get-Content -LiteralPath $recordPath -Raw | ConvertFrom-Json
    $apiProcess = Get-Process -Id $record.Pid -ErrorAction SilentlyContinue
    if ($apiProcess) {
        $started = $apiProcess.StartTime.ToUniversalTime().ToString("o")
        if ($started -ne $record.StartTime) {
            Write-Error "PID was reused; refusing to stop an unrelated process."
            exit 1
        }
        Stop-Process -Id $apiProcess.Id -Force -ErrorAction Stop
        Write-Host "Stopped managed API PID $($apiProcess.Id)."
    }
    Remove-Item -LiteralPath $recordPath -Force
    exit 0
} catch {
    Write-Host "Could not stop the managed API: $($_.Exception.Message)"
    exit 1
}
