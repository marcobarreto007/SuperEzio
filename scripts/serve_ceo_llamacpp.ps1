# SuperEzio — CEO Local Server (Qwen3.6-35B CEO+Intent Merged via llama-server)
# Serves OpenAI-compatible API on port 8082 for FastAPI pipeline integration
# RTX 5060 Ti 16GB + 64GB RAM optimized
# Model: superezio-ceo-intent-merged.Q4_K_M.gguf (CEO LoRA ckpt-2600 + Intent LoRA best)
# MTP speculative decoding disabled (nextn_predict_layers=0 patch)

param(
    [int]$Port = 8082,
    [int]$GpuLayers = 28,
    [int]$ContextLength = 8192,
    [int]$Slots = 2
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path "$ScriptDir\.."
$BinDir = "$ProjectRoot\llama.cpp\bin"
$ModelDir = "$ProjectRoot\models"

$Model = "$ModelDir\superezio-ceo-intent-merged.Q4_K_M.gguf"

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
Write-Host "GPU layers : $GpuLayers / 40"
Write-Host "Context    : $ContextLength tokens"
Write-Host "Slots      : $Slots parallel"
Write-Host "Speculative: disabled (patched)"
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
    -fa on `
    -ctk q8_0 `
    -ctv q8_0 `
    --mlock
