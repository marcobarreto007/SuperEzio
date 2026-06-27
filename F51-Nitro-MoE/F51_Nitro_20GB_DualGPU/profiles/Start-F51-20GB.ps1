param(
    [ValidateSet("auto", "safe5", "aggressive6", "experimental6_fullcache")]
    [string] $Profile = "auto",
    [string] $ModelFamily = "gpt-oss-120b",
    [int] $Port = 8080
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$bin = Join-Path $root "bin\llama-server.exe"
$binDir = Split-Path -Parent $bin

if ($ModelFamily -eq "mixtral-8x7b") {
    $modelDir = Join-Path $root "models\Mixtral-8x7B-Instruct-v0.1-GGUF"
    $modelFile = Get-ChildItem -Path $modelDir -Filter "*.gguf" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $modelFile) { throw "Missing Mixtral GGUF in $modelDir" }
    $model = $modelFile.FullName
} else {
    $model = Join-Path $root "models\gpt-oss-120b-mxfp4\gpt-oss-120b-mxfp4-00001-of-00003.gguf"
}
$logs = Join-Path $root "logs"
New-Item -ItemType Directory -Force -Path $logs | Out-Null

if (-not (Test-Path $bin)) {
    throw "Missing runtime: $bin"
}
if (-not (Test-Path $model)) {
    throw "Missing model shard: $model"
}

$gpuRows = @()
try {
    $raw = & nvidia-smi --query-gpu=index,name,memory.total,memory.free --format=csv,noheader,nounits
    foreach ($line in $raw) {
        $parts = $line -split ",\s*"
        if ($parts.Count -ge 4) {
            $gpuRows += [pscustomobject]@{
                Index = [int]$parts[0]
                Name = $parts[1]
                TotalMiB = [int]$parts[2]
                FreeMiB = [int]$parts[3]
            }
        }
    }
} catch {
    throw "nvidia-smi failed. Install/update NVIDIA driver before running this kit."
}

if ($gpuRows.Count -eq 0) {
    throw "No NVIDIA GPUs detected."
}

$totalVramMiB = ($gpuRows | Measure-Object -Property TotalMiB -Sum).Sum
$freeVramMiB = ($gpuRows | Measure-Object -Property FreeMiB -Sum).Sum

if ($ModelFamily -eq "mixtral-8x7b") {
    switch ($Profile) {
        default {
            $nCpuMoe = 10
            # cacheCap=0 enables F51 auto-detection (Mixtral 8x7B → 8 experts, cache all)
            $cacheCap = 0
            $fitTarget = 1024
        }
    }
} else {
    if ($Profile -eq "auto") {
        if ($totalVramMiB -ge 21500 -and $freeVramMiB -ge 19500) {
            $Profile = "aggressive6"
        } else {
            $Profile = "safe5"
        }
    }

    switch ($Profile) {
        "safe5" {
            $nCpuMoe = 31
            $cacheCap = 16
            $fitTarget = 1024
        }
        "aggressive6" {
            $nCpuMoe = 30
            $cacheCap = 14
            $fitTarget = 768
        }
        "experimental6_fullcache" {
            $nCpuMoe = 30
            $cacheCap = 16
            $fitTarget = 512
        }
    }
}

$logicalCores = [Environment]::ProcessorCount
$threads = [Math]::Max(8, [Math]::Min(16, $logicalCores - 2))

$env:F51_MOE_CACHE = "1"
$env:F51_MOE_SCHED_SKIP = "1"
$env:F51_MOE_CACHE_ENABLED = "1"
$env:F51_MOE_CACHE_CAPACITY = [string]$cacheCap
$env:GGML_OP_OFFLOAD_MIN_BATCH = "1"
$env:LLAMA_ARG_FIT_TARGET = [string]$fitTarget
$env:PATH = "$binDir;$env:PATH"

$serverArgs = @(
    "-m", $model,
    "--n-cpu-moe", [string]$nCpuMoe,
    "--no-mmap",
    "-ngl", "99",
    "-c", "4096",
    "-b", "2048",
    "-ub", "512",
    "-t", [string]$threads,
    "--host", "127.0.0.1",
    "--port", [string]$Port,
    "-fa", "on",
    "--swa-full",
    "-fit", "on",
    "-fitc", "4096"
)

if ($gpuRows.Count -gt 1) {
    $split = ($gpuRows | Sort-Object Index | ForEach-Object { [string]$_.TotalMiB }) -join ","
    $serverArgs += @("-sm", "layer", "-ts", $split)
} else {
    $serverArgs += @("-sm", "none")
}

$logPath = Join-Path $logs ("server_{0}_{1}.log" -f $Profile, (Get-Date -Format "yyyyMMdd_HHmmss"))

Write-Host "F51 Nitro 20GB launch"
Write-Host "Profile: $Profile"
Write-Host "Model Family: $ModelFamily"
Write-Host "GPU count: $($gpuRows.Count), total VRAM MiB: $totalVramMiB, free MiB: $freeVramMiB"
Write-Host "n_cpu_moe: $nCpuMoe, cache/layer: $cacheCap"
Write-Host "FIT target MiB: $fitTarget"
Write-Host "Threads: $threads"
Write-Host "Log: $logPath"
Write-Host ""
Write-Host "$bin $($serverArgs -join ' ')"
Write-Host ""

& $bin @serverArgs 2>&1 | Tee-Object -FilePath $logPath -Append
exit $LASTEXITCODE
