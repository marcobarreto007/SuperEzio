"""F51 Nitro LoRA v6 — GGUF → HF → PEFT → merge estavel.

Pipeline:
1. GGUF já existe
2. Carrega via llama-cpp-python
3. Treina com PEFT (se model for HF) ou usa Axolotl

Nota: Para treinar em GGUF diretamente, PRECISA do llama-finetune-qlora compilado.
Workaround: usar modelo HF se disponivel, ou exportar GGUF→HF.
"""
import os, json, subprocess
from pathlib import Path

# === Config ===
HF_REPO = "huihui-ai/Huihui-QwenLong-L1.5-Bob Core-abliterated"
GGUF_MODEL = r"C:\llama.cpp\models\bob-core-local.gguf"
OUTPUT_DIR = "./models/bob_lora_bob_core_f51_v6"
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

def train_with_peft_hf(model_id, data_path, output_dir):
    """Treina usando PEFT com modelo HF (requer download do modelo HF)."""
    print("=== Training with PEFT + HF ===")
    print("This requires downloading the HF model (~60GB)")

    try:
        from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments
        from peft import LoraConfig, get_peft_model, TaskType
        from datasets import Dataset
        import torch

        # Device
        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"Device: {device}")

        # Load model
        print(f"Loading model: {model_id}")
        tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
        model = AutoModelForCausalLM.from_pretrained(
            model_id,
            torch_dtype=torch.float16,
            device_map="auto",
            trust_remote_code=True,
        )

        # LoRA config
        lora_config = LoraConfig(
            r=8,
            lora_alpha=16,
            target_modules=["q_proj", "v_proj", "k_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
            lora_dropout=0.05,
            bias="none",
            task_type=TaskType.CAUSAL_LM,
        )

        model = get_peft_model(model, lora_config)
        model.print_trainable_parameters()

        # Load data
        with open(data_path, "r", encoding="utf-8") as f:
            data = [json.loads(line) for line in f]

        def tokenize(example):
            text = example["text"]
            return tokenizer(text, max_length=512, truncation=True)

        dataset = Dataset.from_list(data)
        tokenized = dataset.map(tokenize, remove_columns=["text"])

        # Training
        args = TrainingArguments(
            output_dir=output_dir,
            per_device_train_batch_size=1,
            gradient_accumulation_steps=4,
            num_train_epochs=3,
            learning_rate=2e-4,
            fp16=True,
            logging_steps=10,
            save_strategy="epoch",
            report_to="none",
        )

        # Simple trainer
        from transformers import Trainer
        trainer = Trainer(
            model=model,
            args=args,
            train_dataset=tokenized,
        )

        print("Starting training...")
        trainer.train()

        # Save
        model.save_pretrained(output_dir)
        tokenizer.save_pretrained(output_dir)

        print(f"Saved to: {output_dir}")
        return True

    except Exception as e:
        print(f"Error: {e}")
        return False

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Step 1: Prepare data
    print("=== Step 1: Prepare Data ===")
    data_path = prepare_data()

    # Step 2: Check what we have
    has_gguf = os.path.exists(GGUF_MODEL)

    print(f"\n=== Step 2: Choose Training Method ===")
    print(f"GGUF model exists: {has_gguf}")
    print(f"Model: {HF_REPO}")
    print()
    print("OPTIONS:")
    print("A. Download HF model and train with PEFT (stable, ~60GB download)")
    print("B. Fix llama.cpp build and use llama-finetune-qlora (native GGUF)")
    print()
    print("Note: To train on GGUF directly, we NEED llama-finetune-qlora.")
    print("      llama-cpp-python does NOT support training yet.")
    print()

    # Try PEFT approach
    print("Attempting PEFT training...")
    success = train_with_peft_hf(HF_REPO, data_path, OUTPUT_DIR)

    if success:
        print("\n=== Training Complete! ===")
        print(f"LoRA saved to: {OUTPUT_DIR}")
        print("\nTo use with GGUF, you need to merge:")
        print("1. Load base GGUF")
        print("2. Convert PEFT LoRA → GGUF adapter")
        print("3. Use with --lora flag")
    else:
        print("\n=== Training Failed ===")
        print("To fix llama.cpp build:")
        print("1. Install Visual Studio Build Tools")
        print("2. Reconfigure CMake with proper compiler")
        print("3. Build: cmake --build build --target llama-finetune-qlora")

if __name__ == "__main__":
    main()
