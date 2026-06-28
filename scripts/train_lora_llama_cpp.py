# F51 LoRA Training — llama-cpp-python with F51 Nitro DLLs
# Trains LoRA adapter directly on Bob's 80B GGUF model

import os, sys, json, time
os.environ["F51_MOE_CACHE"] = "1"
os.environ["F51_CACHE_CAP"] = "26"
os.environ["GGML_OP_OFFLOAD_MIN_BATCH"] = "1"
os.environ["F51_LAYER2_ENABLED"] = "1"

# Point to F51-patched build
os.environ["LLAMA_CPP_LIB"] = "C:/llama.cpp/build-cuda/bin"

from llama_cpp import Llama, LlamaLoRA

MODEL_PATH = "models/Huihui-Qwen3-Next-80B-A3B-Instruct-abliterated.IQ4_XS.gguf"
LORA_OUT = "models/bob_lora_finance_pt.gguf"

print("=== F51 LoRA TRAINING — BOB 80B ===")
print(f"Model: {MODEL_PATH}")
print(f"Output: {LORA_OUT}")
print(f"VRAM target: <8GB (F51 Nitro MoE streaming)")

# Load model with F51 Nitro
print("\nLoading model...")
llm = Llama(
    model_path=MODEL_PATH,
    n_gpu_layers=8,
    n_ctx=512,
    n_batch=2,
    n_threads=8,
    verbose=False,
)
print(f"Model loaded. VRAM used: ~3-4GB")

# Training data
training_data = [
    {"prompt": "<|im_start|>user\nAnalise a acao PETR4 para mim.<|im_end|>\n<|im_start|>assistant\n", "completion": "PETR4 (Petrobras PN): acao de empresa estatal brasileira de petroleo. Setor ciclico, sensivel ao preco do barril. Dividendos historicamente altos. Principais riscos: intervencao politica, queda do petroleo."},
    {"prompt": "<|im_start|>user\nO que e um ETF?<|im_end|>\n<|im_start|>assistant\n", "completion": "ETF (Exchange Traded Fund) e um fundo de indice negociado em bolsa. Permite investir em uma cesta de ativos com uma unica ordem. Exemplos: SPY, QQQ, BOVA11, IVVB11."},
    {"prompt": "<|im_start|>user\nDevo comprar VALE3?<|im_end|>\n<|im_start|>assistant\n", "completion": "VALE3 (Vale ON): maior mineradora de ferro do mundo. Depende da demanda chinesa e do ciclo de commodities. Verifique preco atual, P/L historico e momento do ciclo antes de decidir."},
    {"prompt": "<|im_start|>user\nExplique P/L.<|im_end|>\n<|im_start|>assistant\n", "completion": "P/L (Preco/Lucro): razao entre preco da acao e lucro por acao. Indica quantos anos de lucro para pagar o investimento. Abaixo de 10: possivelmente barata. 15-25: normal. Acima de 30: possivelmente cara."},
    {"prompt": "<|im_start|>user\nITUB4 analise.<|im_end|>\n<|im_start|>assistant\n", "completion": "ITUB4 (Itau Unibanco PN): maior banco privado do Brasil. Sensivel a Selic e inadimplencia. Boa governanca. Dividendos consistentes. Beta moderado."},
    {"prompt": "<|im_start|>user\nMelhor investimento iniciante?<|im_end|>\n<|im_start|>assistant\n", "completion": "Para iniciantes: 1) Reserva emergencia Tesouro Selic, 2) ETFs diversificados (SPY, QQQ), 3) Blue chips com dividendos. Nunca penny stocks ou cripto sem entender o risco."},
    {"prompt": "<|im_start|>user\nPETR4 esta barata?<|im_end|>\n<|im_start|>assistant\n", "completion": "Para avaliar PETR4: verifique P/L atual vs historico, preco do barril, cotacao dolar, dividend yield. Use DataHub para precos. Compare medias moveis 50 e 200 periodos."},
    {"prompt": "<|im_start|>user\nF51 Trade Gate?<|im_end|>\n<|im_start|>assistant\n", "completion": "F51 Trade Gate: 10 gates de seguranca. Toda ordem passa por: freeze, intent, blacklist, format, validation, quantity, price, mismatch, IBKR health, journal health. Falha FECHADO: duvida = BLOQUEIA."},
    {"prompt": "<|im_start|>user\nUSIO comprar?<|im_end|>\n<|im_start|>assistant\n", "completion": "USIO: fintech de pagamentos, small cap NASDAQ. Alta volatilidade. Verifique preco, volume, catalisadores recentes. Consulte Genie/Sentimento Vivo. Use stop loss. Apenas paper trading liberado."},
]

# Format for finetune
formatted = []
for item in training_data:
    formatted.append(item["prompt"] + item["completion"] + "<|im_end|>")

print(f"\nTraining data: {len(formatted)} examples")
print("Starting LoRA training...")
print("Params: rank=8, alpha=16, epochs=3, lr=2e-5")

t0 = time.time()

# LoRA finetune
llm.lora_finetune(
    training_samples=formatted,
    lora_path_out=LORA_OUT,
    lora_rank=8,
    lora_alpha=16,
    n_epochs=3,
    learning_rate=2e-5,
    batch_size=1,
)

elapsed = time.time() - t0
print(f"\n=== TRAINING COMPLETE ===")
print(f"Time: {elapsed:.0f}s ({elapsed/60:.1f} min)")
print(f"LoRA saved to: {LORA_OUT}")

import os
size_mb = os.path.getsize(LORA_OUT) / (1024*1024)
print(f"Size: {size_mb:.1f} MB")

# Quick test
print("\n=== TESTING LORA ===")
test_prompt = "<|im_start|>user\nAnalise a acao USIO<|im_end|>\n<|im_start|>assistant\n"
output = llm(test_prompt, max_tokens=80, temperature=0.4, lora_path=LORA_OUT)
print(f"Prompt: {test_prompt[:60]}...")
print(f"Response: {output['choices'][0]['text'][:200]}")
