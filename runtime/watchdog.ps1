$root = 'C:\Users\marco\Desktop\SuperEzio Financeiro'
$logFile = Join-Path $root 'runtime\logs\watchdog.log'

# Rotate if > 1 MB
if (Test-Path $logFile) {
    $size = (Get-Item $logFile).Length
    if ($size -gt 1MB) {
        $bak = $logFile -replace '\.log$', '.bak.log'
        Move-Item $logFile $bak -Force
    }
}

function log($m) {
    $ts = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    $line = $ts + ' ' + $m
    try {
        Add-Content -Path $logFile -Value $line -Encoding UTF8 -ErrorAction Stop
    } catch {
        Write-Host "[WATCHDOG] Failed to write log: $_" -ForegroundColor Yellow
    }
}

log '=== SuperEzio Watchdog started ==='
log "Interval: 30s | Max failures: 3 | PID: $PID"

$i = 0
$consecutive_failures = 0
$max_consecutive_failures = 3
$restart_cooldown_s = 120  # don't restart more than once every 2 minutes
$last_restart_ts = [datetime]::MinValue

while ($true) {
    $i++
    try {
        # Wrap each check in its own try/catch so one failure doesn't abort the loop
        try {
            $r8082 = Invoke-WebRequest 'http://127.0.0.1:8082/health' -UseBasicParsing -TimeoutSec 10
            $ok8082 = ($r8082.StatusCode -eq 200)
        } catch {
            $ok8082 = $false
            log "8082 check error: $_"
        }

        try {
            $r8002 = Invoke-WebRequest 'http://127.0.0.1:8002/health' -UseBasicParsing -TimeoutSec 10
            $ok8002 = ($r8002.StatusCode -eq 200)
        } catch {
            $ok8002 = $false
            log "8002 check error: $_"
        }

        $s8082 = if ($ok8082) { 'UP' } else { 'DOWN' }
        $s8002 = if ($ok8002) { 'UP' } else { 'DOWN' }

        if (-not $ok8082 -or -not $ok8002) {
            $consecutive_failures++
            log "Pulse #${i}: 8082=${s8082} 8002=${s8002} failures=${consecutive_failures}/${max_consecutive_failures}"
        } else {
            if ($consecutive_failures -gt 0) {
                log "Pulse #${i}: 8082=${s8082} 8002=${s8002} (recovered after ${consecutive_failures} failures)"
            }
            $consecutive_failures = 0
        }

        if ($consecutive_failures -ge $max_consecutive_failures) {
            $now = Get-Date
            $elapsed = ($now - $last_restart_ts).TotalSeconds
            if ($elapsed -lt $restart_cooldown_s) {
                log "RESTART skipped — cooldown active (last restart ${elapsed}s ago)"
            } else {
                log "RESTART triggered — ${consecutive_failures} consecutive failures"
                $last_restart_ts = $now
                $restart = Join-Path $root 'runtime\do_restart.ps1'
                if (Test-Path $restart) {
                    try {
                        $proc = Start-Process powershell -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File',$restart -PassThru -Wait -WindowStyle Hidden
                        log "Restart completed (exit code: $($proc.ExitCode))"
                    } catch {
                        log "Restart FAILED: $_"
                    }
                } else {
                    log "RESTART skipped — do_restart.ps1 not found at $restart"
                }
                $consecutive_failures = 0
            }
            Start-Sleep -Seconds 15
        }
    } catch {
        log "Pulse #${i}: UNHANDLED ERROR: $_"
        # Don't let a single unhandled error kill the watchdog
    }

    Start-Sleep -Seconds 30
}
