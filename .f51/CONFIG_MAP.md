# Config Map — SuperEzio

> Atualizado: 2026-05-19 | Branch: main | Session: f51-inventory-full-scan

---

## Fonte de Verdade (Runtime Real)

### `.env` (raiz) — ATIVO
- **Status:** ATIVO — fonte real de configuração
- **Prioridade:** OS env > .env.local > .env
- **Carregado por:** `src/core/config/secrets.py::load_local_env()`
- **Keys ativas:**
  - `SUPEREZIO_CEO_BASE_URL=http://127.0.0.1:8082/v1` (Qwen3.6-35B)
  - `SUPEREZIO_DEEPSEEK_MODEL=deepseek-v4-pro` (Cloud experts)
  - `SUPEREZIO_PROFESSIONAL_COLLECTOR=true`
  - 12+ API keys (Alpha Vantage, Twelve Data, NewsAPI, Wolfram, etc.)
  - `ANTHROPIC_*` vars para Claude Code via DeepSeek
- **Segurança:** `.env` no `.gitignore`. `.env.example` não tem secrets.
- **Risco:** 12+ API keys em plaintext no disco (R7).

---

## Config Estáticos

### `config/runtime.yml` — STALE
- **Problema:** Só lista modelos cloud (DeepSeek). Não tem CEO local Qwen3.6.
- **Uso em runtime:** `src/core/config/schema.py` define schema; `get_config()` pode ler.

### `config/model_manifest.json` — STALE
- **Problema:** CEO configurado como Gemma-4-26B-A4B-abliterated.
- **Realidade:** CEO é Qwen3.6-35B F51.
- **Uso em runtime:** Não confirmado — possivelmente não lido.

### `config/mandamentos.json` — ATIVO
- **Uso:** Regras operacionais injetadas no pipeline graph.

---

## Config de Build e Tooling

| Arquivo | Status | Função |
|---------|--------|--------|
| `pyproject.toml` | ATIVO (parcialmente stale) | Package metadata v4.0.0, dependencies, ruff config. Descrição menciona Gemma. |
| `pytest.ini` | ATIVO | min 8.0, testpaths=tests, asyncio auto, maxfail=5 |
| `Makefile` | ATIVO | Targets: install-deps, test, test-windows, verify |
| `Dockerfile` | ATIVO | Multi-stage: deps → CPU runtime → GPU runtime. Entry: `python -m agent_server.main` :8002 |
| `requirements-ci.txt` | ATIVO | Pinned CI deps para GitHub Actions |
| `.pre-commit-config.yaml` | ATIVO | ruff lint+format, mypy, check-json/toml/yaml |
| `.gitignore` | ATIVO | Python, .venv, models/, .env, data/traces, output, scratch |
| `.dockerignore` | ATIVO | Exclui .venv, models, data, .env, .claude |

---

## Config de Modelo

### `scripts/serve_ceo_llamacpp.ps1` — ATIVO
- Port=8082, GpuLayers=20, ContextLength=32768, Slots=4
- Modelo: `models/qwen36-35b-f51.Q4_K_M.gguf`
- Flags: `--spec-type draft-mtp -fa on -ctk q8_0 -ctv q8_0 --mlock`

### `.env` (CEO config)
- `SUPEREZIO_CEO_BASE_URL`, `SUPEREZIO_CEO_TIMEOUT=180`
- `SUPEREZIO_CEO_MAX_TOKENS=16384`, `SUPEREZIO_CEO_TEMPERATURE=0.3`

---

## Config de Treinamento

| Arquivo | Status | Função |
|---------|--------|--------|
| `scripts/finetune_glm_config.yaml` | ATIVO | QLoRA SFT config para GLM-4.7-Flash |

---

## Config em Código

| Arquivo | Função |
|---------|--------|
| `src/core/config/schema.py` | Schema Pydantic para runtime.yml (ServerConfig, ModelConfig, GatewayConfig) |
| `src/core/config/env.py` | Re-exporta `load_env_once` de `secrets.py` |
| `src/core/config/secrets.py` | `load_local_env()`, `get_secret()` |
| `src/agent_server/main.py` | `load_local_env()` no startup, PORT/HOST from env |

---

## Domain Data Config

| Arquivo | Função |
|---------|--------|
| `data/fraud_patterns/fraud_patterns.json` | 9 padrões de fraude com red flags |
| `data/fraud_patterns/red_flag_rules.json` | 11 regras de detecção |
| `data/macro_dataset/dataset_index.json` | 4 séries macro canadenses |
| `data/memory/default_mem0.json` | Memória persistente (vazio) |

---

## CI/CD

| Arquivo | Função |
|---------|--------|
| `.github/workflows/ci.yml` | GitHub Actions — Windows 2022, Python 3.12, ruff + pytest |

---

## IDE e Dev Tools

| Arquivo | Função |
|---------|--------|
| `.vscode/settings.json` | VS Code settings — Claude Code, git options |
| `.vscode/extensions.json` | Recomenda `anthropic.claude-code` |

---

## Claude Code / MCP

| Arquivo | Função |
|---------|--------|
| `.claude/settings.local.json` | Permissões: allow python, pennylab CLI |
| `.claude/mcp-catalog.json` | Catálogo de MCPs disponíveis (referência) |
| `.claude/partner/handoff.json` | Protocolo dual-agent (Bob/Sasaki) |

---

## Itens Stale — Ação Recomendada

| Arquivo | Problema | Ação |
|---------|----------|------|
| `config/model_manifest.json` | CEO = Gemma | Atualizar para Qwen3.6-35B F51 |
| `config/runtime.yml` | Sem CEO local | Adicionar seção `ceo_local` |
| `pyproject.toml` descrição | Diz "Gemma-4-26B" | Trocar para "Qwen3.6-35B" |

---

## Stale Training Artifacts (.f51/tmp/)

13 arquivos de Nemotron-12B (modelo abandonado):
- `treino_status.json`, `treino_phase1_status.json`
- `phase1-adapter/` (adapter config + tokenizer)
- `superezio-merged/` (merged model config)
- `mamba-ssm-src/`, `causal-conv1d-src/` (vendor source)

**Ação:** Manter como histórico ou limpar quando conveniente. Não é bloqueador.
