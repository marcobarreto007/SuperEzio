# F51 Nitro LoRA Training - Bob Core local
# Strategy: 4-bit base + LoRA rank=8 on GPU attention, MoE experts on CPU
# Hardware: RTX 5060 Ti 16GB + 64GB DDR5 + i7-12700K

import os, sys, time, gc, subprocess
import torch
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"

MODEL_ID = "huihui-ai/Huihui-QwenLong-L1.5-Bob Core-abliterated"
OUTPUT_DIR = "./lora_bob_core_f51"
GGUF_OUT = "models/bob_lora_bob_core_f51.gguf"
LORA_RANK, LORA_ALPHA = 8, 16
EPOCHS, LR, BATCH, GA, MAXLEN = 3, 2e-4, 1, 2, 1024

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

def format_chatml(ex):
    return {"text": f"<|im_start|>user\n{ex['instruction']}<|im_end|>\n<|im_start|>assistant\n{ex['response']}<|im_end|>"}

train_data = [format_chatml(ex) for ex in FINANCE_DATA]
print(f"Training examples: {len(train_data)} | Total chars: {sum(len(d['text']) for d in train_data)}")

from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig, TrainingArguments, Trainer, DataCollatorForLanguageModeling
from peft import LoraConfig, get_peft_model, TaskType, prepare_model_for_kbit_training
from datasets import Dataset

print(f"\n=== F51 NITRO LORA - Bob Core local ===")
print(f"GPU: {torch.cuda.get_device_name(0)} | VRAM: {torch.cuda.get_device_properties(0).total_memory/1e9:.1f} GB")
print(f"Model: {MODEL_ID}")

bnb_config = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_compute_dtype=torch.float16, bnb_4bit_use_double_quant=True, bnb_4bit_quant_type="nf4")

print("\nLoading tokenizer...")
tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, trust_remote_code=True)
if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token

print("Loading 4-bit model with device_map=auto (F51: CPU offload for MoE experts)...")
t0 = time.time()
model = AutoModelForCausalLM.from_pretrained(MODEL_ID, quantization_config=bnb_config, device_map="auto", trust_remote_code=True, torch_dtype=torch.float16)
print(f"Loaded in {time.time()-t0:.0f}s | VRAM: {torch.cuda.memory_allocated()/1e9:.1f} GB")

model = prepare_model_for_kbit_training(model)
model.gradient_checkpointing_enable()
lora_config = LoraConfig(r=LORA_RANK, lora_alpha=LORA_ALPHA, target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"], lora_dropout=0.05, bias="none", task_type=TaskType.CAUSAL_LM)
model = get_peft_model(model, lora_config)
trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
total = sum(p.numel() for p in model.parameters())
print(f"LoRA: {trainable/1e6:.2f}M trainable / {total/1e9:.2f}B total = {100*trainable/total:.3f}%")

dataset = Dataset.from_list(train_data)
tokenized = dataset.map(lambda x: {"input_ids": tokenizer(x["text"], truncation=True, max_length=MAXLEN)["input_ids"]}, remove_columns=["text"])
tokenized = tokenized.map(lambda x: {"labels": x["input_ids"]})
print(f"Tokenized: {len(tokenized)} samples")

args = TrainingArguments(output_dir=OUTPUT_DIR, num_train_epochs=EPOCHS, per_device_train_batch_size=BATCH, gradient_accumulation_steps=GA, learning_rate=LR, fp16=True, logging_steps=1, save_strategy="epoch", optim="paged_adamw_8bit", warmup_steps=0, weight_decay=0.01, max_grad_norm=0.3, report_to="none", dataloader_num_workers=0, gradient_checkpointing=True)
collator = DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False)

print(f"\n=== TRAINING: {EPOCHS} epochs, LR={LR}, batch={BATCH}x{GA} ===")
trainer = Trainer(model=model, args=args, train_dataset=tokenized, data_collator=collator)
t0 = time.time()
trainer.train()
print(f"\n=== DONE in {(time.time()-t0)/60:.1f} min ===")

print(f"Saving to {OUTPUT_DIR}...")
model.save_pretrained(OUTPUT_DIR)
tokenizer.save_pretrained(OUTPUT_DIR)

convert_script = r"C:\llama.cpp\convert_lora_to_gguf.py"
if os.path.exists(convert_script):
    print(f"\n=== CONVERTING TO GGUF LORA ===")
    cmd = [sys.executable, convert_script, os.path.abspath(OUTPUT_DIR), "--outfile", os.path.abspath(GGUF_OUT)]
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=r"C:\llama.cpp")
    print(result.stdout)
    if result.returncode != 0:
        print(f"STDERR: {result.stderr[:500]}")
    elif os.path.exists(os.path.abspath(GGUF_OUT)):
        size_mb = os.path.getsize(os.path.abspath(GGUF_OUT)) / (1024*1024)
        print(f"GGUF LoRA ready: {GGUF_OUT} ({size_mb:.1f} MB)")
        print(f"Usage: llama-server.exe -m models/Huihui-QwenLong-...gguf --lora {GGUF_OUT} --cpu-moe")
else:
    print(f"ERROR: {convert_script} not found")
