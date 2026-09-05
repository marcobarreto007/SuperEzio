# SuperEzio operator mouth (ZERO-CLOUD).
# Sobe Ornith-1.0-9B-Q4_K_M na porta 8080. Um servidor por vez.
# Hardware vivo medido em 2026-09-04: 1x RTX 2070 8GB. A RTX 3060 12GB
# existe no PnP mas esta em CM_PROB_FAILED_ADD e NAO entra no nvidia-smi.
# Nao use -ts 8,6 / -ts 12,8: isso assume duas GPUs e derruba camadas na CPU.
# Sources config.ps1 for portable path detection and keeps command-line overrides.

param(
    [int]$Port = 8080,
    [string]$TensorSplit = "auto",
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

function Get-SuperEzioLiveGpus {
    $gpus = @()
    try {
        $raw = & nvidia-smi --query-gpu=index,name,memory.total --format=csv,noheader,nounits 2>$null
        if ($LASTEXITCODE -ne 0) { return @($gpus) }
        foreach ($line in @($raw)) {
            if (-not $line) { continue }
            $parts = @(($line -split ",") | ForEach-Object { $_.Trim() })
            if ($parts.Count -lt 3) { continue }
            $idx = 0
            $vram = 0
            if (-not [int]::TryParse($parts[0], [ref]$idx)) { continue }
            [void][int]::TryParse(($parts[2] -replace "[^\d]", ""), [ref]$vram)
            $gpus += [pscustomobject]@{
                Index   = $idx
                Name    = $parts[1]
                VramMib = $vram
            }
        }
    } catch {}
    return @($gpus)
}

function Get-SuperEzioDisplayProblems {
    try {
        return @(Get-PnpDevice -Class Display -ErrorAction SilentlyContinue | Where-Object {
            $_.FriendlyName -match "NVIDIA|GeForce|RTX"
        } | ForEach-Object {
            [pscustomobject]@{
                Name    = $_.FriendlyName
                Status  = [string]$_.Status
                Problem = [string]$_.Problem
            }
        })
    } catch { return @() }
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

$cudaDll = Test-Path -LiteralPath (Join-Path $BinDir "ggml-cuda.dll")
$hasCuda = ($version -match "cuda") -or $cudaDll

$liveGpus = Get-SuperEzioLiveGpus
$displayCards = Get-SuperEzioDisplayProblems
$deadCards = @($displayCards | Where-Object { $_.Status -ne "OK" })
$resolvedTs = $null
$tsNote = "omitted (single live GPU)"
if ($TensorSplit -and ($TensorSplit -ne "auto")) {
    $wanted = @($TensorSplit -split ",").Count
    if ($liveGpus.Count -gt 0 -and $wanted -gt $liveGpus.Count) {
        Write-Host "WARNING: -ts $TensorSplit expects $wanted GPUs; nvidia-smi sees $($liveGpus.Count). Dropping -ts so layers stay on the live card." -ForegroundColor Yellow
        $tsNote = "dropped ($TensorSplit needed $wanted GPUs, live=$($liveGpus.Count))"
    } else {
        $resolvedTs = $TensorSplit
        $tsNote = $resolvedTs
    }
} elseif ($liveGpus.Count -ge 2) {
    $resolvedTs = ($liveGpus | ForEach-Object { [Math]::Max(1, [int][Math]::Round($_.VramMib / 1024.0)) }) -join ","
    $tsNote = "$resolvedTs (auto from live VRAM)"
}

Write-Host "============================================" -ForegroundColor Cyan
Write-Host " SuperEzio CEO Server (ZERO-CLOUD)" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "Model      : $(Split-Path -Leaf $ModelPath)"
Write-Host "LoRA       : $(if ($LoraPath) { $LoraPath } else { 'NONE' })"
Write-Host "Vision     : $(if ($MmprojPath) { $MmprojPath } else { 'OFF (mmproj missing)' })"
Write-Host "Server     : $LlamaServerPath"
Write-Host "Version    : $version"
Write-Host "CUDA       : $(if ($hasCuda) { 'YES' } else { 'NO (CPU-only)' })"
if ($liveGpus.Count -eq 0) {
    Write-Host "GPUs live  : NONE (nvidia-smi empty)"
} else {
    $gpuLine = ($liveGpus | ForEach-Object { "$($_.Index):$($_.Name) $($_.VramMib)MiB" }) -join " | "
    Write-Host "GPUs live  : $gpuLine"
}
foreach ($card in $deadCards) {
    Write-Host "GPU dead   : $($card.Name) Status=$($card.Status) Problem=$($card.Problem)" -ForegroundColor Yellow
}
Write-Host "Port       : $Port"
Write-Host "Context    : $($ContextLength.ToString('N0')) tokens"
Write-Host "Slots      : $Slots parallel"
# This llama.cpp build refuses quantized V cache without flash attn:
# "quantized V cache requires flash_attn to be enabled". Keep -fa on.
# First prompt eval on a cold WDDM 2070 can take ~60s (kernel warmup).
$flashAttn = "on"

Write-Host "TensorSplit: $tsNote"
Write-Host "Flash Attn : $flashAttn (required for q8_0 V cache)"
Write-Host "Cache type : q8_0"
Write-Host "API        : http://127.0.0.1:$Port/v1"
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

if (-not $hasCuda) {
    Write-Host "WARNING: Non-CUDA llama-server. Model will run on CPU only." -ForegroundColor Yellow
}
if ($liveGpus.Count -eq 0) {
    Write-Host "WARNING: No live NVIDIA GPU. Offload will fail closed onto CPU." -ForegroundColor Yellow
}
if ($deadCards.Count -gt 0) {
    Write-Host "WARNING: Dead NVIDIA display device(s). Dual-GPU split is NO-GO until Device Manager is repaired." -ForegroundColor Yellow
}

Write-Host "Starting llama-server..." -ForegroundColor Green

# Perfil operador 2026-09-04: Ornith-1.0-9B Q4_K_M na RTX 2070 8GB viva,
# cache q8_0, contexto 8192, sem visao. MTP desligado. Sem -ts fantasma.
$llamaArgs = @(
    "-m", $ModelPath,
    "-ngl", "all",
    "-sm", "layer",
    "-c", $ContextLength,
    "--host", "127.0.0.1",
    "--port", $Port,
    "-np", $Slots,
    "-fa", $flashAttn,
    "--cache-type-k", "q8_0",
    "--cache-type-v", "q8_0",
    "--reasoning", "off",
    "--jinja"
)

if ($resolvedTs) {
    $llamaArgs += @("-ts", $resolvedTs)
}

if ($LoraPath) {
    $llamaArgs += @("--lora", $LoraPath)
}

if ($MmprojPath) {
    $llamaArgs += @("--mmproj", $MmprojPath)
}

& $LlamaServerPath @llamaArgs
