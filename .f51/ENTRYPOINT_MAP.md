# Entrypoint Map — SuperEzio

> Atualizado: 2026-05-19 | Branch: main | Session: f51-inventory-full-scan

---

## Entrypoints Principais

### 1. Agent Server (FastAPI) — CORE
- **Comando:** `python -m agent_server.main`
- **Porta:** 8002 (configurável via `SUPEREZIO_PORT`)
- **Host:** 127.0.0.1
- **Arquivo:** `src/agent_server/main.py`
- **Protocolo:** A2A (Agent-to-Agent) via SSE + REST
- **Frontend:** `frontend/` servido como static files
- **Health:** `/health` (deep check: GPU, modelos, providers, cache)

### 2. CEO Local Server (llama.cpp) — CORE
- **Comando:** `.\scripts\serve_ceo_llamacpp.ps1`
- **Porta:** 8082
- **Modelo:** `models/superezio-ceo-intent-merged.Q4_K_M.gguf`
- **Backend:** llama-server.exe (llama.cpp)
- **API:** OpenAI-compatible em `/v1`
- **GPU:** 28 camadas na RTX 5060 Ti 16GB
- **Speculative:** desabilitado (nextn patched 1→0)
- **Contexto:** 8192 tokens
- **Thinking:** auto (habilitado)

### 3. Launcher (Desktop) — APP
- **Arquivo:** `desktop/SuperEzio.bat`
- **Função:** Limpa portas 8002/8082, inicia CEO, inicia API, abre navegador

### 4. PennyLab CLI — APP
- **Comando:** `python -m experts.pennylab.cli`
- **Subcomandos:** `ticker`, `scan`, `log`, `postmortem`
- **Arquivo:** `src/experts/pennylab/cli.py`

---

## Scripts de Treinamento — EXPERIMENTAL

| Script | Alvo | Status |
|--------|------|--------|
| `scripts/finetune_qwen36_sft.py` | Qwen3.6-35B LoRA/QLoRA SFT | ATIVO |
| `scripts/train_qwen36_3h.py` | Qwen3.6 3h timebox + self-heal | ATIVO |
| `scripts/merge_qwen36_lora.py` | Merge LoRA adapters into base | ATIVO |
| `scripts/run_merge_patched.py` | Merge com monkey-patch PEFT | ATIVO |
| `scripts/finetune_glm_sft.py` | GLM-4.7-Flash QLoRA | ATIVO (alternativa) |
| `scripts/finetune_gemma_sft.py` | Gemma-4-26B QLoRA | DEPRECATED |

---

## Scripts de Avaliação — TEST

| Script | Função | Requer |
|--------|--------|--------|
| `scripts/eval_pipeline.py` | E2E eval com GLM proxy judge | Servidor + GLM proxy :8899 |
| `scripts/financial_quality_benchmark.py` | 50Q benchmark financeiro | Servidor :8002 |
| `scripts/trick_questions_test.py` | 20 trick questions | Servidor :8002 |
| `scripts/investment_test.py` | 3 cenários de investimento | Servidor :8002 |

---

## Scripts de Dados — PIPELINE

| Script | Função |
|--------|--------|
| `scripts/generate_intent_dataset.py` | Gera dataset de intenção (600 exemplos) |
| `scripts/build_hf_intent_dataset.py` | Build dataset de HuggingFace |
| `scripts/generate_system_knowledge_sft.py` | SFT de conhecimento do sistema |
| `scripts/sftp_download_chunks.py` | Download GGUF via SFTP (single-use) |

---

## Dataset Pipeline — EXPERIMENTAL

| Script | Função |
|--------|--------|
| `F51_Datasets/download_hf_datasets.py` | Download datasets HuggingFace |
| `F51_Datasets/explore_datasets.py` | Explora estrutura dos datasets |
| `F51_Datasets/convert_to_sft.py` | Conversão para JSONL SFT |
| `F51_Datasets/score_and_split.py` | Score + split 90/10 |
| `F51_Datasets/integrate_staged.py` | Integração de batches |
| `F51_Datasets/grok_transfusion.py` | Geração premium via Grok (multi-domain) |
| `F51_Datasets/grok_transfusion_python.py` | Geração premium via Grok (Python) |
| `F51_Datasets/prepare_final_dataset.py` | Merge final para GLM fine-tuning |

---

## Testes — TEST

| Comando | Escopo |
|---------|--------|
| `python -m pytest tests/ -q` | Suite completa (530+ testes) |
| `python -m pytest tests/test_pipeline_smoke.py -q` | Smoke do pipeline |
| `python -m pytest tests/test_components_*.py -q` | Testes por componente |
| `python -m pytest tests/contracts/ -q` | Testes de contrato (~150) |

---

## Entrypoints Deprecated

| Arquivo | Motivo |
|---------|--------|
| `archive/experimental/training/finetune_qwen36.py` | Superseded by `finetune_qwen36_sft.py` |
| `archive/experimental/training/finetune_phase1.py` | Treinamento Nemotron (modelo abandonado) |
| `archive/experimental/training/test_adapter.py` | Teste de adapter Nemotron |
| `scripts/sftp_download_chunks.py` | Single-use, credenciais hardcoded |

---

## Cloud (Vast.ai)

| Script | Função |
|--------|--------|
| `scripts/vastai_setup_qwen36.sh` | Setup GPU cloud |
| `scripts/cloud_merge_and_quantize.sh` | Merge + quantize na cloud |
| `scripts/cloud_nextn_pipeline.sh` | Pipeline NEXTN na cloud |

---

## Diagnostic Helpers

| Arquivo | Função |
|---------|--------|
| `src/data/data_hub.py` (`__main__`) | Printa rotas ativas do DataHub |
| `scratch/check_scan.py` | Teste ad-hoc de intent scanning |
| `scratch/test_fax.py` | Teste ad-hoc de envio ao API |
| `scratch/test_neural_expert.py` | Teste ad-hoc de neural expert |
