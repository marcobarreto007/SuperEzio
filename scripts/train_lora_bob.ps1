# F51 LoRA Training — Direct on Bob's 80B GGUF Model
# Uses llama.cpp finetune + F51 Nitro streaming
# Marco's Hardware: RTX 5060 Ti 16GB + 68GB RAM + i7-12700K

Continue = "Stop"
 = Split-Path -Parent System.Management.Automation.InvocationInfo.MyCommand.Path
 = (Resolve-Path (Join-Path  "..")).Path

# === CONFIG ===
 = "/models/Huihui-Qwen3-Next-80B-A3B-Instruct-abliterated.IQ4_XS.gguf"
 = "/data/lora_training_data.txt"
 = "/models/bob_lora_finance_pt.gguf"
 = "C:\llama.cpp\build\bin\llama-finetune.exe"

# F51 Nitro env vars
1 = "1"
 = "26"
 = "1"
 = "1"

Write-Host "=== F51 LoRA TRAINING — BOB 80B ==="
Write-Host "Model: "
Write-Host "Output: "
Write-Host ""

# Check prerequisites
if (-not (Test-Path )) { Write-Error "llama-finetune not found at "; exit 1 }
if (-not (Test-Path )) { Write-Error "Bob model not found at "; exit 1 }
if (-not (Test-Path )) { Write-Error "Training data not found at "; exit 1 }

Write-Host "Starting training..."
Write-Host "Params: epochs=3, lr=1e-5, batch=4, ctx=1024, rank=8"
Write-Host "VRAM: ~6GB (only 3B active params + LoRA)"
Write-Host ""

&  
    -m  
    -f  
    --lora-out  
    --epochs 3 
    --learning-rate 1e-5 
    --batch-size 4 
    --ctx-size 1024 
    -ngl 14 
    --threads 16 
    --val-split 0.1

if ( -eq 0) {
    Write-Host ""
    Write-Host "=== TRAINING COMPLETE ==="
    Write-Host "LoRA saved to: "
     = (Get-Item ).Length / 1MB
    Write-Host "Size: 0 MB"
} else {
    Write-Host "Training failed with exit code: "
}
