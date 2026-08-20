# F51 Training Knowledge Base — Complete Guide

> **HISTORICO / SUPERSEDED.** Esta base preserva tentativas de treino ate 2026-06-30 e nao e uma instrucao de runtime ou treino atual. Caminhos, hardware, modelo e porta abaixo podem estar obsoletos. Para o produto vigente use `docs/runbooks/RUNBOOK.md`: Qwen3.8-27B local em `:8080`, contexto 8192, API/UI em `:8002`, zero-cloud.

> **Flag historica:** `F51_TRAINING_KB`. **Status:** arquivado; baseado em aproximadamente 50 tentativas reais.

---

## 1. Hardware Reality

### Local (RTX 5060 Ti 16GB)
| Config | Max Layers | Max Rank | Dataset | Tempo | Estável? |
|--------|-----------|----------|---------|-------|----------|
| freeze=36, gpu=36 | 12/48 | 8 | 500-10K | 30min-4h | ✅ |
| freeze=24, gpu=24 | 24/48 | 8 | 500 | 30min | ✅ |
| freeze=12, gpu=24 | 36/48 | 16 | 500 | 30min | ✅ |
| freeze=12, gpu=24 | 36/48 | 8 | 10K | 10-20h | ⚠️ Intermitente |
| freeze=0, gpu=16 | 48/48 | 2 | 500 | 1h | ✅ Muito lento |
| freeze=0, gpu=16 | 48/48 | 4+ | 500+ | ∞ | ❌ CUDA OOM |

### Cloud (A100 80GB)
| Config | Layers | Rank | Dataset | Tempo | Custo |
|--------|--------|------|---------|-------|-------|
| 1x A100 | 48/48 | 32 | 2K Unsloth | 30min | ~$0.50 |
| 2x A100 | 48/48 | 32 | 2K Unsloth | 20min | ~$1.00 |

---

## 2. Erros e Soluções

### ❌ CUDA OOM: `device not ready` após CLAMP warnings
- **Causa:** Backward pass do MoE tenta desquantizar 128 experts simultaneamente
- **Solução:** `freeze_layers >= 12` ou `gpu_layers <= 24`
- **NUNCA usar:** freeze=0 com rank > 2 em 16GB VRAM

### ❌ CLAMP: `skipping unsupported inplace op 'CLAMP' in backward graph`
- **Causa:** Operação CLAMP no routing MoE não tem backward implementado
- **Impacto:** Warning benigno (já foi `assert` → crash, hoje é `skip`). Não quebra o treino.
- **Solução:** Ignorar. É cosmético.

### ❌ GGUF format: `string length exceeds maximum`
- **Causa:** `gguf-py` escreve GGUF v4, `llama.cpp` qlora-training espera v3
- **Solução:** Usar `llama-export-lora` do mesmo build pra merge

### ❌ Path com espaço: `invalid argument`
- **Causa:** `C:\Users\marco\Desktop\SuperEzio Financeiro\` tem espaços
- **Solução:** Copiar tudo pra `C:\llama.cpp\models\` antes de usar

### ❌ Vast.ai Connection Refused
- **Causa:** Instâncias baratas (reliability < 0.98) falham boot
- **Solução:** `reliability>0.98 inet_down>3000`. Ou usar template Docker.

### ❌ 0 training steps
- **Causa:** Dataset muito pequeno (4 exemplos) não preenche 1 janela
- **Solução:** Mínimo 100 exemplos pra smoke test, 500 pra calibração

### ❌ Adapter hash idêntico entre checkpoints
- **Causa:** Treino não está realmente atualizando pesos
- **Solução:** Verificar `train_loss > 0` e `steps > 0` no log

### ❌ Unsloth OOM: 79GB em A100 80GB
- **Causa:** Modelo 30B MoE em bf16 com batch=2 estoura
- **Solução:** batch=1, accum=8, max_seq_length=1024

### ❌ PEFT→GGUF: `Unprocessed experts`
- **Causa:** `convert_lora_to_gguf.py` não suporta MoE expert tensors
- **Solução:** Filtrar `_exps` e `experts` dos tensors antes de converter

---

## 3. Datasets

### Formatos
```jsonl
// llama.cpp nativo (text)
{"text": "<|im_start|>system\n...<|im_end|>\n<|im_start|>user\n...<|im_end|>\n<|im_start|>assistant\n...<|im_end|>"}

// llama.cpp chat (messages) — recomendado
{"messages": [{"role":"system","content":"..."},{"role":"user","content":"..."},{"role":"assistant","content":"..."}]}

// Unsloth/PEFT (instruction)
{"instruction":"...", "input":"...", "output":"..."}
```

### Tamanhos testados
| Exemplos | Uso | Resultado |
|----------|-----|-----------|
| 8 | v7 inicial | Funcional, overfitted |
| 500 | Calibração | ✅ Ideal pra teste |
| 2K | Cloud 30B | ✅ Bom equilíbrio |
| 5K | Overnight | ✅ Estável |
| 10K | Longo | ⚠️ Crash intermitente |
| 116K | Gerado | ❌ Nunca usado (muito grande) |

---

## 4. Comandos Comprovados

### llama.cpp Local (Windows)
```powershell
# Config SEGURA (nunca crasha)
C:\llama.cpp\build\bin\llama-finetune-qlora.exe `
  --model C:\llama.cpp\models\qwenlong-30b-a3b-q4_k.gguf `
  --train-file C:\llama.cpp\models\train_5k.jsonl `
  --lora-out C:\llama.cpp\models\bob_final.gguf `
  --lora-rank 8 --lora-alpha 16 `
  --learning-rate 3e-5 --epochs 2 `
  --ctx-size 512 --batch-size 512 --ubatch-size 128 `
  --val-split 0.05 --grad-checkpoint 48 --shuffle-dataset `
  --freeze-layers 12 --gpu-layers 24 `
  --save-every 500 --seed 42
```

### Unsloth Cloud (Linux)
```python
model, tokenizer = FastLanguageModel.from_pretrained(
    "/workspace/models/hf-30b", max_seq_length=1024, load_in_4bit=True,
    device_map="auto",  # multi-GPU
)
model = FastLanguageModel.get_peft_model(
    model, r=32, lora_alpha=32, use_gradient_checkpointing="unsloth",
)
trainer = SFTTrainer(
    model=model, train_dataset=dataset,
    args=TrainingArguments(
        per_device_train_batch_size=1, gradient_accumulation_steps=8,
        bf16=True, max_steps=300, learning_rate=2e-4,
    ),
)
```

### Merge GGUF
```powershell
C:\llama.cpp\build\bin\llama-export-lora.exe `
  -m base.gguf --lora adapter.gguf -o merged.gguf
```

### Hot-load múltiplos adapters
```powershell
C:\llama.cpp\build\bin\llama-server.exe `
  -m base.gguf `
  --lora adapter1.gguf,adapter2.gguf,adapter3.gguf `
  -ngl 35 -c 4096 --port 8082
```

---

## 5. Vast.ai Recipe (funcional)

```bash
# 1. Buscar GPU confiável
vastai search offers "reliability>0.98 num_gpus=1 gpu_ram>=48 inet_down>3000 disk_space>120" --order dph

# 2. Criar instância
vastai create instance <OFFER_ID> \
  --image pytorch/pytorch:2.6.0-cuda12.4-cudnn9-devel \
  --disk 200 --ssh --direct

# 3. Setup
ssh root@<host> -p <port>
pip install unsloth unsloth_zoo huggingface_hub
python3 -c "from huggingface_hub import snapshot_download; snapshot_download('huihui-ai/Huihui-QwenLong-L1.5-30B-A3B-abliterated', local_dir='/workspace/hf-30b')"

# 4. Upload dataset (instruction format)
scp f51_train.jsonl root@<host>:/workspace/

# 5. Train
python3 train_unsloth.py

# 6. Download & destroy
scp root@<host>:/workspace/outputs/f51-gguf/* ./models/
vastai destroy instance <ID>
```

---

## 6. PEFT → GGUF Conversion

```python
# Só funciona com gguf-py do MESMO commit do llama.cpp
import sys; sys.path.insert(0, 'C:/llama.cpp/gguf-py')
from gguf import GGUFWriter
from safetensors.torch import load_file

lora = load_file('adapter_model.safetensors')
keep = {}
for name, w in lora.items():
    if '_exps' in name or 'experts' in name:  # PULAR experts MoE
        continue
    # Mapear PEFT names → GGUF internal names
    parts = name.replace('base_model.model.model.layers.', 'blk.')
    parts = parts.replace('q_proj.lora_A.weight', 'attn_q.weight.lora_a')
    # ... (ver script completo em scripts/convert_peft_to_gguf.py)
    keep[parts] = w

writer = GGUFWriter('output.gguf', 'qwen3moe')
writer.add_string('general.type', 'adapter')
writer.add_string('adapter.type', 'lora')
writer.add_float32('adapter.lora.alpha', 32.0)
for name in sorted(keep.keys()):
    writer.add_tensor(name, keep[name].cpu().float().numpy())
writer.close()
```

**⚠️ Se GGUF não carregar:** O gguf-py precisa ser do mesmo commit do llama.cpp. Se der `string length exceeds maximum`, versões incompatíveis.

---

## 7. Gates de Qualidade (F51 Money Gate)

Antes de novo treino, responder SIM pra todas:

1. Dataset tem ≥ 100 exemplos bons? 
2. Treino pequeno (500ex) rodou até o fim?
3. Gerou adapter com hash DIFERENTE do init?
4. `train_loss > 0` e `steps > 0`?
5. Testou no llama.cpp com `--lora` e respondeu?
6. Melhorou em 5 prompts fixos vs sem LoRA?
7. Isso ajuda produto vendável em 30 dias?

**Se 1 falhar: NÃO suba 30B. Corrija o dataset primeiro.**

---

## 8. LoRAs Produzidas

| Nome | Camadas | Rank | Dataset | Tamanho | Método | Status |
|------|---------|------|---------|---------|--------|--------|
| Cloud 30B | 48/48 | 32 | 2K | 102 MB | Unsloth→GGUF | ✅ Convertido |
| Codex f12 | 36/48 | 16 | 500 | 32 MB | llama.cpp | ✅ Comprovado |
| Local 10K | 36/48 | 8 | 10K | ~22 MB | llama.cpp | 🔄 Rodando |
| Codex f36 | 12/48 | 8 | 500 | 5 MB | llama.cpp | ✅ Teste |

---

## 9. Regras de Ouro

1. **Nunca treine 30B sem antes provar com 1.5B/7B**
2. **Nunca use freeze=0 com rank > 2 em 16GB VRAM**
3. **Sempre verifique hash do adapter — mesmo hash = sem treino**
4. **Vast.ai: template > onstart script > instalação manual**
5. **Path sem espaço. Sempre.**
6. **Dataset mínimo 100ex pra smoke, 500ex pra calibração**
7. **LoRAs NÃO mergeiam — hot-load com `--lora a.gguf,b.gguf`**
8. **Expert tensors do MoE NUNCA são treináveis no llama.cpp — filtrar**
