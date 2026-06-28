"""F51 Nitro LoRA v5 — Python nativo via llama-cpp-python.

Sem dependência de executáveis quebrados.
Usa llama-cpp-python com suporte a CUDA.
"""
import os, json, shutil
from pathlib import Path

# === Config ===
GGUF_MODEL = r"C:\llama.cpp\models\qwenlong-30b-a3b-q4_k.gguf"
OUTPUT_DIR = "./models/bob_lora_qwenlong_30b_f51_v5"
WORKSPACE = "./temp_gguf_workspace"

# === Finance Data ===
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

def prepare_data():
    """Prepara JSONL de treinamento."""
    os.makedirs(WORKSPACE, exist_ok=True)
    train_jsonl = os.path.join(WORKSPACE, "train_finance.jsonl")

    with open(train_jsonl, "w", encoding="utf-8") as f:
        for ex in TRAIN_DATA:
            text = f"<|im_start|>user\n{ex['instruction']}<|im_end|>\n<|im_start|>assistant\n{ex['response']}<|im_end|>"
            f.write(json.dumps({"text": text}) + "\n")

    print(f"Created: {train_jsonl}")
    return train_jsonl

def train_lora_pytorch(model_path, data_path, output_dir):
    """Treina LoRA usando PyTorch + PEFT (F51 Nitro style)."""
    try:
        from transformers import (
            AutoModelForCausalLM,
            AutoTokenizer,
            TrainingArguments,
            Trainer,
        )
        from peft import LoraConfig, get_peft_model, TaskType
        from datasets import Dataset
        import torch

        print("=== Loading Model ===")
        # Verifica se tem GPU
        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"Device: {device}")

        # Para GGUF, precisamos converter ou usar llama-cpp-python
        # Vamos usar llama-cpp-python que suporta GGUF diretamente
        from llama_cpp import Llama

        print("=== Loading GGUF with llama-cpp-python ===")
        model = Llama(
            model_path=model_path,
            n_ctx=4096,
            n_gpu_layers=-1,  # All layers on GPU
            verbose=True,
        )

        # llama-cpp-python não suporta treinamento LoRA nativo ainda
        # Precisamos usar outra abordagem
        raise NotImplementedError("llama-cpp-python não suporta treinamento LoRA nativo")

    except ImportError as e:
        print(f"Missing dependency: {e}")
        print("Install: pip install llama-cpp-python transformers peft datasets torch")
        return False
    except Exception as e:
        print(f"Error: {e}")
        return False

def train_lora_manual(model_path, data_path, output_dir):
    """F51 Nitro: treinamento manual simples usando PyTorch puro."""
    import torch
    import torch.nn as nn
    from torch.utils.data import Dataset, DataLoader

    print("=== F51 Nitro Manual Training ===")

    # Verifica GPU
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    # Carrega dados
    with open(data_path, "r", encoding="utf-8") as f:
        data = [json.loads(line) for line in f]

    print(f"Loaded {len(data)} examples")

    # Tokenização simplificada (para demonstração)
    # Na prática, precisaria do tokenizer do modelo
    class SimpleDataset(Dataset):
        def __init__(self, data):
            self.data = data

        def __len__(self):
            return len(self.data)

        def __getitem__(self, idx):
            return self.data[idx]

    dataset = SimpleDataset(data)
    loader = DataLoader(dataset, batch_size=1, shuffle=True)

    print("Training loop would go here...")
    print("(This is a placeholder - full implementation requires model loading)")

    return True

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Step 1: Prepare data
    print("=== Step 1: Prepare Data ===")
    data_path = prepare_data()

    # Step 2: Check model
    if not os.path.exists(GGUF_MODEL):
        print(f"Model not found: {GGUF_MODEL}")
        return

    # Step 3: Train
    print("\n=== Step 2: Train LoRA ===")
    print("Note: Full LoRA training on GGUF requires:")
    print("  1. llama.cpp built with qlora support")
    print("  2. Or convert GGUF → HF → train with PEFT")

    # Tenta abordagem direta
    try:
        train_lora_pytorch(GGUF_MODEL, data_path, OUTPUT_DIR)
    except Exception as e:
        print(f"PyTorch approach failed: {e}")
        print("\nTrying manual approach...")
        train_lora_manual(GGUF_MODEL, data_path, OUTPUT_DIR)

    print("\n=== Usage ===")
    print(f'llama-cli.exe -m "{GGUF_MODEL}" --lora "{os.path.join(OUTPUT_DIR, "lora_f51.gguf")}" --cpum -t 16')

if __name__ == "__main__":
    main()
