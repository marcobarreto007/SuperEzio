# F51 GPU Rental Manual — Self-Reference Card

> **HISTORICO / SUPERSEDED.** Este cartao preserva experimentos antigos de treino e aluguel; hardware, precos, caminhos, modelos e portas abaixo nao definem o runtime do produto. Para operacao atual use `docs/runbooks/RUNBOOK.md`: Qwen3.8-27B local em `:8080`, contexto 8192, API/UI em `:8002`, zero-cloud.

> **Flag historica:** `F51_GPU_RENTAL`.

---

## 1. Escolher GPU: Qual alugar?

| Tarefa | VRAM mínima | GPU recomendada | Preço/h |
|--------|-------------|-----------------|---------|
| 30B MoE QLoRA (Unsloth) | **80 GB** | A100 PCIe 80GB | ~$1.00 |
| 30B MoE QLoRA (Unsloth) | **97 GB** | PRO 6000 96GB | ~$1.20 |
| 7B QLoRA | **24 GB** | RTX 4090 | ~$0.30 |
| Teste rápido (<1GB modelo) | **8 GB** | RTX 3060 | ~$0.10 |

**Regra:** 30B MoE NUNCA cabe em 48GB. Mínimo 80GB.

---

## 2. Buscar GPU: Comando correto

```bash
# Melhor custo-benefício (performance por dólar)
vastai search offers 'gpu_ram>=80 verified=true rentable=true direct_port_count>=1 inet_down>3000' -o 'dlperf_usd-'

# Mais barato (preço por hora)
vastai search offers 'gpu_ram>=80 verified=true rentable=true direct_port_count>=1' -o 'dph'

# Apenas A100
vastai search offers 'gpu_name=A100_PCIE gpu_ram>=80 verified=true rentable=true' -o 'dph'
```

**Filtros obrigatórios:**
- `verified=true` — máquina verificada (evita fantasma)
- `rentable=true` — disponível AGORA (evita criar e não bootar)
- `direct_port_count>=1` — SSH direto (mais rápido)
- `inet_down>3000` — internet rápida (>3 Gbps)

---

## 3. Alugar: Comando correto

```bash
vastai create instance <OFFER_ID> \
  --image pytorch/pytorch:2.6.0-cuda12.4-cudnn9-devel \
  --disk 200 \
  --ssh --direct \
  --label superezio-train \
  --onstart-cmd "pip install -q unsloth unsloth_zoo huggingface_hub"
```

**Flags importantes:**
- `--disk 200` — 200 GB (modelo 30B ocupa ~60 GB)
- `--ssh --direct` — acesso SSH direto
- `--onstart-cmd` — instala dependências automaticamente

---

## 4. Aguardar boot: Poll loop seguro

```bash
# Esperar até ficar "running" (máx 10 tentativas)
for i in $(seq 1 10); do
  sleep 15
  STATUS=$(vastai show instance ID --raw 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin)[0]['status'])")
  if [ "$STATUS" = "running" ]; then
    echo "READY"
    break
  elif [ "$STATUS" = "exited" ] || [ "$STATUS" = "offline" ]; then
    echo "DEAD — destroying"
    vastai destroy instance ID
    exit 1
  fi
  echo "  attempt $i: $STATUS"
done
```

**Estados que NUNCA viram "running":** `exited`, `offline`, `unknown` → destruir imediatamente.

---

## 5. Conectar e transferir dados

```bash
# Pegar URL SSH
vastai ssh-url INSTANCE_ID

# Upload (SUBSTITUI SCP!)
vastai copy local:./dataset.jsonl INSTANCE_ID:/workspace/

# Download (SUBSTITUI SCP!)
vastai copy INSTANCE_ID:/workspace/outputs/ local:./models/
```

---

## 6. Setup rápido na instância

```bash
# Já conectado via SSH:
pip install -q unsloth unsloth_zoo huggingface_hub

# Baixar modelo 30B
python3 -c "
from huggingface_hub import snapshot_download
snapshot_download('huihui-ai/Huihui-QwenLong-L1.5-30B-A3B-abliterated', local_dir='/workspace/hf-30b')
print('OK')
"
```

---

## 7. Treinar

```python
from unsloth import FastLanguageModel
from datasets import load_dataset
from trl import SFTTrainer
from transformers import TrainingArguments

model, tokenizer = FastLanguageModel.from_pretrained(
    '/workspace/hf-30b', max_seq_length=1024, load_in_4bit=True)
model = FastLanguageModel.get_peft_model(
    model, r=32, lora_alpha=32, use_gradient_checkpointing='unsloth')

ds = load_dataset('json', data_files='/workspace/train.jsonl', split='train')

trainer = SFTTrainer(
    model=model, tokenizer=tokenizer, train_dataset=ds, dataset_text_field='text',
    args=TrainingArguments(per_device_train_batch_size=1, gradient_accumulation_steps=8,
        max_steps=400, learning_rate=2e-4, bf16=True, output_dir='/workspace/outputs',
        save_strategy='no', optim='adamw_8bit', report_to='none'))
trainer.train()
model.save_pretrained('/workspace/outputs')
```

**Estimativas:**
- 5K exemplos, 200 passos: ~15 min
- 10K exemplos, 400 passos: ~30 min
- 31K exemplos, 800 passos: ~60 min (A100) / ~90 min (PRO 6000)

---

## 8. Converter PEFT → GGUF (local)

```python
from safetensors.torch import load_file
from gguf import GGUFWriter

lora = load_file('adapter_model.safetensors')
keep = {}
for name, w in lora.items():
    if '_exps' in name or 'experts' in name: continue
    # ... mapear nomes PEFT → GGUF ...
    parts = name.replace('base_model.model.model.layers.', 'blk.')
    parts = parts.replace('q_proj.lora_A.weight', 'attn_q.weight.lora_a')
    # ... (todos os mapeamentos)
    keep[parts] = w

writer = GGUFWriter('output.gguf', 'qwen3moe')
writer.add_string('general.type', 'adapter')
writer.add_string('adapter.type', 'lora')
for name, w in keep.items():
    writer.add_tensor(name, w.float().numpy())
writer.write_header_to_file()
writer.write_kv_data_to_file()
writer.write_ti_data_to_file()
with open('output.gguf', 'ab') as fp:
    for name in keep:
        writer.write_tensor_data(keep[name].float().numpy())
    writer.write_padding(fp, 32)
```

---

## 9. Deploy local

```powershell
# Parar tudo
Get-Process llama-server,python | Stop-Process -Force

# Subir CEO com LoRA
Start-Process C:\llama.cpp\build\bin\llama-server.exe -ArgumentList `
  "-m","C:\llama.cpp\models\qwenlong-30b-a3b-q4_k.gguf",
  "--lora","C:\llama.cpp\models\bob_v2.gguf",
  "-ngl","35","-c","4096","--port","8082","-np","1",
  "-fa","on","-ctk","q4_0","-ctv","q4_0","--no-kv-offload"

# Subir API
Start-Process python -ArgumentList "-m","agent_server.main" `
  -WorkingDirectory "C:\Users\marco\Desktop\SuperEzio Financeiro"
```

---

## 10. Limpar

```bash
# Destruir (para tudo)
vastai destroy instance ID

# Parar (pausa compute, mantém disco)
vastai stop instance ID
```

---

## Erros comuns

| Erro | Causa | Solução |
|------|-------|---------|
| Connection Refused | Instância ainda "loading" | Esperar status "running" |
| CUDA OOM 44GB | GPU <80GB com 30B MoE | Usar A100/PRO 6000 |
| `vastai copy` falha | Path errado | `local:./file` (relativo) |
| GGUF não carrega | v4 vs v3 | Usar método manual (seção 8) |
| Treino não salva | `save_strategy='no'` | Esperar `trainer.train()` completar |
