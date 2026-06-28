"""F51 Nitro LoRA — QwenLong 30B via GGUF + llama.cpp.

Stable Windows training path:
1. HF model → GGUF (convert_hf_to_gguf.py)
2. GGUF → LoRA training (llama-finetune.exe)
3. Export LoRA (llama-export-lora.exe)

Requirements:
- llama.cpp built with finetune support
- huggingface-cli installed
- 64GB RAM recommended
"""
import os, subprocess, json, shutil
from pathlib import Path

# === Config ===
HF_REPO = "huihui-ai/Huihui-QwenLong-L1.5-30B-A3B-abliterated"
LLAMA_CPP = r"C:\llama.cpp"
MODELS_DIR = os.path.join(LLAMA_CPP, "models")
OUTPUT_DIR = "./models/bob_lora_qwenlong_30b_f51"
WORKSPACE = "./temp_gguf_workspace"

# === Finance Data (same as v2/v3/v4) ===
TRAIN_DATA = [
    {"instruction": "Analise a acao PETR4 para mim.", "response": "PETR4 (Petrobras PN): acao estatal brasileira de petroleo. Setor ciclico, sensivel ao barril e cambio. Dividendos historicamente altos. Riscos: politica, petroleo, regulacao."},
    {"instruction": "O que e um ETF?", "response": "ETF (Exchange Traded Fund): fundo de indice negociado em bolsa. Diversificacao com uma ordem. Exemplos: BOVA11, IVVB11, SPY, QQQ."},
    {"instruction": "Devo comprar VALE3?", "response": "VALE3 (Vale ON): maior mineradora de ferro. Ciclica, depende da China. Verifique preco, P/L e momento do ciclo."},
    {"instruction": "Explique P/L.", "response": "P/L (Preco/Lucro): razao entre preco e lucro por acao. <10: barata. 15-25: normal. >30: cara. Use com ROE e crescimento."},
    {"instruction": "Analise ITUB4.", "response": "ITUB4 (Itau Unibanco PN): maior banco privado BR. Sensivel a Selic. Boa governanca, dividendos consistentes, beta moderado."},
    {"instruction": "Melhor investimento iniciante?", "response": "1) Reserva emergencia Tesouro Selic. 2) ETFs diversificados. 3) Blue chips. 4) Nunca penny/cripto sem experiencia. 5) Estude fundamentos."},
    {"instruction": "F51 Trade Gate?", "response": "10 gates: Freeze, Intent, Blacklist, Format, Validation, Quantity, Price, Mismatch, IBKR Health, Journal Health. Duvida = BLOQUEIA."},
    {"instruction": "USIO comprar?", "response": "USIO: fintech pagamentos, small cap NASDAQ. Alta volatilidade. Verifique preco, volume, catalisadores. Use stop loss. So paper trading."},
]

def run(cmd, check=True):
    """Run command and print output."""
    print(f"\n> {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=__import__("sys").stderr)
    if check and result.returncode != 0:
        raise RuntimeError(f"Command failed: {cmd}")
    return result

def main():
    os.makedirs(WORKSPACE, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # === Step 1: Check if GGUF model exists ===
    gguf_model = os.path.join(MODELS_DIR, "qwenlong-30b-a3b-f16.gguf")
    gguf_model_q4 = os.path.join(MODELS_DIR, "qwenlong-30b-a3b-q4_k.gguf")

    if not os.path.exists(gguf_model) and not os.path.exists(gguf_model_q4):
        print("=== Step 1: Convert HF to GGUF ===")

        # Download from HF
        hf_dir = os.path.join(WORKSPACE, "hf_model")
        print(f"Downloading {HF_REPO} to {hf_dir}...")
        run(f"hf download {HF_REPO} --local-dir \"{hf_dir}\"")

        # Convert to GGUF
        print("Converting to GGUF (f16)...")
        convert_script = os.path.join(LLAMA_CPP, "convert_hf_to_gguf.py")
        run(f"python \"{convert_script}\" \"{hf_dir}\" --outfile \"{gguf_model}\" --outtype f16")

        # Optional: Quantize to Q4_K_M
        print("Quantizing to Q4_K_M (faster training)...")
        gguf_exe = os.path.join(LLAMA_CPP, "build", "bin", "llama-gguf.exe")
        run(f"\"{gguf_exe}\" quantize \"{gguf_model}\" \"{gguf_model_q4}\" Q4_K_M")
    else:
        print("=== Step 1: GGUF model exists, skipping ===")

    # === Step 2: Prepare training data ===
    print("\n=== Step 2: Prepare Training Data ===")

    train_jsonl = os.path.join(WORKSPACE, "train_finance.jsonl")
    with open(train_jsonl, "w", encoding="utf-8") as f:
        for ex in TRAIN_DATA:
            text = f"<|im_start|>user\n{ex['instruction']}<|im_end|>\n<|im_start|>assistant\n{ex['response']}<|im_end|>"
            f.write(json.dumps({"text": text}) + "\n")

    print(f"Created: {train_jsonl}")

    # === Step 3: Run LoRA Training ===
    print("\n=== Step 3: LoRA Training with llama-finetune ===")

    model_to_use = gguf_model_q4 if os.path.exists(gguf_model_q4) else gguf_model
    print(f"Using model: {model_to_use}")

    lora_output = os.path.join(OUTPUT_DIR, "lora_f51.gguf")
    finetune_exe = os.path.join(LLAMA_CPP, "build", "bin", "llama-finetune.exe")

    cmd = (
        f"\"{finetune_exe}\" "
        f"--model \"{model_to_use}\" "
        f"--lora-out \"{lora_output}\" "
        f"--train-data \"{train_jsonl}\" "
        f"--threads 16 "
        f"--rank 8 "
        f"--epoch 3 "
        f"--batch-size 1 "
        f"--learning-rate 0.0002 "
        f"--warmup 0 "
        f"--output-precision f16"
    )
    run(cmd)

    print("\n=== Training Complete! ===")
    print(f"LoRA saved to: {lora_output}")

    # === Step 4: Usage info ===
    print("\n=== Usage ===")
    print(f'llama-cli.exe -m "{model_to_use}" --lora "{lora_output}" --cpum -t 16')

if __name__ == "__main__":
    main()
