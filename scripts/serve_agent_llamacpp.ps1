# SuperEzio Bob CEO local server.
# Canonical runtime prefers the patched F51 llama.cpp build in C:\llama.cpp.
# The repo-local llama.cpp\bin binary is only a fallback and is reported loudly.

param(
    [int]$Port = 8082,
    [int]$GpuLayers = 999,
    [int]$ContextLength = 131072,
    [int]$Slots = 2,
    [int]$NCpuMoe = 31,
    [int]$CacheRamMiB = 8192,
    [int]$F51CacheCapacity = 16,
    [string]$LlamaServerPath = $env:SUPEREZIO_LLAMA_SERVER_EXE
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path "$ScriptDir\.."
$Model = Join-Path $ProjectRoot "models\Huihui-Qwen3-Next-80B-A3B-Instruct-abliterated.IQ4_XS.gguf"

$candidateServers = @()
if ($LlamaServerPath) {
    $candidateServers += $LlamaServerPath
}
$candidateServers += "C:\llama.cpp\build-cuda\bin\llama-server.exe"
$candidateServers += (Join-Path $ProjectRoot "llama.cpp\bin\llama-server.exe")

$Server = $null
foreach ($candidate in $candidateServers) {
    if ($candidate -and (Test-Path $candidate)) {
        $Server = (Resolve-Path $candidate).Path
        break
    }
}

if (-not (Test-Path $Model)) {
    Write-Host "ERROR: Model not found: $Model" -ForegroundColor Red
    exit 1
}

if (-not $Server) {
    Write-Host "ERROR: llama-server.exe not found. Set SUPEREZIO_LLAMA_SERVER_EXE or restore C:\llama.cpp\build-cuda\bin." -ForegroundColor Red
    exit 1
}

$BinDir = Split-Path -Parent $Server
$env:PATH = "$BinDir;$env:PATH"

# F51 runtime knobs. These are harmless on non-F51 binaries and active on the patched build.
$env:F51_MOE_CACHE = "1"
$env:F51_MOE_CACHE_ENABLED = "1"
$env:F51_MOE_SCHED_SKIP = "1"
$env:F51_MOE_CACHE_CAPACITY = [string]$F51CacheCapacity

$gpuMoeLayers = 48 - $NCpuMoe
$expertLayerMB = 816
$gpuExpertMB = $gpuMoeLayers * $expertLayerMB
$denseMB = 1300
$kvMB = 400
$totalGpuMB = $denseMB + $kvMB + $gpuExpertMB

$version = ""
$oldErrorActionPreference = $ErrorActionPreference
try {
    $ErrorActionPreference = "Continue"
    $version = (& $Server --version 2>&1 | ForEach-Object { "$_" } | Select-Object -First 5) -join " | "
}
catch {
    $version = "version probe failed: $($_.Exception.Message)"
}
finally {
    $ErrorActionPreference = $oldErrorActionPreference
}

$usingPatchedF51 = $Server -like "C:\llama.cpp\build-cuda\bin\llama-server.exe"

Write-Host "============================================" -ForegroundColor Cyan
Write-Host " SuperEzio Bob CEO Server" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "Model      : Qwen3-Next-80B-A3B Abliterated IQ4_XS"
Write-Host "Server     : $Server"
Write-Host "Version    : $version"
Write-Host "F51 build  : $usingPatchedF51"
Write-Host "Port       : $Port"
Write-Host "Context    : $ContextLength tokens"
Write-Host "Slots      : $Slots parallel"
Write-Host "Flash Attn : on"
Write-Host "Cache type : q8_0"
Write-Host "Cache RAM  : $CacheRamMiB MiB"
Write-Host "Reasoning  : disabled"
Write-Host ""
Write-Host "MoE split  : $gpuMoeLayers layers GPU + $NCpuMoe layers CPU"
Write-Host "GPU budget : ~$totalGpuMB MB ($denseMB dense + $kvMB KV + $gpuExpertMB experts)"
Write-Host "RAM budget : ~$($NCpuMoe * $expertLayerMB) MB ($NCpuMoe expert layers)"
Write-Host "F51 cache  : enabled capacity=$F51CacheCapacity"
Write-Host "API        : http://127.0.0.1:$Port/v1"
Write-Host "============================================"
Write-Host ""

if (-not $usingPatchedF51) {
    Write-Host "WARNING: running fallback llama-server, not C:\llama.cpp\build-cuda\bin\llama-server.exe" -ForegroundColor Yellow
}

Write-Host "Starting llama-server..." -ForegroundColor Green

& $Server `
    -m $Model `
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
