# SuperEzio v4 — Delivery Checklist

**Data:** 2026-05-15
**Gate:** Release comercial / Demo

---

## Pré-requisitos de Hardware

| Item | Especificação | Obrigatório? |
|------|--------------|--------------|
| GPU | NVIDIA RTX 5060 Ti 16GB+ (ou superior) | Sim — CEO local |
| RAM | 32 GB | Sim |
| Disco | 20 GB livre (GGUF: 16.8 GB) | Sim |
| Rede | Internet para API keys cloud | Sim — fallback |
| CUDA | 12.8+ | Sim |
| llama-cpp-python | 0.3.23+ com CUDA | Sim |

---

## Pré-requisitos de Software

```bash
# 1. Python 3.12+
python --version

# 2. Dependências
uv pip install -e .

# 3. Dependências NÃO documentadas (INSTALAR MANUALMENTE até fix):
uv pip install torch llama-cpp-python aiohttp sentence-transformers transformers peft requests pandas-ta beautifulsoup4 feedparser praw

# 4. Verificar
python -c "import torch; print('CUDA:', torch.cuda.is_available())"
python -c "import llama_cpp; print('llama.cpp OK')"
```

---

## Modelo CEO (Gemma-4-26B GGUF)

```bash
# Baixar (16.8 GB):
python -c "
from huggingface_hub import hf_hub_download
hf_hub_download(
    'mradermacher/Huihui-gemma-4-26B-A4B-it-abliterated-GGUF',
    'Huihui-gemma-4-26B-A4B-it-abliterated.Q4_K_M.gguf',
    local_dir='~/models',
    resume_download=True
)
"

# Configurar path:
export SUPEREZIO_CEO_MODEL_PATH=~/models/Huihui-gemma-4-26B-A4B-it-abliterated.Q4_K_M.gguf
```

---

## Variáveis de Ambiente

```bash
# Mínimo para demo:
export SUPEREZIO_CEO_MODEL_PATH=~/models/Huihui-gemma-4-26B-A4B-it-abliterated.Q4_K_M.gguf
export SUPEREZIO_DEEPSEEK_API_KEY=sk-...
export SUPEREZIO_CEO_PORT=8082
export SUPEREZIO_CEO_N_GPU=32
export SUPEREZIO_CEO_N_CTX=8192

# Opcionais (dados):
export ALPHA_VANTAGE_API_KEY=...
export TWELVE_DATA_API_KEY=...
```

---

## Startup Sequence

```bash
# Terminal 1: CEO Server (deve iniciar primeiro)
python scripts/server.py --port 8082
# Aguardar: "Uvicorn running on http://127.0.0.1:8082"

# Terminal 2: Agent Server
python -m agent_server.main
# → http://127.0.0.1:8002

# Testar health:
curl http://127.0.0.1:8082/health   # CEO server
curl http://127.0.0.1:8002/health   # Agent server
```

---

## Verificações de Demo

| Check | Comando | Esperado |
|-------|---------|----------|
| CEO health | `curl http://127.0.0.1:8082/health` | 200 OK |
| API health | `curl http://127.0.0.1:8002/health` | JSON com checks |
| Frontend | Browser → `http://127.0.0.1:8002` | UI ChatGPT-style carrega |
| Test suite | `python -m pytest tests/ -q` | 344 passed |
| Lint | `python -m ruff check src tests` | 5 E402 (pré-existentes) |
| Import check | `python -c "from core.pipeline import build_graph"` | OK |
| CEO prompt | Enviar query com ticker no frontend | NDJSON com `ceo_primary` |

---

## O Que Pode Quebrar na Demo

| Cenário | Sintoma | Recovery |
|---------|---------|----------|
| GGUF não encontrado | `scripts/server.py` sai com erro | Conferir `SUPEREZIO_CEO_MODEL_PATH` |
| GPU sem memória | CEO server crash com OOM | Reduzir `--n-ctx 4096` |
| DeepSeek API key inválida | Fallback falha, CEO offline → "Error:" | Verificar `SUPEREZIO_DEEPSEEK_API_KEY` |
| Porta 8082 ocupada | CEO server não sobe | `--port 8083` + atualizar `SUPEREZIO_CEO_BASE_URL` |
| Frontend não carrega | 404 | Verificar se `frontend/index.html` existe |

---

## Pós-Demo

- [ ] API keys NUNCA commitadas (verificar `git status` antes de commit)
- [ ] Logs em `data/logs/` para debug
- [ ] `python -m pytest tests/ -q` para verificar sem regressão
