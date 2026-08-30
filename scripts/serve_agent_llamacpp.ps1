# SuperEzio operator mouth (ZERO-CLOUD).
# Sobe Ornith-1.0-9B-Q4_K_M na porta 8080. Um servidor por vez — a unica GPU
# real desta maquina (RTX 3060 12GB) nao aguenta duas instancias.
# Sources config.ps1 for portable path detection and keeps command-line overrides.

param(
    [int]$Port = 8080,
    [string]$TensorSplit = "12",
    [int]$ContextLength = 8192,
    [int]$Slots = 1,
    [string]$LlamaServerPath = $env:SUPEREZIO_LLAMA_SERVER_EXE
)

$ErrorActionPreference = "Stop"
$RequestedLlamaServerPath = $LlamaServerPath
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path (Join-Path $ScriptDir "..")).Path

$configPath = Join-Path $ProjectRoot "config.ps1"
if (Test-Path $configPath) {
    . $configPath
} else {
    Write-Host "ERROR: config.ps1 not found at $configPath" -ForegroundColor Red
    exit 1
}
# config.ps1 sets $ErrorActionPreference = "Continue" for its own path probing;
# re-assert fail-fast here or startup errors would be silently swallowed.
$ErrorActionPreference = "Stop"

if ($RequestedLlamaServerPath) {
    if (Test-Path $RequestedLlamaServerPath) {
        $LlamaServerPath = (Resolve-Path $RequestedLlamaServerPath).Path
    } else {
        Write-Host "ERROR: Requested llama-server.exe not found: $RequestedLlamaServerPath" -ForegroundColor Red
        exit 1
    }
}

if (-not (Test-Path $ModelPath)) {
    Write-Host "ERROR: Model not found: $ModelPath" -ForegroundColor Red
    exit 1
}

if ($LoraPath -and -not (Test-Path $LoraPath)) {
    Write-Host "WARNING: LoRA not found: $LoraPath - starting without LoRA" -ForegroundColor Yellow
    $LoraPath = $null
}

# Operator mouth is text-only. Do not attach the old 27B mmproj — it steals
# VRAM and is the wrong projector for Ornith.
$MmprojPath = $null

if (-not $LlamaServerPath) {
    Write-Host "ERROR: llama-server.exe not found." -ForegroundColor Red
    exit 1
}

$BinDir = Split-Path -Parent $LlamaServerPath
$pathEntries = @($BinDir)
$requestedCudaBin = $env:SUPEREZIO_CUDA_BIN
if (-not $requestedCudaBin -and $env:CUDA_PATH) {
    $requestedCudaBin = Join-Path $env:CUDA_PATH "bin"
}
if ($requestedCudaBin) {
    if (-not (Test-Path -LiteralPath $requestedCudaBin)) {
        Write-Host "ERROR: Configured CUDA bin directory not found: $requestedCudaBin" -ForegroundColor Red
        exit 1
    }
    $pathEntries += (Resolve-Path -LiteralPath $requestedCudaBin).Path
}
$pathEntries += $env:PATH
$env:PATH = $pathEntries -join ";"

$version = ""
$oldEAP = $ErrorActionPreference
try {
    $ErrorActionPreference = "Continue"
    $version = (& $LlamaServerPath --version 2>&1 | ForEach-Object { "$_" } | Select-Object -First 5) -join " | "
} catch {
    $version = "version probe failed"
} finally {
    $ErrorActionPreference = $oldEAP
}

$hasCuda = ($version -match "cuda") -or ($LlamaServerPath -match "cuda|build-cuda|Release|tools\\llama.cpp")

Write-Host "============================================" -ForegroundColor Cyan
Write-Host " SuperEzio CEO Server (ZERO-CLOUD)" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "Model      : $(Split-Path -Leaf $ModelPath)"
Write-Host "LoRA       : $(if ($LoraPath) { $LoraPath } else { 'NONE' })"
Write-Host "Vision     : $(if ($MmprojPath) { $MmprojPath } else { 'OFF (mmproj missing)' })"
Write-Host "Server     : $LlamaServerPath"
Write-Host "Version    : $version"
Write-Host "CUDA       : $(if ($hasCuda) { 'YES' } else { 'NO (CPU-only)' })"
Write-Host "Port       : $Port"
Write-Host "Context    : $($ContextLength.ToString('N0')) tokens"
Write-Host "Slots      : $Slots parallel"
Write-Host "TensorSplit: $TensorSplit (-sm layer)"
Write-Host "Flash Attn : on"
Write-Host "Cache type : q8_0"
Write-Host "API        : http://127.0.0.1:$Port/v1"
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

if (-not $hasCuda) {
    Write-Host "WARNING: Non-CUDA llama-server. Model will run on CPU only." -ForegroundColor Yellow
}

Write-Host "Starting llama-server..." -ForegroundColor Green

# Perfil operador 2026-08-29: Ornith-1.0-9B Q4_K_M na RTX 3060 12GB,
# cache q8_0, contexto 8192, sem visao. MTP desligado.
$args = @(
    "-m", $ModelPath,
    "-ngl", "all",
    "-sm", "layer",
    "-ts", $TensorSplit,
    "-c", $ContextLength,
    "--port", $Port,
    "-np", $Slots,
    "-fa", "on",
    "--cache-type-k", "q8_0",
    "--cache-type-v", "q8_0",
    "--reasoning", "off",
    "--jinja"
)

if ($LoraPath) {
    $args += @("--lora", $LoraPath)
}

if ($MmprojPath) {
    $args += @("--mmproj", $MmprojPath)
}

& $LlamaServerPath @args
