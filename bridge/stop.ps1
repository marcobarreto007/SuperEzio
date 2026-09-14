# Para SOMENTE o processo do bridge registrado pelo start.ps1, nunca um dono de
# porta qualquer. Mesmo padrao verificado do SuperEzio/stop.ps1:14-18: confere o
# StartTime gravado e recusa matar PID que foi reutilizado por outro processo.

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$recordPath = Join-Path (Join-Path $ScriptDir "runtime") "bridge-process.json"

if (-not (Test-Path -LiteralPath $recordPath)) {
    Write-Host "Nenhum processo do bridge registrado. Nada a parar."
    exit 0
}

try {
    $record = Get-Content -LiteralPath $recordPath -Raw | ConvertFrom-Json
    $bridgeProcess = Get-Process -Id $record.Pid -ErrorAction SilentlyContinue
    if ($bridgeProcess) {
        $started = $bridgeProcess.StartTime.ToUniversalTime().ToString("o")
        if ($started -ne $record.StartTime) {
            Write-Error "PID foi reutilizado; recusando matar um processo alheio."
            exit 1
        }
        Stop-Process -Id $bridgeProcess.Id -Force -ErrorAction Stop
        Write-Host "Bridge parado (PID $($bridgeProcess.Id))."
    } else {
        Write-Host "PID $($record.Pid) nao existe mais; removendo o registro."
    }
    Remove-Item -LiteralPath $recordPath -Force
    exit 0
} catch {
    Write-Host "Nao foi possivel parar o bridge: $($_.Exception.Message)"
    exit 1
}
