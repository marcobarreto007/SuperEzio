# SuperEzio Bob CEO local server.
# Sources config.ps1 for path detection and keeps command-line overrides.
# Official agent GGUF: Huihui-Qwen3-Next-80B-A3B-Instruct-abliterated.IQ4_XS.gguf
# Preferred llama-server: C:\llama.cpp\build-cuda\bin\llama-server.exe

param(
    [int]$Port = 8082,
    [int]$GpuLayers = 14,
    [int]$ContextLength = 131072,
    [int]$Slots = 2,
    [int]$NCpuMoe = 31,
    [int]$CacheRamMiB = 8192,
    [int]$F51CacheCapacity = 16,
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
    Write-Host "Download the model to $ModelsDir and try again." -ForegroundColor Yellow
    exit 1
}

if (-not $LlamaServerPath) {
    Write-Host "ERROR: llama-server.exe not found." -ForegroundColor Red
    Write-Host ""
    Write-Host "Options to fix:" -ForegroundColor Yellow
    Write-Host "  1. Set env var: `$env:SUPEREZIO_LLAMA_SERVER_EXE = 'C:\path\to\llama-server.exe'"
    Write-Host "  2. Add llama.cpp\build-cuda\bin to your PATH"
    Write-Host "  3. Put llama-server.exe under a local llama.cpp\bin folder"
    Write-Host ""
    exit 1
}

$BinDir = Split-Path -Parent $LlamaServerPath
$env:PATH = "$BinDir;$env:PATH"

# F51 Nitro MoE runtime knobs.
$env:F51_MOE_CACHE = "1"
$env:F51_MOE_CACHE_ENABLED = "1"
$env:F51_MOE_SCHED_SKIP = "1"
$env:F51_MOE_CACHE_CAPACITY = [string]$F51CacheCapacity

$actualGpuLayers = [Math]::Min($GpuLayers, 48 - $NCpuMoe)
$expertLayerMB = 816
$gpuExpertMB = $actualGpuLayers * $expertLayerMB
$denseMB = 1300
$kvMB = 400
$totalGpuMB = $denseMB + $kvMB + $gpuExpertMB

$version = ""
$oldEAP = $ErrorActionPreference
try {
    $ErrorActionPreference = "Continue"
    $version = (& $LlamaServerPath --version 2>&1 | ForEach-Object { "$_" } | Select-Object -First 5) -join " | "
} catch {
    $version = "version probe failed: $($_.Exception.Message)"
} finally {
    $ErrorActionPreference = $oldEAP
}

$hasCuda = ($version -match "cuda") -or ($LlamaServerPath -match "cuda|build-cuda")
$hasF51 = $version -match "f51|nitro"

Write-Host "============================================" -ForegroundColor Cyan
Write-Host " SuperEzio Bob CEO Server" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "Model      : Qwen3-Next-80B-A3B Abliterated IQ4_XS"
Write-Host "Server     : $LlamaServerPath"
Write-Host "Version    : $version"
Write-Host "CUDA       : $(if ($hasCuda) { 'YES' } else { 'NO (CPU-only, will be slow)' })"
Write-Host "F51 marker : $(if ($hasF51) { 'reported by binary' } else { 'not reported by binary' })"
Write-Host "Port       : $Port"
Write-Host "Context    : $($ContextLength.ToString('N0')) tokens"
Write-Host "Slots      : $Slots parallel"
Write-Host "Flash Attn : on"
Write-Host "Cache type : q8_0"
Write-Host "Cache RAM  : $CacheRamMiB MiB"
Write-Host "Reasoning  : disabled"
Write-Host ""
Write-Host "MoE split  : $actualGpuLayers layers GPU + $NCpuMoe layers CPU (ngl=$GpuLayers)"
Write-Host "GPU budget : ~$totalGpuMB MB ($denseMB dense + $kvMB KV + $gpuExpertMB experts)"
Write-Host "RAM budget : ~$((48 - $actualGpuLayers) * $expertLayerMB) MB ($(48 - $actualGpuLayers) expert layers)"
Write-Host "F51 cache  : enabled capacity=$F51CacheCapacity"
Write-Host "API        : http://127.0.0.1:$Port/v1"
Write-Host "============================================"
Write-Host ""

if (-not $hasCuda) {
    Write-Host "WARNING: Non-CUDA llama-server. Model will run on CPU only. Expect slower responses." -ForegroundColor Yellow
}
if (-not $hasF51) {
    Write-Host "NOTE: Binary did not report F51/Nitro markers. Runtime knobs are enabled; confirm acceleration from logs." -ForegroundColor Yellow
}

Write-Host "Starting llama-server..." -ForegroundColor Green

& $LlamaServerPath `
    -m $ModelPath `
    -ngl $GpuLayers `
    -c $ContextLength `
    --port $Port `
    -np $Slots `
    -fa on `
    -ctk q8_0 `
    -ctv q8_0 `
    --n-cpu-moe $NCpuMoe `
    -cram $CacheRamMiB `
    --reasoning off `
    --mlock
