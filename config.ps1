# SuperEzio - centralized runtime configuration.
# Source this file from the root scripts to get consistent paths, Python
# detection, llama-server detection, environment variables, and health helpers.

$ErrorActionPreference = "Continue"

# Root directory where this config lives.
$script:SuperEzioRoot = $PSScriptRoot

# Paths.
$script:ScriptsDir = Join-Path $SuperEzioRoot "scripts"
$script:ModelsDir = Join-Path $SuperEzioRoot "models"
$script:SrcDir = Join-Path $SuperEzioRoot "src"
$script:RuntimeDir = Join-Path $SuperEzioRoot "runtime"
$script:LogsDir = Join-Path $SuperEzioRoot "runtime\logs"
$script:FrontendDir = Join-Path $SuperEzioRoot "frontend"
$script:DocsDir = Join-Path $SuperEzioRoot "docs"
$script:EnvFile = Join-Path $SuperEzioRoot ".env"
$script:EnvExampleFile = Join-Path $SuperEzioRoot ".env.example"

# Model.
$script:ModelName = "Huihui-Qwen3-Next-80B-A3B-Instruct-abliterated.IQ4_XS.gguf"
$script:ModelPath = Join-Path $ModelsDir $ModelName

# Ports.
$script:CeoPort = 8082
$script:ApiPort = 8002

function Resolve-SuperEzioPythonExecutable {
    param(
        [Parameter(Mandatory = $true)][string]$Command,
        [string[]]$Arguments = @()
    )

    try {
        $probe = & $Command @Arguments -c "import sys; print(sys.executable); raise SystemExit(0 if sys.version_info >= (3, 11) else 42)" 2>&1
        if ($LASTEXITCODE -ne 0) {
            return $null
        }

        $exe = ($probe | Select-Object -First 1).ToString().Trim()
        if ($exe -and (Test-Path $exe)) {
            return (Resolve-Path $exe).Path
        }
    } catch {}

    return $null
}

function Get-SuperEzioPython {
    <#
    .SYNOPSIS
    Returns the best available Python executable for SuperEzio.
    Priority: .venv\Scripts\python.exe -> python -> python3 -> py launchers.
    #>
    $candidates = @(
        @{ Command = (Join-Path $SuperEzioRoot ".venv\Scripts\python.exe"); Arguments = @() },
        @{ Command = "python"; Arguments = @() },
        @{ Command = "python3"; Arguments = @() },
        @{ Command = "py"; Arguments = @("-3.12") },
        @{ Command = "py"; Arguments = @("-3.11") },
        @{ Command = "py"; Arguments = @("-3") }
    )

    foreach ($candidate in $candidates) {
        $exe = Resolve-SuperEzioPythonExecutable -Command $candidate.Command -Arguments $candidate.Arguments
        if ($exe) {
            return $exe
        }
    }

    return $null
}

$script:PythonExe = Get-SuperEzioPython

function Get-SuperEzioLlamaServer {
    <#
    .SYNOPSIS
    Returns the path to llama-server.exe.
    Priority: SUPEREZIO_LLAMA_SERVER_EXE env -> PATH -> common locations.
    #>
    $envPath = $env:SUPEREZIO_LLAMA_SERVER_EXE
    if ($envPath -and (Test-Path $envPath)) {
        return (Resolve-Path $envPath).Path
    }

    try {
        $inPath = Get-Command llama-server.exe -ErrorAction SilentlyContinue
        if ($inPath) {
            return $inPath.Source
        }
    } catch {}

    $commonLocations = @(
        "C:\llama.cpp\build-cuda\bin\llama-server.exe",
        "C:\llama.cpp\build\bin\llama-server.exe",
        (Join-Path $SuperEzioRoot "llama.cpp\bin\llama-server.exe")
    )

    if ($env:LOCALAPPDATA) {
        $commonLocations += (Join-Path $env:LOCALAPPDATA "llama.cpp\llama-server.exe")
    }
    if ($env:ProgramFiles) {
        $commonLocations += (Join-Path $env:ProgramFiles "llama.cpp\bin\llama-server.exe")
    }

    foreach ($loc in $commonLocations) {
        if ($loc -and (Test-Path $loc)) {
            return (Resolve-Path $loc).Path
        }
    }

    return $null
}

$script:LlamaServerPath = Get-SuperEzioLlamaServer

# Runtime environment variables.
$env:PYTHONPATH = $SrcDir
$env:SUPEREZIO_BOB_SOVEREIGN = "1"
$env:SUPEREZIO_PROFESSIONAL_COLLECTOR = "true"

function Get-SuperEzioPortOwner {
    param([Parameter(Mandatory = $true)][int]$Port)

    $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $conn) {
        return $null
    }

    $proc = Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue
    return [pscustomobject]@{
        Port = $Port
        Pid = $conn.OwningProcess
        ProcessName = if ($proc) { $proc.ProcessName } else { "unknown" }
    }
}

function Test-SuperEzioPort {
    param([int]$Port)
    return ((Get-SuperEzioPortOwner -Port $Port) -ne $null)
}

function Test-SuperEzioHealth {
    param([int]$Port, [int]$TimeoutSec = 8)
    try {
        $r = Invoke-WebRequest "http://127.0.0.1:$Port/health" -UseBasicParsing -TimeoutSec $TimeoutSec
        return ($r.StatusCode -eq 200)
    } catch {
        return $false
    }
}

function Initialize-SuperEzioDirs {
    foreach ($d in @($RuntimeDir, $LogsDir)) {
        if (-not (Test-Path $d)) {
            New-Item -ItemType Directory -Force -Path $d | Out-Null
        }
    }
}

function Write-SuperEzioConfig {
    Write-Host "=== SuperEzio Configuration ===" -ForegroundColor Cyan
    Write-Host "Root        : $SuperEzioRoot"
    if ($PythonExe) {
        Write-Host "Python      : $PythonExe" -ForegroundColor Green
    } else {
        Write-Host "Python      : NOT FOUND (install Python 3.12 or 3.11)" -ForegroundColor Red
    }
    if ($LlamaServerPath) {
        Write-Host "llama-server: $LlamaServerPath" -ForegroundColor Green
    } else {
        Write-Host "llama-server: NOT FOUND (set `$env:SUPEREZIO_LLAMA_SERVER_EXE or install llama.cpp)" -ForegroundColor Red
    }
    if (Test-Path $ModelPath) {
        Write-Host "Model       : $ModelPath" -ForegroundColor Green
    } else {
        Write-Host "Model       : NOT FOUND (download to $ModelsDir)" -ForegroundColor Red
    }
    Write-Host "Ports       : CEO=$CeoPort, API=$ApiPort"
    Write-Host "================================`n"
}
