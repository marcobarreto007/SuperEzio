# SuperEzio — Qwen3.6-35B F51 local inference
# RTX 5060 Ti 16GB + 64GB RAM optimized
# Speculative decoding: disabled (awaiting Qwen3.6-family small model)

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
$DraftModel = "$ModelDir\qwen2.5-0.5b-draft-Q4_K_M.gguf"

# Speculative decoding DISABLED — Qwen2.5 draft has incompatible vocab
# Qwen3.6: BoS=248044, EoS=248046, ~248K tokens
# Qwen2.5: BoS=151643, EoS=151645, ~151K tokens
# Need same-family draft (Qwen3.6-0.6B or Qwen3-0.6B GGUF)
# When ready: set $UseDraft = $true
$UseDraft = $false

# Add CUDA DLLs to PATH
$env:PATH = "$BinDir;$env:PATH"

if (-not (Test-Path $MainModel)) {
    Write-Host "ERROR: Main model not found: $MainModel" -ForegroundColor Red
    exit 1
}
if ($UseDraft -and -not (Test-Path $DraftModel)) {
    Write-Host "WARNING: Draft model not found, disabling speculative decoding" -ForegroundColor Yellow
    $UseDraft = $false
}

Write-Host "============================================" -ForegroundColor Cyan
Write-Host " SuperEzio Qwen3.6-35B F51" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "Main model : $MainModel"
Write-Host "Draft model: $(if ($UseDraft) { $DraftModel } else { 'DISABLED' })"
Write-Host "GPU layers : $GpuLayers / 40 (~$([math]::Round($GpuLayers * 500 / 1024, 1)) GB)"
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
    "--repeat-penalty", 1.1
)

if ($UseDraft) {
    $llamaArgs += "-md"; $llamaArgs += $DraftModel
    $llamaArgs += "-ngld"; $llamaArgs += 99
}

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
