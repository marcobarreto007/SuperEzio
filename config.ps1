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

# Official zero-cloud runtime: shared local llama-server on 8080 and API on 8002.
$script:CeoPort = if ($env:SUPEREZIO_MODEL_PORT) { [int]$env:SUPEREZIO_MODEL_PORT } else { 8080 }
$script:ApiPort = if ($env:SUPEREZIO_PORT) { [int]$env:SUPEREZIO_PORT } else { 8002 }
$script:ModelsDir = Join-Path $SuperEzioRoot "models"
# Operator mouth (live GPU 2026-09-04: RTX 2070 8GB). Ornith-1.0-9B Q4_K_M (~5.6GB).
# RTX 3060 12GB is physically present but CM_PROB_FAILED_ADD — not in nvidia-smi.
# System organs decide; this GGUF only routes tools and narrates the cockpit.
$modelFileName = "Ornith-1.0-9B-Q4_K_M.gguf"
$modelCandidates = @(
    $env:SUPEREZIO_MODEL_PATH,
    (Join-Path $ModelsDir $modelFileName)
)
if ($env:USERPROFILE) {
    $modelCandidates += Join-Path $env:USERPROFILE "models\ornith-1.0-9b\$modelFileName"
}
$script:ModelPath = $modelCandidates | Where-Object {
    $_ -and (Test-Path -LiteralPath $_)
} | Select-Object -First 1
if (-not $ModelPath) {
    # Keep the failure message actionable even before the model is installed.
    $script:ModelPath = Join-Path $ModelsDir $modelFileName
}
$script:LoraPath = $null

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

function Get-SuperEzioLlamaServer {
    $candidates = @(
        $env:SUPEREZIO_LLAMA_SERVER_EXE,
        (Join-Path $SuperEzioRoot "llama.cpp\bin\llama-server.exe")
    )
    if ($env:USERPROFILE) {
        $candidates += Join-Path $env:USERPROFILE "tools\llama.cpp\llama-server.exe"
    }
    try {
        $inPath = Get-Command llama-server.exe -ErrorAction SilentlyContinue
        if ($inPath) { $candidates += $inPath.Source }
    } catch {}
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }
    return $null
}

$script:PythonExe = Get-SuperEzioPython
$script:LlamaServerPath = Get-SuperEzioLlamaServer
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
    Write-Host "llama-server: $(if ($LlamaServerPath) { $LlamaServerPath } else { 'NOT FOUND' })"
    Write-Host "Model       : $ModelPath"
    Write-Host "Ports       : CEO=$CeoPort, API=$ApiPort"
}
