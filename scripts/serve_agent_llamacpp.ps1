# SuperEzio CEO Local Server (Qwen3-Next-80B-A3B Abliterated IQ4_XS GGUF via llama-server)
# Serves OpenAI-compatible API on port 8082 for FastAPI pipeline integration.
# RTX 5060 Ti 16GB + 64GB RAM.
# MoE: 512 experts, 10 active + 1 shared per token, ~544 KB per expert tensor (IQ4_XS).
# Strategy: --n-cpu-moe 31 = 17 MoE layers on GPU (~13.9 GB) + 31 layers on CPU/RAM.
# GPU: attention + dense + 17 expert layers = ~15.2 GB VRAM (nearly full).
# RAM: ~26 GB (31 layers of experts, IQ4_XS quantized).
# Measured: 31.9 tok/s decode (2x CPU-only) at ctx=4096.
# F51 Nitro cache (dança das cadeiras) not needed for Qwen 80B IQ4_XS — experts too small.
# Reasoning is disabled so short API calls return message.content reliably.

param(
    [int]$Port = 8082,
    [int]$GpuLayers = 999,
    [int]$ContextLength = 131072,
    [int]$Slots = 2,
    [int]$NCpuMoe = 31
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path "$ScriptDir\.."
$BinDir = "$ProjectRoot\llama.cpp\bin"
$ModelDir = "$ProjectRoot\models"

$Model = "$ModelDir\Huihui-Qwen3-Next-80B-A3B-Instruct-abliterated.IQ4_XS.gguf"

$env:PATH = "$BinDir;$env:PATH"

if (-not (Test-Path $Model)) {
    Write-Host "ERROR: Model not found: $Model" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path "$BinDir\llama-server.exe")) {
    Write-Host "ERROR: llama-server.exe not found in: $BinDir" -ForegroundColor Red
    exit 1
}

$gpuMoeLayers = 48 - $NCpuMoe
$expertLayerMB = 816
$gpuExpertMB = $gpuMoeLayers * $expertLayerMB
$denseMB = 1300
$kvMB = 400
$totalGpuMB = $denseMB + $kvMB + $gpuExpertMB

Write-Host "============================================" -ForegroundColor Cyan
Write-Host " SuperEzio CEO Server (Qwen3-Next-80B Nitro)" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "Model      : Qwen3-Next-80B-A3B Abliterated IQ4_XS"
Write-Host "Arch       : MoE (512 experts, 10 active/token)"
Write-Host "Port       : $Port"
Write-Host "Context    : $ContextLength tokens"
Write-Host "Slots      : $Slots parallel"
Write-Host "Flash Attn : on"
Write-Host "Cache type : q8_0"
Write-Host "Reasoning  : disabled"
Write-Host ""
Write-Host "MoE split  : $gpuMoeLayers layers GPU + $NCpuMoe layers CPU"
Write-Host "GPU budget : ~$totalGpuMB MB ($denseMB dense + $kvMB KV + $gpuExpertMB experts)"
Write-Host "RAM budget : ~$($NCpuMoe * $expertLayerMB) MB ($NCpuMoe expert layers)"
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
    --n-cpu-moe $NCpuMoe `
    --reasoning off `
    --mlock