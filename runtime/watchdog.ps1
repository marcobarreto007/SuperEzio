$root = 'C:\Users\marco\Desktop\SuperEzio Financeiro'
$logFile = Join-Path $root 'runtime\logs\watchdog.log'
Remove-Item $logFile -Force -ErrorAction SilentlyContinue

function log($m) {
    $ts = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    $line = $ts + ' ' + $m
    Add-Content -Path $logFile -Value $line -Encoding UTF8
}

log 'Watchdog started (30s interval)'

$i = 0
while ($true) {
    $i++
    try {
        $r8082 = Invoke-WebRequest 'http://127.0.0.1:8082/health' -UseBasicParsing -TimeoutSec 5
        $ok8082 = ($r8082.StatusCode -eq 200)
    } catch { $ok8082 = $false }
    
    try {
        $r8002 = Invoke-WebRequest 'http://127.0.0.1:8002/health' -UseBasicParsing -TimeoutSec 5
        $ok8002 = ($r8002.StatusCode -eq 200)
    } catch { $ok8002 = $false }
    
    $s8082 = if ($ok8082) { 'UP' } else { 'DOWN' }
    $s8002 = if ($ok8002) { 'UP' } else { 'DOWN' }
    log ('#' + $i + ' 8082=' + $s8082 + ' 8002=' + $s8002)
    
    if (-not $ok8082 -or -not $ok8002) {
        log 'RESTART triggered'
        $restart = Join-Path $root 'runtime\do_restart.ps1'
        Start-Process powershell -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File',$restart -Wait -WindowStyle Hidden
        log 'Restart completed'
        Start-Sleep -Seconds 15
    }
    
    Start-Sleep -Seconds 30
}
