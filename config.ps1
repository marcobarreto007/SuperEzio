# SuperEzio - centralized local runtime configuration.

$ErrorActionPreference = "Continue"
$script:SuperEzioRoot = $PSScriptRoot
$script:ScriptsDir = Join-Path $SuperEzioRoot "scripts"
$script:SrcDir = Join-Path $SuperEzioRoot "src"
$script:RuntimeDir = Join-Path $SuperEzioRoot "runtime"
$script:LogsDir = Join-Path $RuntimeDir "logs"
$script:FrontendDir = Join-Path $SuperEzioRoot "frontend"
$script:DocsDir = Join-Path $SuperEzioRoot "docs"
$script:EnvFile = Join-Path $SuperEzioRoot ".env"
$script:EnvExampleFile = Join-Path $SuperEzioRoot ".env.example"

# Cloud model providers are configured by config/runtime.yml and environment.
$script:ApiPort = if ($env:SUPEREZIO_PORT) { [int]$env:SUPEREZIO_PORT } else { 8002 }
if ($ApiPort -lt 1 -or $ApiPort -gt 65535) { throw "SUPEREZIO_PORT must be between 1 and 65535" }

function Resolve-SuperEzioPythonExecutable {
    param([Parameter(Mandatory = $true)][string]$Command, [string[]]$Arguments = @())
    try {
        $probe = & $Command @Arguments -c "import sys; print(sys.executable); raise SystemExit(0 if sys.version_info >= (3, 11) else 42)" 2>&1
        if ($LASTEXITCODE -ne 0) { return $null }
        $exe = ($probe | Select-Object -First 1).ToString().Trim()
        if ($exe -and (Test-Path -LiteralPath $exe)) { return (Resolve-Path -LiteralPath $exe).Path }
    } catch {}
    return $null
}

function Get-SuperEzioPython {
    $candidates = @(
        @{ Command = (Join-Path $SuperEzioRoot ".venv\Scripts\python.exe"); Arguments = @() },
        @{ Command = "python"; Arguments = @() },
        @{ Command = "py"; Arguments = @("-3.11") },
        @{ Command = "py"; Arguments = @("-3") }
    )
    foreach ($candidate in $candidates) {
        $exe = Resolve-SuperEzioPythonExecutable -Command $candidate.Command -Arguments $candidate.Arguments
        if ($exe) { return $exe }
    }
    return $null
}

$script:PythonExe = Get-SuperEzioPython
if ($env:PYTHONPATH) {
    if (($env:PYTHONPATH -split ';') -notcontains $SrcDir) { $env:PYTHONPATH = "$SrcDir;$env:PYTHONPATH" }
} else {
    $env:PYTHONPATH = $SrcDir
}

function Get-SuperEzioPortOwner {
    param([Parameter(Mandatory = $true)][int]$Port)
    $connection = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $connection) { return $null }
    $process = Get-Process -Id $connection.OwningProcess -ErrorAction SilentlyContinue
    return [pscustomobject]@{
        Port = $Port
        Pid = $connection.OwningProcess
        ProcessName = if ($process) { $process.ProcessName } else { "unknown" }
    }
}

function Test-SuperEzioPort {
    param([Parameter(Mandatory = $true)][int]$Port)
    return ((Get-SuperEzioPortOwner -Port $Port) -ne $null)
}

function Test-SuperEzioHealth {
    param([Parameter(Mandatory = $true)][int]$Port, [int]$TimeoutSec = 8)
    try {
        $response = Invoke-WebRequest "http://127.0.0.1:$Port/health" -UseBasicParsing -TimeoutSec $TimeoutSec
        return ($response.StatusCode -eq 200)
    } catch { return $false }
}

function Initialize-SuperEzioDirs {
    foreach ($directory in @($RuntimeDir, $LogsDir)) {
        if (-not (Test-Path -LiteralPath $directory)) {
            New-Item -ItemType Directory -Force -Path $directory | Out-Null
        }
    }
}

function Write-SuperEzioConfig {
    Write-Host "Root        : $SuperEzioRoot"
    Write-Host "Python      : $(if ($PythonExe) { $PythonExe } else { 'NOT FOUND' })"
    Write-Host "AI providers: configured external APIs"
    Write-Host "API port    : $ApiPort"
}
