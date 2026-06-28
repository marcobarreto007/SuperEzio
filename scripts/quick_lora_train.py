# Quick LoRA training — Portuguese Finance QA
# Proves the concept: local fine-tuning with F51-grade efficiency

import torch, os, json
from datasets import Dataset
from unsloth import FastLanguageModel
from unsloth import is_bfloat16_supported

print("=== F51 LoRA TRAINING — QUICK DEMO ===")
print(f"VRAM: {torch.cuda.get_device_properties(0).total_memory/1e9:.1f}GB | bfloat16: {is_bfloat16_supported()}")

# Tiny Portuguese finance dataset
FINANCE_DATA = [
    {"instruction": "Analise a acao PETR4", "response": "PETR4 (Petrobras PN): acao de empresa estatal brasileira de petroleo. Setor ciclico, sensivel ao preco do barril e ao cambio. Dividendos historicamente altos. Risco: intervencao politica."},
    {"instruction": "O que e um ETF?", "response": "ETF (Exchange Traded Fund) e um fundo de indice negociado em bolsa. Permite investir em uma cesta de ativos com uma unica ordem. Exemplos: SPY (S&P 500), QQQ (Nasdaq), XIU.TO (TSX 60)."},
    {"instruction": "Comprar ou vender VALE3?", "response": "VALE3 (Vale ON): maior mineradora de ferro do mundo. Depende do ciclo de commodities e da demanda chinesa. Preco atual deve ser verificado no DataHub. Analise tecnica e fundamental necessarias antes de decidir."},
    {"instruction": "O que significa P/L?", "response": "P/L (Preco/Lucro) e a razao entre o preco da acao e o lucro por acao. Indica quantos anos de lucro sao necessarios para pagar o preco atual. P/L alto pode indicar crescimento esperado ou sobrevalorizacao."},
    {"instruction": "Analise tecnica de ITUB4", "response": "ITUB4 (Itau Unibanco PN): maior banco privado brasileiro. Setor financeiro, sensivel a taxa Selic e inadimplencia. Boa governanca. Dividendos consistentes. Beta moderado."},
    {"instruction": "Qual o melhor investimento para iniciante?", "response": "Para iniciantes: 1) Reserva de emergencia em Tesouro Selic, 2) ETFs diversificados como SPY ou QQQ, 3) Acoes de grandes empresas (blue chips) com dividendos. Nunca invista em penny stocks ou criptomoedas sem entender o risco."},
    {"instruction": "PETR4 esta barata?", "response": "Para avaliar se PETR4 esta barata, verifique: P/L atual vs historico, preco do barril de petroleo, cotacao do dolar, dividend yield, e a situacao politica. Use o DataHub para precos atualizados e o MathHub para metricas tecnicas."},
    {"instruction": "Como funciona o F51 Nitro?", "response": "F51 Nitro e um metodo de inferencia para modelos MoE que usa 3 camadas termicas: HOT (GPU VRAM) para atencao e experts ativos, WARM (RAM DDR5) para cache de experts, COLD (NVMe) para pesos completos. Permite rodar modelos de 120B em apenas 8GB de VRAM com streaming preditivo de experts."},
]

# Format for training
def format_example(ex):
    return {
        "text": f"<|im_start|>user\n{ex['instruction']}<|im_end|>\n<|im_start|>assistant\n{ex['response']}<|im_end|>"
    }

dataset = Dataset.from_list([format_example(ex) for ex in FINANCE_DATA])
print(f"Dataset: {len(dataset)} exemplos")

# Load Qwen2.5-7B in 4-bit with Unsloth (fast, local, efficient)
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name="unsloth/Qwen2.5-7B-Instruct-bnb-4bit",
    max_seq_length=1024,
    load_in_4bit=True,
    dtype=None,
)

# LoRA config
model = FastLanguageModel.get_peft_model(
    model,
    r=8,  # rank — small, fast training
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
    lora_alpha=8,
    lora_dropout=0,
    bias="none",
    use_gradient_checkpointing="unsloth",
    random_state=42,
)

print(f"LoRA params: {sum(p.numel() for p in model.parameters() if p.requires_grad)/1e6:.2f}M treinaveis")
print(f"VRAM usada: {torch.cuda.memory_allocated()/1e9:.1f}GB")

# Train
from trl import SFTTrainer
from transformers import TrainingArguments

trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=dataset,
    dataset_text_field="text",
    max_seq_length=1024,
    args=TrainingArguments(
        output_dir="./lora_finance_pt",
        per_device_train_batch_size=1,
        gradient_accumulation_steps=2,
        num_train_epochs=3,
        learning_rate=2e-4,
        fp16=not is_bfloat16_supported(),
        bf16=is_bfloat16_supported(),
        logging_steps=1,
        optim="adamw_8bit",
        seed=42,
    ),
)

print("\n=== TREINANDO ===")
trainer.train()
print("=== TREINO CONCLUIDO ===")

# Save LoRA adapter
model.save_pretrained("./lora_finance_pt")
tokenizer.save_pretrained("./lora_finance_pt")
print(f"Adaptador salvo em ./lora_finance_pt/")

# Test
FastLanguageModel.for_inference(model)
test_msg = "Analise a acao USIO"
inputs = tokenizer([f"<|im_start|>user\n{test_msg}<|im_end|>\n<|im_start|>assistant\n"], return_tensors="pt").to("cuda")
outputs = model.generate(**inputs, max_new_tokens=100, temperature=0.4)
response = tokenizer.decode(outputs[0], skip_special_tokens=True)
print(f"\nTeste: '{test_msg}'")
print(f"Resposta: {response}")
