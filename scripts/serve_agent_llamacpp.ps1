# SuperEzio CEO Local Server (Qwen3-Next-80B-A3B Abliterated IQ4_XS GGUF via llama-server)
# Serves OpenAI-compatible API on port 8082 for FastAPI pipeline integration.
# RTX 5060 Ti 16GB + 64GB RAM optimized with F51 Nitro MoE tiering.
# MoE: 512 experts, 10 active + 1 shared per token, ~59 MB per expert.
# Nitro Layers 1-4 active: Persistence Cache, Async PCIe Streams, Router Lookahead, KV Cache Tiering.
# Reasoning is disabled so short API calls return message.content reliably.
# VRAM budget: ~6.3 GB @ 256K context (shared layers only, experts on CPU via --cpu-moe).

param(
    [int]$Port = 8082,
    [int]$GpuLayers = 999,
    [int]$ContextLength = 262144,
    [int]$Slots = 2
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

Write-Host "============================================" -ForegroundColor Cyan
Write-Host " SuperEzio CEO Server (Qwen3-Next-80B Nitro)" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "Model      : Qwen3-Next-80B-A3B Abliterated IQ4_XS"
Write-Host "Arch       : MoE (512 experts, 10 active/token)"
Write-Host "Port       : $Port"
Write-Host "GPU layers : $GpuLayers (max offload, experts on CPU)"
Write-Host "CPU MoE    : enabled (--cpu-moe)"
Write-Host "Context    : $ContextLength tokens (256K)"
Write-Host "Slots      : $Slots parallel"
Write-Host "Flash Attn : on"
Write-Host "Cache type : q8_0"
Write-Host "Speculative: disabled"
Write-Host "Reasoning  : disabled"
Write-Host "Nitro L1   : Expert Persistence Cache (8 slots)"
Write-Host "Nitro L2   : Async Multi-Stream PCIe"
Write-Host "Nitro L3   : Router Lookahead Prefetch"
Write-Host "Nitro L4   : KV Cache Tiering (Hot/Warm)"
Write-Host "VRAM budget: ~6.3 GB (shared layers + KV)"
Write-Host "RAM budget : ~39 GB (expert pool)"
Write-Host "API        : http://127.0.0.1:$Port/v1"
Write-Host "============================================"
Write-Host ""
Write-Host "Starting llama-server with F51 Nitro optimizations..." -ForegroundColor Green

& "$BinDir\llama-server.exe" `
    -m $Model `
    -ngl $GpuLayers `
    -c $ContextLength `
    --port $Port `
    -np $Slots `
    -fa on `
    -ctk q8_0 `
    -ctv q8_0 `
    --cpu-moe `
    --reasoning off `
    --mlock