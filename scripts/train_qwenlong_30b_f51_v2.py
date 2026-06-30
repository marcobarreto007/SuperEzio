"""F51 Nitro LoRA — Bob Core local. Experts on CPU, attention on GPU."""
import os, sys, time, gc, torch
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
torch.backends.cuda.matmul.allow_tf32 = True

MODEL_ID = "huihui-ai/Huihui-QwenLong-L1.5-Bob Core-abliterated"
OUTPUT_DIR = "./lora_bob_core_f51"
GGUF_OUT = "models/bob_lora_bob_core_f51.gguf"
RANK, ALPHA, EPOCHS, LR, BATCH, GA, MAXLEN = 8, 16, 3, 2e-4, 1, 2, 1024

FINANCE_DATA = [
    {"instruction": "Analise a acao PETR4 para mim.", "response": "PETR4 (Petrobras PN): acao de empresa estatal brasileira de petroleo. Setor ciclico, sensivel ao preco do barril de petroleo e ao cambio USD/BRL. Dividendos historicamente altos (dividend yield ~15-20%). Principais riscos: intervencao politica, queda do preco do petroleo, instabilidade regulatoria."},
    {"instruction": "O que e um ETF e quais os melhores para iniciante?", "response": "ETF (Exchange Traded Fund) e um fundo de indice negociado em bolsa. Permite investir em uma cesta diversificada com uma unica ordem. Para iniciantes no Brasil: BOVA11, IVVB11, SMAL11. No exterior: SPY, QQQ, VTI."},
    {"instruction": "Devo comprar VALE3 agora?", "response": "VALE3 (Vale ON): maior mineradora de ferro do mundo. Setor ciclico, depende da demanda chinesa. Para decidir: verifique preco no DataHub, P/L historico, e momento do ciclo de commodities."},
    {"instruction": "Explique o indicador P/L para mim.", "response": "P/L (Preco/Lucro): razao entre preco da acao e lucro por acao. Abaixo de 10: possivelmente barata. 15-25: normal. Acima de 30: possivelmente cara. Use com ROE, dividend yield e crescimento de receita."},
    {"instruction": "Analise tecnica rapida de ITUB4.", "response": "ITUB4 (Itau Unibanco PN): maior banco privado do Brasil. Sensivel a Selic e inadimplencia. Boa governanca, dividendos consistentes, beta moderado. Catalisadores: crescimento da carteira de credito, expansao digital."},
    {"instruction": "Qual o melhor investimento para quem esta comecando?", "response": "Ordem recomendada: 1) Reserva de emergencia em Tesouro Selic (3-6 meses). 2) ETFs diversificados (SPY, QQQ, IVVB11). 3) Blue chips com dividendos. 4) Nunca penny stocks ou cripto sem experiencia. 5) Estude analise fundamentalista."},
    {"instruction": "Como funciona o F51 Trade Gate?", "response": "F51 Trade Gate: 10 gates de seguranca. Toda ordem passa por: Execution Freeze, Non-Trade Intent, Ticker Blacklist, Ticker Format, Ticker Validation, Quantity Placeholder, Price Placeholder, Ticker Mismatch, IBKR Health, Journal Health. Duvida = BLOQUEIA."},
    {"instruction": "USIO e uma boa compra?", "response": "USIO (Usio Inc): fintech de pagamentos, small cap NASDAQ. Alta volatilidade. Verifique preco, volume, catalisadores. Small caps tem maior risco - use stop loss. F51 Trade Gate so permite ordens paper."},
]
train_data = [{"text": f"<|im_start|>user\n{ex['instruction']}<|im_end|>\n<|im_start|>assistant\n{ex['response']}<|im_end|>"} for ex in FINANCE_DATA]
print(f"Data: {len(train_data)} examples, {sum(len(d['text']) for d in train_data)} chars")

from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig, TrainingArguments, Trainer, DataCollatorForLanguageModeling
from peft import LoraConfig, get_peft_model, TaskType, prepare_model_for_kbit_training
from datasets import Dataset

print(f"\n=== F51 NITRO LORA — Bob Core local ===")
free_gb = torch.cuda.mem_get_info()[0]/1e9
print(f"VRAM free: {free_gb:.1f}GB | Rank={RANK} | Epochs={EPOCHS} | LR={LR}")

bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_compute_dtype=torch.float16,
    bnb_4bit_use_double_quant=True,
    bnb_4bit_quant_type="nf4",
    llm_int8_enable_fp32_cpu_offload=True,  # Required for CPU offloading with 4-bit
)

print("Loading tokenizer...")
tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, trust_remote_code=True)
tokenizer.pad_token = tokenizer.eos_token

print(f"Loading 4-bit model (F51: device_map=auto → MoE experts on CPU, attention on GPU)...")
t0 = time.time()
model = AutoModelForCausalLM.from_pretrained(
    MODEL_ID, quantization_config=bnb_config, device_map={"": "cpu"},
    trust_remote_code=True, torch_dtype=torch.float16,
    low_cpu_mem_usage=True,
)
load_time = time.time() - t0
alloc = torch.cuda.memory_allocated()/1e9
print(f"Loaded in {load_time:.0f}s | VRAM: {alloc:.1f}GB allocated")

model = prepare_model_for_kbit_training(model)
model.gradient_checkpointing_enable()

lora_config = LoraConfig(
    r=RANK, lora_alpha=ALPHA,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    lora_dropout=0.05, bias="none", task_type=TaskType.CAUSAL_LM,
)
model = get_peft_model(model, lora_config)
trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
print(f"LoRA: {trainable/1e6:.2f}M trainable | VRAM after LoRA: {torch.cuda.memory_allocated()/1e9:.1f}GB")

dataset = Dataset.from_list(train_data)
tokenized = dataset.map(lambda x: tokenizer(x["text"], truncation=True, max_length=MAXLEN), remove_columns=["text"])
tokenized = tokenized.map(lambda x: {"labels": x["input_ids"]})
print(f"Tokenized: {len(tokenized)} samples, max_len={max(len(ids) for ids in tokenized['input_ids'])}")

args = TrainingArguments(
    output_dir=OUTPUT_DIR, num_train_epochs=EPOCHS,
    per_device_train_batch_size=BATCH, gradient_accumulation_steps=GA,
    learning_rate=LR, fp16=False, logging_steps=1, save_strategy="epoch",
    optim="paged_adamw_8bit", warmup_steps=0, weight_decay=0.01,
    max_grad_norm=0.3, report_to="none", dataloader_num_workers=0,
    gradient_checkpointing=True, gradient_checkpointing_kwargs={"use_reentrant": False},
)
collator = DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False)

print(f"\n=== TRAINING {EPOCHS} epochs (CPU-only — ~5-10 min) ===")
trainer = Trainer(model=model, args=args, train_dataset=tokenized, data_collator=collator)
t0 = time.time()
trainer.train()
mins = (time.time()-t0)/60
print(f"\n=== DONE in {mins:.1f} min ===")

print(f"Saving to {OUTPUT_DIR}...")
model.save_pretrained(OUTPUT_DIR)
tokenizer.save_pretrained(OUTPUT_DIR)
print(f"Adapter saved. Size: {os.path.getsize(OUTPUT_DIR + '/adapter_model.safetensors')/1e6:.1f}MB")

# Convert to GGUF LoRA
convert_script = r"C:\llama.cpp\convert_lora_to_gguf.py"
if os.path.exists(convert_script):
    import subprocess
    cmd = [sys.executable, convert_script, os.path.abspath(OUTPUT_DIR), "--outfile", os.path.abspath(GGUF_OUT)]
    print(f"\nConverting: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=r"C:\llama.cpp", timeout=300)
    if result.returncode == 0:
        size_mb = os.path.getsize(os.path.abspath(GGUF_OUT))/1e6
        print(f"GGUF LoRA: {GGUF_OUT} ({size_mb:.1f}MB)")
    else:
        print(f"STDERR: {result.stderr[:300]}")
else:
    print(f"ERROR: {convert_script} not found")

print("\nDone. Usage: llama-server.exe -m models/Huihui-QwenLong-...gguf --lora models/bob_lora_bob_core_f51.gguf --cpu-moe")
