# SuperEzio CEO watchdog (ZERO-CLOUD).
# Mantem o llama-server :8080 vivo. Causa raiz da queda de 2026-08-23:
# serve_agent_llamacpp.ps1 roda o modelo em foreground, preso a janela que o
# iniciou — janela fechada matou o processo e nada religou (49 min em
# MAN_AT_WORK). Este watchdog desacopla a vida do modelo da janela.
#
# Comportamento:
#   - a cada $IntervalSec segundos checa o /health do llama-server;
#   - health ok -> reseta falhas e dorme;
#   - health falhou e processo existe -> conta ciclo de graca (modelo
#     carregando), nao mata nada;
#   - health falhou por $GraceCycles ciclos e NAO ha processo -> relanca o
#     serve DETACHED (janela escondida), com log proprio;
#   - max $MaxRestartsPerHour relances por hora (anti-crashloop): atingiu,
#     para de relancar e registra CRITICAL ate a janela deslizar.
#
# Uso (de preferencia via Task Scheduler no logon ou start.ps1):
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\watchdog_ceo.ps1
# Log: runtime/logs/watchdog_ceo.log

param(
    [int]$Port = 8080,
    [int]$IntervalSec = 30,
    [int]$GraceCycles = 3,
    [int]$MaxRestartsPerHour = 4
)

$ErrorActionPreference = "Continue"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path (Join-Path $ScriptDir "..")).Path
$ServeScript = Join-Path $ScriptDir "serve_agent_llamacpp.ps1"
$LogDir = Join-Path $ProjectRoot "runtime\logs"
$LogFile = Join-Path $LogDir "watchdog_ceo.log"
$HealthUrl = "http://127.0.0.1:$Port/health"

if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }

function Write-WdLog {
    param([string]$Level, [string]$Message)
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') [$Level] $Message"
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
    Write-Host $line
}

Write-WdLog "INFO" "watchdog_ceo iniciado: port=$Port interval=${IntervalSec}s grace=$GraceCycles maxRestarts/h=$MaxRestartsPerHour"

$failCycles = 0
$restartTimestamps = @()  # timestamps de relance na ultima hora

while ($true) {
    $healthy = $false
    try {
        $resp = Invoke-WebRequest -Uri $HealthUrl -TimeoutSec 5 -UseBasicParsing
        if ($resp.StatusCode -eq 200) { $healthy = $true }
    } catch {
        $healthy = $false
    }

    $proc = Get-Process -Name "llama-server" -ErrorAction SilentlyContinue

    if ($healthy) {
        if ($failCycles -gt 0) {
            Write-WdLog "INFO" "CEO healthy novamente apos $failCycles ciclos de falha"
        }
        $failCycles = 0
        Start-Sleep -Seconds $IntervalSec
        continue
    }

    if ($proc) {
        $failCycles++
        if ($failCycles -eq 1) {
            Write-WdLog "WARN" "health falhou mas processo llama-server existe (PID $($proc.Id)) - assumindo carregamento; ciclo $failCycles/$GraceCycles"
        }
        Start-Sleep -Seconds $IntervalSec
        continue
    }

    $failCycles++
    Write-WdLog "WARN" "health falhou e sem processo llama-server - ciclo $failCycles/$GraceCycles"

    if ($failCycles -lt $GraceCycles) {
        Start-Sleep -Seconds $IntervalSec
        continue
    }

    # Janela anti-crashloop: conta relances na ultima hora.
    $now = Get-Date
    $restartTimestamps = @($restartTimestamps | Where-Object { ($now - $_).TotalMinutes -lt 60 })
    if ($restartTimestamps.Count -ge $MaxRestartsPerHour) {
        Write-WdLog "CRITICAL" "max $MaxRestartsPerHour relances/h atingido - NAO relancando. Investigacao manual necessaria."
        $failCycles = 0
        Start-Sleep -Seconds ($IntervalSec * 4)
        continue
    }

    Write-WdLog "INFO" "relancando CEO via $ServeScript (detached, hidden)"
    try {
        Start-Process -FilePath "powershell" -ArgumentList @(
            "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", $ServeScript, "-Port", $Port
        ) -WindowStyle Hidden -RedirectStandardOutput (Join-Path $LogDir "ceo-serve-watchdog.log") -RedirectStandardError (Join-Path $LogDir "ceo-serve-watchdog.err.log")
        $restartTimestamps += $now
        Write-WdLog "INFO" "relance disparado ($($restartTimestamps.Count)/$MaxRestartsPerHour na ultima hora)"
    } catch {
        Write-WdLog "ERROR" "falha ao relancar CEO: $($_.Exception.Message)"
    }
    $failCycles = 0
    Start-Sleep -Seconds ($IntervalSec * 2)
}
