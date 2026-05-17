# SuperEzio — Qwen3.6-35B F51 local inference
# RTX 5060 Ti 16GB + 64GB RAM optimized
# NEXTN/MTP built-in speculative decoding (1.7-2x speedup)

param(
    [string]$Prompt = "",
    [int]$ContextLength = 8192,
    [int]$GpuLayers = 20,
    [float]$Temp = 0.7
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path "$ScriptDir\.."
$BinDir = "$ProjectRoot\llama.cpp\bin"
$ModelDir = "$ProjectRoot\models"

$MainModel = "$ModelDir\qwen36-35b-f51.Q4_K_M.gguf"

# Add CUDA DLLs to PATH
$env:PATH = "$BinDir;$env:PATH"

if (-not (Test-Path $MainModel)) {
    Write-Host "ERROR: Main model not found: $MainModel" -ForegroundColor Red
    exit 1
}

Write-Host "============================================" -ForegroundColor Cyan
Write-Host " SuperEzio Qwen3.6-35B F51 + NEXTN/MTP" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "Main model : $MainModel"
Write-Host "Speculative: MTP (built-in, block 40)"
Write-Host "GPU layers : $GpuLayers / 41 (~$([math]::Round($GpuLayers * 500 / 1024, 1)) GB)"
Write-Host "Context    : $ContextLength tokens"
Write-Host "Temp       : $Temp"
Write-Host "============================================"

$llamaArgs = @(
    "-m", $MainModel,
    "-ngl", $GpuLayers,
    "-c", $ContextLength,
    "--mlock",
    "-fa", "on",
    "-ctk", "q8_0",
    "-ctv", "q8_0",
    "--temp", $Temp,
    "--top-p", 0.95,
    "--top-k", 20,
    "--repeat-penalty", 1.1,
    "--spec-type", "draft-mtp"
)

if ($Prompt) {
    $llamaArgs += "-p"
    $llamaArgs += $Prompt
} else {
    $llamaArgs += "--interactive"
    $llamaArgs += "--interactive-first"
    $llamaArgs += "--chat-template", "qwen"
}

Write-Host "Starting llama-cli..." -ForegroundColor Green
Write-Host ""

&amp; "$BinDir\llama-cli.exe" @llamaArgs
