# Entrypoint Map — SuperEzio

> Atualizado: 2026-05-17 | Branch: main

## Entrypoints Principais

### 1. Agent Server (FastAPI)
- **Comando:** `python -m agent_server.main`
- **Porta:** 8002 (configuravel via `SUPEREZIO_PORT`)
- **Host:** 127.0.0.1
- **Arquivo:** `src/agent_server/main.py`
- **Protocolo:** A2A (Agent-to-Agent) via SSE + REST
- **Frontend:** `frontend/` servido como static files
- **Health:** `/health` (deep check: GPU, modelos, providers, cache)

### 2. CEO Local Server (llama.cpp)
- **Comando:** `.\scripts\serve_ceo_llamacpp.ps1`
- **Porta:** 8082
- **Modelo:** `models/qwen36-35b-f51.Q4_K_M.gguf`
- **Backend:** llama-server.exe (llama.cpp)
- **API:** OpenAI-compatible em `/v1`
- **GPU:** 20 camadas na RTX 5060 Ti 16GB
- **Speculative:** MTP draft (built-in)
- **Contexto:** 32768 tokens

### 3. Launcher (Desktop)
- **Arquivo:** `desktop/SuperEzio.bat`
- **Funcao:** Limpa portas 8002/8082, inicia CEO, inicia API, abre navegador

## Entrypoints Secundarios

### 4. Merge LoRA → GGUF
- **Comando:** `python scripts/merge_qwen36_lora.py --base Qwen/Qwen3.6-35B-A3B --adapter checkpoint-N --output merged-model`
- **Requisito:** 98GB+ VRAM (RTX PRO 6000 S)

### 5. Fine-tuning SFT
- **Qwen3.6:** `python scripts/finetune_qwen36_sft.py`
- **Rapido:** `python scripts/train_qwen36_3h.py`

### 6. Avaliacao
- **Pipeline:** `python scripts/eval_pipeline.py`
- **Benchmark:** `python scripts/financial_quality_benchmark.py`
- **Trick questions:** `python scripts/trick_questions_test.py`

### 7. Cloud (Vast.ai)
- **Setup:** `bash scripts/vastai_setup_qwen36.sh`
- **Merge:** `bash scripts/cloud_merge_and_quantize.sh`
- **NEXTN:** `bash scripts/cloud_nextn_pipeline.sh`

### 8. Testes
- **Todos:** `python -m pytest tests/ -q`
- **Smoke:** `python -m pytest tests/test_pipeline_smoke.py -q`
- **Componentes:** `python -m pytest tests/test_components_*.py -q`

## Entrypoints Deprecated

| Arquivo | Motivo |
|---------|--------|
| `scripts/finetune_glm_sft.py` | GLM-4.7 abandonado |
| `scripts/finetune_gemma_sft.py` | Gemma 4 abandonado |
| `scripts/vastai_setup_gemma.sh` | Gemma abandonado |
| `scripts/__pycache__/serve_ceo.cpython-312.pyc` | Cache orfa de serve_ceo.py removido |
