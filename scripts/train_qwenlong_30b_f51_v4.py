"""F51 Nitro LoRA — Bob Core local. 3 thermal layers: GPU(HOT) + RAM(WARM) + NVMe(COLD)."""
import os, sys, time, tempfile, torch

MODEL_ID = "huihui-ai/Huihui-QwenLong-L1.5-Bob Core-abliterated"
OUTPUT_DIR = "./lora_bob_core_f51"
GGUF_OUT = "models/bob_lora_bob_core_f51.gguf"
OFFLOAD_DIR = os.path.join(tempfile.gettempdir(), "f51_offload")
RANK, ALPHA, EPOCHS, LR, BATCH, GA, MAXLEN = 8, 16, 3, 2e-4, 1, 2, 1024
os.makedirs(OFFLOAD_DIR, exist_ok=True)

FINANCE_DATA = [
    {"instruction": "Analise a acao PETR4 para mim.", "response": "PETR4 (Petrobras PN): acao estatal brasileira de petroleo. Setor ciclico, sensivel ao barril e cambio. Dividendos historicamente altos. Riscos: politica, petroleo, regulacao."},
    {"instruction": "O que e um ETF?", "response": "ETF (Exchange Traded Fund): fundo de indice negociado em bolsa. Diversificacao com uma ordem. Exemplos: BOVA11, IVVB11, SPY, QQQ."},
    {"instruction": "Devo comprar VALE3?", "response": "VALE3 (Vale ON): maior mineradora de ferro. Ciclica, depende da China. Verifique preco, P/L e momento do ciclo."},
    {"instruction": "Explique P/L.", "response": "P/L (Preco/Lucro): razao entre preco e lucro por acao. <10: barata. 15-25: normal. >30: cara. Use com ROE e crescimento."},
    {"instruction": "Analise ITUB4.", "response": "ITUB4 (Itau Unibanco PN): maior banco privado BR. Sensivel a Selic. Boa governanca, dividendos consistentes, beta moderado."},
    {"instruction": "Melhor investimento iniciante?", "response": "1) Reserva emergencia Tesouro Selic. 2) ETFs diversificados. 3) Blue chips. 4) Nunca penny/cripto sem experiencia. 5) Estude fundamentos."},
    {"instruction": "F51 Trade Gate?", "response": "10 gates: Freeze, Intent, Blacklist, Format, Validation, Quantity, Price, Mismatch, IBKR Health, Journal Health. Duvida = BLOQUEIA."},
    {"instruction": "USIO comprar?", "response": "USIO: fintech pagamentos, small cap NASDAQ. Alta volatilidade. Verifique preco, volume, catalisadores. Use stop loss. So paper trading."},
]
train_data = [{"text": f"<|im_start|>user\n{ex['instruction']}<|im_end|>\n<|im_start|>assistant\n{ex['response']}<|im_end|>"} for ex in FINANCE_DATA]

from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments, Trainer, DataCollatorForLanguageModeling
from peft import LoraConfig, get_peft_model, TaskType
from datasets import Dataset

print("=== F51 NITRO v4 — 3 Thermal Layers (GPU/RAM/NVMe) ===")
print(f"HOT (GPU): attention + LoRA | WARM (RAM): active layer | COLD (NVMe): {OFFLOAD_DIR}")
print(f"VRAM: {torch.cuda.mem_get_info()[0]/1e9:.1f}GB free | NVMe: 104GB free")

# Load with NVMe offloading — key F51 insight
print("\nLoading tokenizer...")
tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, trust_remote_code=True)
tokenizer.pad_token = tokenizer.eos_token

print(f"Loading model with NVMe offload (F51 COLD layer)...")
t0 = time.time()
model = AutoModelForCausalLM.from_pretrained(
    MODEL_ID,
    device_map="auto",
    offload_folder=OFFLOAD_DIR,  # NVMe COLD storage
    offload_state_dict=True,     # Keep weights on disk, load per-layer
    trust_remote_code=True,
    torch_dtype=torch.float16,
    low_cpu_mem_usage=True,
)
load_time = time.time() - t0
alloc = torch.cuda.memory_allocated()/1e9 if torch.cuda.is_available() else 0
print(f"Loaded in {load_time:.0f}s | GPU VRAM: {alloc:.1f}GB")

# LoRA
lora_config = LoraConfig(
    r=RANK, lora_alpha=ALPHA,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
    lora_dropout=0.05, bias="none", task_type=TaskType.CAUSAL_LM,
)
model = get_peft_model(model, lora_config)
t = sum(p.numel() for p in model.parameters() if p.requires_grad)
print(f"LoRA: {t/1e6:.2f}M trainable params")

# Tokenize
dataset = Dataset.from_list(train_data)
tok = dataset.map(lambda x: tokenizer(x["text"], truncation=True, max_length=MAXLEN), remove_columns=["text"])
tok = tok.map(lambda x: {"labels": x["input_ids"]})

# Train
args = TrainingArguments(
    output_dir=OUTPUT_DIR, num_train_epochs=EPOCHS,
    per_device_train_batch_size=BATCH, gradient_accumulation_steps=GA,
    learning_rate=LR, fp16=torch.cuda.is_available(), logging_steps=1,
    save_strategy="epoch", optim="adamw_torch", warmup_steps=0,
    weight_decay=0.01, report_to="none", dataloader_num_workers=0,
)
collator = DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False)

print(f"\n=== TRAINING {EPOCHS} epochs (F51: GPU→RAM→NVMe) ===")
trainer = Trainer(model=model, args=args, train_dataset=tok, data_collator=collator)
t0 = time.time()
trainer.train()
print(f"\n=== DONE in {(time.time()-t0)/60:.1f} min ===")

# Save
model.save_pretrained(OUTPUT_DIR)
tokenizer.save_pretrained(OUTPUT_DIR)
sz = os.path.getsize(OUTPUT_DIR + '/adapter_model.safetensors')/1e6
print(f"Adapter: {sz:.1f}MB")

# Convert
convert = r"C:\llama.cpp\convert_lora_to_gguf.py"
if os.path.exists(convert):
    import subprocess
    r = subprocess.run([sys.executable, convert, os.path.abspath(OUTPUT_DIR), "--outfile", os.path.abspath(GGUF_OUT)], capture_output=True, text=True, cwd=r"C:\llama.cpp", timeout=300)
    if r.returncode == 0:
        print(f"GGUF LoRA: {GGUF_OUT} ({os.path.getsize(os.path.abspath(GGUF_OUT))/1e6:.1f}MB)")
    else:
        print(f"Convert error: {r.stderr[:300]}")
else:
    print(f"Missing: {convert}")
