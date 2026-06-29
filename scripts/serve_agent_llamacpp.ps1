# SuperEzio Bob CEO local server.
# CEO: QwenLong 30B A3B Q4_K + LoRA F51 Nitro v7 (49/49 layers GPU, 17.3 GB)
# Sources config.ps1 for path detection and keeps command-line overrides.
# llama-server: C:\llama.cpp\build\bin\llama-server.exe

param(
    [int]$Port = 8082,
    [int]$GpuLayers = 99,
    [int]$ContextLength = 65536,
    [int]$Slots = 2,
    [int]$CacheRamMiB = 4096,
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
    Write-Host "Run: python scripts/train_qwenlong_30b_gguf_f51_v7.py" -ForegroundColor Yellow
    exit 1
}

if ($LoraPath -and -not (Test-Path $LoraPath)) {
    Write-Host "WARNING: LoRA not found: $LoraPath — starting without LoRA" -ForegroundColor Yellow
    $LoraPath = $null
}

if (-not $LlamaServerPath) {
    Write-Host "ERROR: llama-server.exe not found." -ForegroundColor Red
    exit 1
}

$BinDir = Split-Path -Parent $LlamaServerPath
$env:PATH = "$BinDir;$env:PATH"

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

$hasCuda = ($version -match "cuda") -or ($LlamaServerPath -match "cuda|build-cuda")

Write-Host "============================================" -ForegroundColor Cyan
Write-Host " SuperEzio Bob CEO Server" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "Model      : QwenLong 30B A3B Q4_K"
Write-Host "LoRA       : $(if ($LoraPath) { $LoraPath } else { 'NONE' })"
Write-Host "Server     : $LlamaServerPath"
Write-Host "Version    : $version"
Write-Host "CUDA       : $(if ($hasCuda) { 'YES (all layers GPU)' } else { 'NO (CPU-only)' })"
Write-Host "Port       : $Port"
Write-Host "Context    : $($ContextLength.ToString('N0')) tokens"
Write-Host "Slots      : $Slots parallel"
Write-Host "Flash Attn : on"
Write-Host "Cache type : q8_0"
Write-Host "Cache RAM  : $CacheRamMiB MiB"
Write-Host "API        : http://127.0.0.1:$Port/v1"
Write-Host "============================================"
Write-Host ""

if (-not $hasCuda) {
    Write-Host "WARNING: Non-CUDA llama-server. Model will run on CPU only." -ForegroundColor Yellow
}

Write-Host "Starting llama-server..." -ForegroundColor Green

$args = @(
    "-m", $ModelPath,
    "-ngl", $GpuLayers,
    "-c", $ContextLength,
    "--port", $Port,
    "-np", $Slots,
    "-fa", "on",
    "-ctk", "q8_0",
    "-ctv", "q8_0",
    "-cram", $CacheRamMiB,
    "--mlock"
)

if ($LoraPath) {
    $args += @("--lora", $LoraPath)
}

& $LlamaServerPath @args
