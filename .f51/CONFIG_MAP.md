# Config Map — SuperEzio

> Atualizado: 2026-05-17 | Branch: main

## Fonte de Verdade (Runtime Real)

### `.env` (raiz do projeto)
- **Status:** ATIVO — fonte real de configuracao
- **Prioridade:** OS env > .env.local > .env
- **Carregado por:** `src/core/config/secrets.py::load_local_env()`
- **Keys ativas:**
  - `SUPEREZIO_CEO_BASE_URL=http://127.0.0.1:8082/v1` (Qwen3.6-35B)
  - `SUPEREZIO_DEEPSEEK_MODEL=deepseek-v4-pro` (Cloud experts)
  - `SUPEREZIO_PROFESSIONAL_COLLECTOR=true`
  - 12+ API keys (Alpha Vantage, Twelve Data, NewsAPI, Wolfram, etc.)
  - `ANTHROPIC_*` vars para Claude Code via DeepSeek

## Config Files (Estaticos)

### `config/model_manifest.json`
- **Status:** STALE
- **Problema:** CEO configurado como Gemma-4-26B-A4B-abliterated
- **Realidade:** CEO e Qwen3.6-35B F51
- **Uso em runtime:** Nao confirmado — possivelmente nao lido

### `config/runtime.yml`
- **Status:** STALE
- **Problema:** So lista modelos cloud (DeepSeek). Nao tem CEO local Qwen3.6.
- **Uso em runtime:** `src/core/config/schema.py` define schema; `get_config()` pode ler

### `config/mandamentos.json`
- **Status:** ATIVO
- **Uso:** Regras operacionais injetadas no pipeline graph

### `pyproject.toml`
- **Status:** ATIVO (parcialmente stale)
- **Problema:** Descricao diz "CEO: Gemma-4-26B-A4B-abliterated"
- **Dependencias:** Corretas (torch, transformers, peft, llama-cpp-python, langgraph, etc.)

## Config em Codigo

### `src/core/config/schema.py`
- Schema Pydantic para `config/runtime.yml`
- Define ServerConfig, ModelConfig, GatewayConfig, TriadeConfig, StorageConfig

### `src/core/config/env.py`
- Re-exporta `load_env_once` de `secrets.py`
- Unico ponto de entrada para carregar .env

### `src/core/config/secrets.py`
- `load_local_env()` — carrega .env com prioridade
- `get_secret()` — busca secret com fallback

### `src/agent_server/main.py`
- `load_local_env()` chamado no startup
- PORT: `SUPEREZIO_PORT` ou `A2A_PORT` (legacy) ou 8002
- HOST: `SUPEREZIO_HOST` ou `A2A_BIND` (legacy) ou 127.0.0.1

## Config de Modelo

### `scripts/serve_ceo_llamacpp.ps1`
- **Parametros:** Port=8082, GpuLayers=20, ContextLength=32768, Slots=4
- **Modelo:** `models/qwen36-35b-f51.Q4_K_M.gguf`
- **Flags:** `--spec-type draft-mtp -fa on -ctk q8_0 -ctv q8_0 --mlock`

### `.env` (CEO)
- `SUPEREZIO_CEO_BASE_URL=http://127.0.0.1:8082/v1`
- `SUPEREZIO_CEO_TIMEOUT=180`
- `SUPEREZIO_CEO_QUANTIZE=nf4`
- `SUPEREZIO_CEO_MAX_TOKENS=16384`
- `SUPEREZIO_CEO_TEMPERATURE=0.3`

## Itens Stale — Acao Recomendada

1. `config/model_manifest.json` → Atualizar CEO para Qwen3.6-35B F51
2. `config/runtime.yml` → Adicionar secao `ceo_local` ou remover
3. `pyproject.toml` descricao → Trocar "Gemma-4-26B" por "Qwen3.6-35B"
