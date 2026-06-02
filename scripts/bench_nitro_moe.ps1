# F51 Nitro-MoE Benchmark - 3 tests, zero downloads
param(
    [int]$ContextLength = 4096,
    [int]$MaxTokens = 64
)

$model = "C:\Users\marco\F51\models\Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive-Q4_K_P.gguf"
$llama = "C:\Users\marco\F51\tools\llama.cpp\llama-server.exe"
$outDir = "C:\F51_LAB"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$results = "$outDir\bench_nitro_moe_$timestamp.txt"
$now = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'

$prompt = '{"model":"test","messages":[{"role":"user","content":"Diz apenas: OK F51 Nitro MoE funcional."}],"max_tokens":' + $MaxTokens + ',"temperature":0}'

$tests = @(
    @{Name="Teste1_CPU_ONLY"; Port="8091"; Args="-ngl 0 -c $ContextLength --port 8091"; Desc="CPU-only (-ngl 0)"},
    @{Name="Teste2_GPU_MOE_RAM"; Port="8092"; Args="-ngl 999 --cpu-moe -c $ContextLength -fa on --port 8092"; Desc="GPU attn + Experts RAM (--cpu-moe)"},
    @{Name="Teste3_GPU_ALL"; Port="8093"; Args="-ngl 99 -c $ContextLength -fa on --port 8093"; Desc="GPU tudo (-ngl 99)"}
)

"# F51 Nitro-MoE Benchmark - $now" | Out-File $results
"# Model: Qwen3.6-35B-A3B MoE (256 experts, 8 active, 21.82 GB Q4_K_P)" | Out-File $results -Append
"# Context: $ContextLength | MaxTokens: $MaxTokens" | Out-File $results -Append
"" | Out-File $results -Append

foreach ($test in $tests) {
    $name = $test.Name
    $port = $test.Port
    $desc = $test.Desc

    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  $name -- $desc" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan

    "## $name -- $desc" | Out-File $results -Append
    "" | Out-File $results -Append

    Get-Process -Name "llama-server" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2

    $logFile = "$outDir\$name.log"
    $proc = Start-Process -FilePath $llama -ArgumentList "-m `"$model`" $($test.Args)" -NoNewWindow -RedirectStandardError $logFile -PassThru

    Write-Host "  Aguardando servidor na porta $port ..." -ForegroundColor Yellow

    $ready = $false
    for ($i = 0; $i -lt 120; $i++) {
        Start-Sleep -Seconds 1
        try {
            $r = Invoke-WebRequest -Uri "http://127.0.0.1:$port/health" -TimeoutSec 2 -ErrorAction SilentlyContinue
            if ($r.StatusCode -eq 200) {
                $ready = $true
                Write-Host "  Servidor pronto em ${i}s" -ForegroundColor Green
                break
            }
        } catch {}
        if ($proc.HasExited) {
            Write-Host "  ERRO: Servidor morreu (exit $($proc.ExitCode))" -ForegroundColor Red
            break
        }
    }

    if (-not $ready) {
        Write-Host "  FALHA: timeout" -ForegroundColor Red
        "STATUS: FAIL (timeout)" | Out-File $results -Append
        $proc | Stop-Process -Force -ErrorAction SilentlyContinue
        continue
    }

    $health = Invoke-RestMethod -Uri "http://127.0.0.1:$port/health" -TimeoutSec 5
    $hstat = "STATUS: OK | slots_idle=$($health.slots_idle) | slots_processing=$($health.slots_processing)"
    Write-Host "  $hstat"
    $hstat | Out-File $results -Append

    $vram = & nvidia-smi --query-gpu=index,name,memory.used,memory.total --format=csv,noheader 2>$null
    if ($vram) {
        "  --- VRAM snapshot ---" | Out-File $results -Append
        foreach ($line in $vram) { "  $line" | Out-File $results -Append }
    }

    Write-Host "  Enviando prompt ..." -ForegroundColor Yellow
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        $response = Invoke-RestMethod -Uri "http://127.0.0.1:$port/v1/chat/completions" -Method Post -Body $prompt -ContentType "application/json" -TimeoutSec 120
        $sw.Stop()
        $answer = $response.choices[0].message.content
        Write-Host "  Resposta: $answer" -ForegroundColor White
        $lat = [math]::Round($sw.Elapsed.TotalSeconds, 2)
        Write-Host "  Latencia HTTP: ${lat}s" -ForegroundColor Green
        "LATENCIA_HTTP_S: $lat" | Out-File $results -Append
        "RESPOSTA: $answer" | Out-File $results -Append
    } catch {
        $sw.Stop()
        Write-Host "  ERRO no chat: $_" -ForegroundColor Red
        "CHAT_ERROR: $_" | Out-File $results -Append
    }

    Start-Sleep -Seconds 3

    $logContent = Get-Content $logFile -ErrorAction SilentlyContinue
    "  --- Server log (tokens/s) ---" | Out-File $results -Append
    $tokensLines = $logContent | Select-String "tokens per second|prompt eval time|eval time|t/s|total time"
    foreach ($line in $tokensLines) {
        $t = $line.Line.Trim()
        Write-Host "  $t" -ForegroundColor DarkGray
        "  $t" | Out-File $results -Append
    }

    $tail = $logContent | Select-Object -Last 3
    "  --- Tail ---" | Out-File $results -Append
    foreach ($line in $tail) { "  $line" | Out-File $results -Append }

    $proc | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
    "" | Out-File $results -Append
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  Benchmark concluido!" -ForegroundColor Green
Write-Host "  Resultados: $results" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green

Write-Host ""
Write-Host "--- RESUMO ---" -ForegroundColor Yellow
Get-Content $results | Select-String "STATUS|LATENCIA|tokens per second|eval time|RESPOSTA|CHAT_ERROR" | ForEach-Object { Write-Host $_ }
