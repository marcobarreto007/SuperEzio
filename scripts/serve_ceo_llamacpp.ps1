# SuperEzio — CEO Local Server (Qwen3.6-35B F51 via llama-server)
# Serves OpenAI-compatible API on port 8082 for FastAPI pipeline integration
# RTX 5060 Ti 16GB + 64GB RAM optimized
# NEXTN/MTP built-in speculative decoding

param(
    [int]$Port = 8082,
    [int]$GpuLayers = 20,
    [int]$ContextLength = 16384,
    [int]$Slots = 4
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path "$ScriptDir\.."
$BinDir = "$ProjectRoot\llama.cpp\bin"
$ModelDir = "$ProjectRoot\models"

$Model = "$ModelDir\qwen36-35b-f51.Q4_K_M.gguf"

# Add CUDA DLLs to PATH
$env:PATH = "$BinDir;$env:PATH"

if (-not (Test-Path $Model)) {
    Write-Host "ERROR: Model not found: $Model" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path "$BinDir\llama-server.exe")) {
    Write-Host "ERROR: llama-server.exe not found in: $BinDir" -ForegroundColor Red
    exit 1
}

Write-Host "============================================" -ForegroundColor Cyan
Write-Host " SuperEzio CEO Server (Qwen3.6-35B F51)"    -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "Model      : $Model"
Write-Host "Port       : $Port"
Write-Host "GPU layers : $GpuLayers / 41"
Write-Host "Context    : $ContextLength tokens"
Write-Host "Slots      : $Slots parallel"
Write-Host "Speculative: MTP (built-in)"
Write-Host "API        : http://127.0.0.1:$Port/v1"
Write-Host "============================================"
Write-Host ""
Write-Host "Starting llama-server..." -ForegroundColor Green

& "$BinDir\llama-server.exe" `
    -m $Model `
    -ngl $GpuLayers `
    -c $ContextLength `
    --port $Port `
    -np $Slots `
    --spec-type draft-mtp `
    -fa on `
    -ctk q8_0 `
    -ctv q8_0 `
    --mlock
