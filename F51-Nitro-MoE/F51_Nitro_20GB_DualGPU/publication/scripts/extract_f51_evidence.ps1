param(
    [string] $LogPath = "logs\f51_mxfp4.log",
    [string] $OutputPath = "publication\results\f51_mxfp4_current_evidence.json"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $LogPath)) {
    throw "Missing log: $LogPath"
}

$text = Get-Content -LiteralPath $LogPath -Raw

function FirstMatch {
    param([string] $Pattern, [int] $Group = 1)
    $m = [regex]::Match($text, $Pattern, [System.Text.RegularExpressions.RegexOptions]::Multiline)
    if ($m.Success) {
        return $m.Groups[$Group].Value
    }
    return $null
}

function DecimalOrNull {
    param($Value)
    if ($null -eq $Value -or $Value -eq "") { return $null }
    return [double]::Parse([string]$Value, [System.Globalization.CultureInfo]::InvariantCulture)
}

function IntOrNull {
    param($Value)
    if ($null -eq $Value -or $Value -eq "") { return $null }
    return [int64]$Value
}

$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
$system = Get-CimInstance Win32_ComputerSystem

$gpuRows = @()
try {
    $rawGpu = & nvidia-smi --query-gpu=name,memory.total,memory.free,pci.bus_id,driver_version --format=csv,noheader,nounits
    foreach ($line in $rawGpu) {
        $p = $line -split ",\s*"
        if ($p.Count -ge 5) {
            $gpuRows += [pscustomobject]@{
                name = $p[0]
                memory_total_mib = [int64]$p[1]
                memory_free_mib = [int64]$p[2]
                pci_bus_id = $p[3]
                driver_version = $p[4]
            }
        }
    }
} catch {
    $gpuRows = @()
}

$gateBytes = IntOrNull (FirstMatch "F51 DIAG.*?nb02=(\d+).*?ffn_gate_exps\.weight#0")
$upBytes = IntOrNull (FirstMatch "F51 DIAG.*?nb02=(\d+).*?ffn_up_exps\.weight#0")
$downBytes = IntOrNull (FirstMatch "F51 DIAG.*?nb02=(\d+).*?ffn_down_exps\.weight#0")
$expertBytes = $null
if ($gateBytes -and $upBytes -and $downBytes) {
    $expertBytes = $gateBytes + $upBytes + $downBytes
}

$nLayers = IntOrNull (FirstMatch "print_info:\s+n_layer\s+=\s+(\d+)")
$expertsPerLayer = IntOrNull (FirstMatch "print_info:\s+n_expert\s+=\s+(\d+)")

$hitRates = @()
foreach ($m in [regex]::Matches($text, "F51 DECODE:\s+token=(\d+)\s+hits=(\d+)\s+misses=(\d+)\s+rate=([0-9.]+)%")) {
    $hitRates += [pscustomobject]@{
        token = [int64]$m.Groups[1].Value
        hits = [int64]$m.Groups[2].Value
        misses = [int64]$m.Groups[3].Value
        rate_percent = [double]::Parse($m.Groups[4].Value, [System.Globalization.CultureInfo]::InvariantCulture)
    }
}

$kvBuffers = @()
foreach ($m in [regex]::Matches($text, "llama_kv_cache:\s+CUDA0 KV buffer size =\s+([0-9.]+)\s+MiB")) {
    $kvBuffers += [double]::Parse($m.Groups[1].Value, [System.Globalization.CultureInfo]::InvariantCulture)
}

$result = [ordered]@{
    generated_at = (Get-Date).ToString("o")
    source_log = (Resolve-Path $LogPath).Path
    hardware = [ordered]@{
        cpu_name = $cpu.Name
        cpu_cores = [int64]$cpu.NumberOfCores
        cpu_logical_processors = [int64]$cpu.NumberOfLogicalProcessors
        cpu_l2_cache_kib = [int64]$cpu.L2CacheSize
        cpu_l3_cache_kib = [int64]$cpu.L3CacheSize
        ram_bytes = [int64]$system.TotalPhysicalMemory
        ram_gib = [math]::Round($system.TotalPhysicalMemory / 1GB, 2)
        gpus = $gpuRows
    }
    model = [ordered]@{
        name = ((FirstMatch "general\.name str\s+=\s+(.+)$") -as [string]).Trim()
        file_size_gib = DecimalOrNull (FirstMatch "file size\s+=\s+([0-9.]+)\s+GiB")
        bpw = DecimalOrNull (FirstMatch "file size\s+=\s+[0-9.]+\s+GiB\s+\(([0-9.]+)\s+BPW\)")
        n_ctx_train = IntOrNull (FirstMatch "print_info:\s+n_ctx_train\s+=\s+(\d+)")
        n_embd = IntOrNull (FirstMatch "print_info:\s+n_embd\s+=\s+(\d+)")
        n_layer = $nLayers
        n_expert = $expertsPerLayer
        n_expert_used = IntOrNull (FirstMatch "print_info:\s+n_expert_used\s+=\s+(\d+)")
        expert_ffn_length = IntOrNull (FirstMatch "expert_feed_forward_length u32\s+=\s+(\d+)")
    }
    expert_accounting = [ordered]@{
        gate_bytes = $gateBytes
        up_bytes = $upBytes
        down_bytes = $downBytes
        expert_bytes = $expertBytes
        expert_mib = if ($expertBytes) { [math]::Round($expertBytes / 1MB, 2) } else { $null }
        full_layer_bytes = if ($expertBytes -and $expertsPerLayer) { $expertBytes * $expertsPerLayer } else { $null }
        full_layer_gib = if ($expertBytes -and $expertsPerLayer) { [math]::Round(($expertBytes * $expertsPerLayer) / 1GB, 3) } else { $null }
        all_expert_bytes = if ($expertBytes -and $expertsPerLayer -and $nLayers) { $expertBytes * $expertsPerLayer * $nLayers } else { $null }
        all_expert_gib = if ($expertBytes -and $expertsPerLayer -and $nLayers) { [math]::Round(($expertBytes * $expertsPerLayer * $nLayers) / 1GB, 2) } else { $null }
    }
    runtime_buffers = [ordered]@{
        cuda_model_buffer_mib = DecimalOrNull (FirstMatch "CUDA0 model buffer size =\s+([0-9.]+)\s+MiB")
        cuda_kv_buffers_mib = $kvBuffers
        cuda_compute_buffer_mib = DecimalOrNull (FirstMatch "CUDA0 compute buffer size =\s+([0-9.]+)\s+MiB")
    }
    timings = [ordered]@{
        prompt_tokens = IntOrNull (FirstMatch "prompt eval time =\s+[0-9.]+ ms /\s+(\d+) tokens")
        prompt_tokens_per_second = DecimalOrNull (FirstMatch "prompt eval time =.*\(\s+[0-9.]+ ms per token,\s+([0-9.]+) tokens per second\)")
        generation_tokens = IntOrNull (FirstMatch "^\s+eval time =\s+[0-9.]+ ms /\s+(\d+) tokens")
        generation_tokens_per_second = DecimalOrNull (FirstMatch "^\s+eval time =.*\(\s+[0-9.]+ ms per token,\s+([0-9.]+) tokens per second\)")
    }
    f51_decode_hit_rates = $hitRates
}

$outDir = Split-Path -Parent $OutputPath
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$result | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
Write-Host "Wrote $OutputPath"
