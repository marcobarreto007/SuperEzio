$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot

Write-Host "=== F51 target check ==="
Write-Host "Root: $root"
Write-Host ""

Write-Host "=== GPU ==="
try {
    & nvidia-smi --query-gpu=index,name,pci.bus_id,memory.total,memory.free,driver_version --format=csv,noheader,nounits
} catch {
    Write-Host "nvidia-smi failed. Install/update NVIDIA driver."
}

Write-Host ""
Write-Host "=== Runtime files ==="
Get-ChildItem (Join-Path $root "bin") -ErrorAction SilentlyContinue | Select-Object Name,Length,LastWriteTime | Format-Table -AutoSize

Write-Host ""
Write-Host "=== CUDA DLLs expected in bin ==="
$cudaDlls = "cudart64_12.dll", "cublas64_12.dll", "cublasLt64_12.dll", "nvJitLink_120_0.dll", "nvrtc64_120_0.dll", "nvrtc-builtins64_128.dll"
foreach ($dll in $cudaDlls) {
    $path = Join-Path $root ("bin\" + $dll)
    if (Test-Path $path) {
        $item = Get-Item $path
        Write-Host ("OK      {0} ({1:N0} bytes)" -f $dll, $item.Length)
    } else {
        Write-Host ("MISSING {0}" -f $dll)
    }
}

Write-Host ""
Write-Host "=== Model files ==="
Get-ChildItem (Join-Path $root "models") -Filter "*.gguf" -Recurse -ErrorAction SilentlyContinue | Select-Object Name,Length,LastWriteTime | Format-Table -AutoSize

Write-Host ""
Write-Host "=== Expected launch profiles ==="
Write-Host "safe5:       --n-cpu-moe 31, F51_MOE_CACHE_CAPACITY=16"
Write-Host "aggressive6: --n-cpu-moe 30, F51_MOE_CACHE_CAPACITY=14"
Write-Host "experimental6_fullcache: --n-cpu-moe 30, F51_MOE_CACHE_CAPACITY=16"
