# F51 Nitro LoRA — Bob Core local via GGUF + llama.cpp
# Stable Windows training path: HF → GGUF → Finetune → Export LoRA

$ErrorActionPreference = "Stop"

# === Config ===
$HF_REPO = "huihui-ai/Huihui-QwenLong-L1.5-Bob Core-abliterated"
$LLAMA_CPP = "C:\llama.cpp"
$MODELS_DIR = "$LLAMA_CPP\models"
$OUTPUT_DIR = "./models/bob_lora_bob_core_f51"
$WORKSPACE = "./temp_gguf_workspace"

# === Finance Data (same as v2/v3/v4) ===
$TRAIN_DATA = @()
$TRAIN_DATA += @{
    instruction = "Analise a acao PETR4 para mim."
    response = "PETR4 (Petrobras PN): acao estatal brasileira de petroleo. Setor ciclico, sensivel ao barril e cambio. Dividendos historicamente altos. Riscos: politica, petroleo, regulacao."
}
$TRAIN_DATA += @{
    instruction = "O que e um ETF?"
    response = "ETF (Exchange Traded Fund): fundo de indice negociado em bolsa. Diversificacao com uma ordem. Exemplos: BOVA11, IVVB11, SPY, QQQ."
}
$TRAIN_DATA += @{
    instruction = "Devo comprar VALE3?"
    response = "VALE3 (Vale ON): maior mineradora de ferro. Ciclica, depende da China. Verifique preco, P/L e momento do ciclo."
}
$TRAIN_DATA += @{
    instruction = "Explique P/L."
    response = "P/L (Preco/Lucro): razao entre preco e lucro por acao. <10: barata. 15-25: normal. >30: cara. Use com ROE e crescimento."
}
$TRAIN_DATA += @{
    instruction = "Analise ITUB4."
    response = "ITUB4 (Itau Unibanco PN): maior banco privado BR. Sensivel a Selic. Boa governanca, dividendos consistentes, beta moderado."
}
$TRAIN_DATA += @{
    instruction = "Melhor investimento iniciante?"
    response = "1) Reserva emergencia Tesouro Selic. 2) ETFs diversificados. 3) Blue chips. 4) Nunca penny/cripto sem experiencia. 5) Estude fundamentos."
}
$TRAIN_DATA += @{
    instruction = "F51 Trade Gate?"
    response = "10 gates: Freeze, Intent, Blacklist, Format, Validation, Quantity, Price, Mismatch, IBKR Health, Journal Health. Duvida = BLOQUEIA."
}
$TRAIN_DATA += @{
    instruction = "USIO comprar?"
    response = "USIO: fintech pagamentos, small cap NASDAQ. Alta volatilidade. Verifique preco, volume, catalisadores. Use stop loss. So paper trading."
}

# === Step 1: Check if GGUF model exists ===
$GGUF_MODEL = "$MODELS_DIR\bob-core-local.gguf"
$GGUF_MODEL_Q4 = "$MODELS_DIR\bob-core-local.gguf"

if (-not (Test-Path $GGUF_MODEL) -and -not (Test-Path $GGUF_MODEL_Q4)) {
    Write-Host "=== Step 1: Convert HF to GGUF ===" -ForegroundColor Cyan

    # Download from HF using huggingface-cli
    Write-Host "Downloading $HF_REPO ..."
    huggingface-cli download $HF_REPO --local-dir "$WORKSPACE\hf_model" --local-dir-use-symlinks False

    # Convert to GGUF
    Write-Host "Converting to GGUF (f16 for base, can quantize later)..."
    python "$LLAMA_CPP\convert_hf_to_gguf.py" "$WORKSPACE\hf_model" "$GGUF_MODEL" --outtype f16

    # Optional: Create Q4_K_M quantized version for faster training
    Write-Host "Quantizing to Q4_K_M (optional, faster training)..."
    & "$LLAMA_CPP\build\bin\llama-gguf.exe" quantize "$GGUF_MODEL" "$GGUF_MODEL_Q4" Q4_K_M
}

# === Step 2: Prepare training data ===
Write-Host "=== Step 2: Prepare Training Data ===" -ForegroundColor Cyan

# Create JSONL training file (llama-finetune format)
$TRAIN_JSONL = "$WORKSPACE\train_finance.jsonl"
$TRAIN_DATA | ForEach-Object {
    $text = "<|im_start|>user$($_.instruction)<|im_end|>`n<|im_start|>assistant$($_.response)<|im_end|>"
    @{ text = $text } | ConvertTo-Json -Compress
} | Out-File -FilePath $TRAIN_JSONL -Encoding utf8

Write-Host "Created: $TRAIN_JSONL"

# === Step 3: Run LoRA Training ===
Write-Host "=== Step 3: LoRA Training with llama-finetune ===" -ForegroundColor Cyan

# Select model (prefer Q4 for speed)
$MODEL_TO_USE = if (Test-Path $GGUF_MODEL_Q4) { $GGUF_MODEL_Q4 } else { $GGUF_MODEL }

Write-Host "Using model: $MODEL_TO_USE"

# llama-finetune parameters
# --lora-out: output LoRA file
# --train-data: training JSONL
# --vocab-only: use existing vocab (faster)
# --threads: CPU threads
# --rank: LoRA rank
# --epoch: training epochs

& "$LLAMA_CPP\build\bin\llama-finetune.exe" `
    --model "$MODEL_TO_USE" `
    --lora-out "$OUTPUT_DIR\lora_f51.gguf" `
    --train-data "$TRAIN_JSONL" `
    --threads 16 `
    --rank 8 `
    --epoch 3 `
    --batch-size 1 `
    --learning-rate 0.0002 `
    --warmup 0 `
    --output-precision f16

if ($LASTEXITCODE -eq 0) {
    Write-Host "=== Training Complete! ===" -ForegroundColor Green
    Write-Host "LoRA saved to: $OUTPUT_DIR\lora_f51.gguf"

    # === Step 4: Export standalone LoRA ===
    Write-Host "=== Step 4: Export LoRA (optional) ===" -ForegroundColor Cyan
    # llama-export-lora can create a standalone adapter file
    & "$LLAMA_CPP\build\bin\llama-export-lora.exe" `
        --base-model "$MODEL_TO_USE" `
        --lora-input "$OUTPUT_DIR\lora_f51.gguf" `
        --lora-output "$OUTPUT_DIR\lora_f51_export.gguf"

    Write-Host "`n=== Usage ===" -ForegroundColor Yellow
    Write-Host "llama-cli.exe -m $MODEL_TO_USE --lora $OUTPUT_DIR\lora_f51.gguf --cpum -t 16"
} else {
    Write-Host "Training failed with exit code: $LASTEXITCODE" -ForegroundColor Red
}
