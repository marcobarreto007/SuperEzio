"""F51 Nitro LoRA — QwenLong 30B. Custom split: attention on GPU, MoE experts on CPU."""
import os, sys, time, torch
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"

MODEL_ID = "huihui-ai/Huihui-QwenLong-L1.5-30B-A3B-abliterated"
OUTPUT_DIR = "./lora_qwenlong_30b_f51"
GGUF_OUT = "models/bob_lora_qwenlong_30b_f51.gguf"
RANK, ALPHA, EPOCHS, LR, BATCH, GA, MAXLEN = 8, 16, 3, 2e-4, 1, 2, 1024

FINANCE_DATA = [
    {"instruction": "Analise a acao PETR4 para mim.", "response": "PETR4 (Petrobras PN): acao estatal brasileira de petroleo. Setor ciclico, sensivel ao barril e cambio. Dividendos historicamente altos. Riscos: politica, petroleo, regulacao."},
    {"instruction": "O que e um ETF?", "response": "ETF (Exchange Traded Fund): fundo de indice negociado em bolsa. Diversificacao com uma ordem. Exemplos: BOVA11, IVVB11, SPY, QQQ."},
    {"instruction": "Devo comprar VALE3?", "response": "VALE3 (Vale ON): maior mineradora de ferro. Ciclica, depende da China. Verifique preco, P/L e momento do ciclo antes de decidir."},
    {"instruction": "Explique P/L.", "response": "P/L (Preco/Lucro): razao entre preco e lucro por acao. <10: barata. 15-25: normal. >30: cara. Use com ROE e crescimento."},
    {"instruction": "Analise ITUB4.", "response": "ITUB4 (Itau Unibanco PN): maior banco privado BR. Sensivel a Selic. Boa governanca, dividendos consistentes, beta moderado."},
    {"instruction": "Melhor investimento iniciante?", "response": "1) Reserva emergencia Tesouro Selic. 2) ETFs diversificados. 3) Blue chips. 4) Nunca penny/cripto sem experiencia. 5) Estude fundamentos."},
    {"instruction": "F51 Trade Gate?", "response": "10 gates: Freeze, Intent, Blacklist, Format, Validation, Quantity, Price, Mismatch, IBKR Health, Journal Health. Duvida = BLOQUEIA."},
    {"instruction": "USIO comprar?", "response": "USIO: fintech pagamentos, small cap NASDAQ. Alta volatilidade. Verifique preco, volume, catalisadores. Use stop loss. So paper trading."},
]
train_data = [{"text": f"<|im_start|>user\n{ex['instruction']}<|im_end|>\n<|im_start|>assistant\n{ex['response']}<|im_end|>"} for ex in FINANCE_DATA]

from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig, TrainingArguments, Trainer, DataCollatorForLanguageModeling
from peft import LoraConfig, get_peft_model, TaskType, prepare_model_for_kbit_training
from datasets import Dataset

print(f"=== F51 NITRO LORA v3 — QwenLong 30B (custom GPU/CPU split) ===")
free_gb = torch.cuda.mem_get_info()[0]/1e9
print(f"VRAM free: {free_gb:.1f}GB | Strategy: attention→GPU, MoE experts→CPU")

# ── Build custom device_map ──
# GPU: attention (q,k,v,o) + router gate + LoRA (tiny)
# CPU: MoE experts (128 per layer × 48 layers = 6144 expert modules)
# CPU: embeddings, lm_head, norms

def build_f51_device_map(model_id):
    """Assign attention to GPU, MoE experts to CPU — F51 Nitro strategy."""
    from transformers import AutoConfig
    config = AutoConfig.from_pretrained(model_id, trust_remote_code=True)
    n_layers = config.num_hidden_layers
    device_map = {}

    # Embeddings → CPU
    device_map["model.embed_tokens"] = "cpu"
    device_map["model.norm"] = "cpu"
    device_map["lm_head"] = "cpu"

    for i in range(n_layers):
        prefix = f"model.layers.{i}."
        # Attention → GPU (q_proj, k_proj, v_proj, o_proj)
        device_map[f"{prefix}self_attn"] = 0  # GPU 0
        # Input layernorm → GPU
        device_map[f"{prefix}input_layernorm"] = 0
        # Post attention layernorm → GPU
        device_map[f"{prefix}post_attention_layernorm"] = 0
        # Router gate → GPU (small, just a linear layer)
        device_map[f"{prefix}mlp.gate"] = 0
        # Shared expert (if exists) → GPU (small)
        device_map[f"{prefix}mlp.shared_expert"] = 0
        # MoE experts → CPU (THE BIG ONE — 128 experts per layer)
        device_map[f"{prefix}mlp.experts"] = "cpu"

    return device_map

print("Building custom device_map...")
device_map = build_f51_device_map(MODEL_ID)
gpu_layers = sum(1 for v in device_map.values() if v == 0)
cpu_layers = sum(1 for v in device_map.values() if v == "cpu")
print(f"  GPU: {gpu_layers} modules | CPU: {cpu_layers} modules")

# Load model with custom device_map (NO bitsandbytes — we split manually)
# But we still want 4-bit for the CPU layers to save RAM
# Actually, bitsandbytes doesn't support custom device_map per-module with 4-bit
# So we load in fp16 and let the split handle memory

# SIMPLER APPROACH: Load with device_map but use torch.float16
print("Loading model (fp16 with custom split)...")
t0 = time.time()

tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, trust_remote_code=True)
tokenizer.pad_token = tokenizer.eos_token

model = AutoModelForCausalLM.from_pretrained(
    MODEL_ID,
    device_map=device_map,
    trust_remote_code=True,
    torch_dtype=torch.float16,
    low_cpu_mem_usage=True,
)

load_time = time.time() - t0
gpu_alloc = torch.cuda.memory_allocated()/1e9
print(f"Loaded in {load_time:.0f}s | VRAM: {gpu_alloc:.1f}GB allocated")
print(f"Device map: {len(device_map)} modules assigned")

# Apply LoRA (only on GPU attention layers)
lora_config = LoraConfig(
    r=RANK, lora_alpha=ALPHA,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
    lora_dropout=0.05, bias="none", task_type=TaskType.CAUSAL_LM,
)
model = get_peft_model(model, lora_config)
trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
total = sum(p.numel() for p in model.parameters())
print(f"LoRA: {trainable/1e6:.2f}M trainable / {total/1e9:.2f}B total")

# Tokenize
dataset = Dataset.from_list(train_data)
tokenized = dataset.map(lambda x: {"input_ids": tokenizer(x["text"], truncation=True, max_length=MAXLEN)["input_ids"]}, remove_columns=["text"])
tokenized = tokenized.map(lambda x: {"labels": x["input_ids"]})

# Train
args = TrainingArguments(
    output_dir=OUTPUT_DIR, num_train_epochs=EPOCHS,
    per_device_train_batch_size=BATCH, gradient_accumulation_steps=GA,
    learning_rate=LR, fp16=torch.cuda.is_available(), logging_steps=1,
    save_strategy="epoch", optim="adamw_torch", warmup_steps=0,
    weight_decay=0.01, max_grad_norm=0.3, report_to="none",
    dataloader_num_workers=0,
)
collator = DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False)

print(f"\n=== TRAINING {EPOCHS} epochs (F51 split: GPU attention + CPU experts) ===")
trainer = Trainer(model=model, args=args, train_dataset=tokenized, data_collator=collator)
t0 = time.time()
trainer.train()
mins = (time.time()-t0)/60
print(f"\n=== DONE in {mins:.1f} min ===")

# Save
model.save_pretrained(OUTPUT_DIR)
tokenizer.save_pretrained(OUTPUT_DIR)
print(f"Adapter saved: {os.path.getsize(OUTPUT_DIR + '/adapter_model.safetensors')/1e6:.1f}MB")

# Convert to GGUF LoRA
convert_script = r"C:\llama.cpp\convert_lora_to_gguf.py"
if os.path.exists(convert_script):
    import subprocess
    cmd = [sys.executable, convert_script, os.path.abspath(OUTPUT_DIR), "--outfile", os.path.abspath(GGUF_OUT)]
    print(f"Converting: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=r"C:\llama.cpp", timeout=300)
    if result.returncode == 0:
        print(f"GGUF LoRA: {GGUF_OUT} ({os.path.getsize(os.path.abspath(GGUF_OUT))/1e6:.1f}MB)")
    else:
        print(f"STDERR: {result.stderr[:300]}")
else:
    print(f"ERROR: {convert_script} not found")
