# SuperEzio v4.0.0

**AI Financial Analysis Platform** — Plataforma de analise financeira com experts deterministicos, motor de veredito F51, CEO local Qwen3.6-35B CEO+Intent Merged e gateway FastAPI.

---

## Quickstart

```bash
# 1. Ambiente
python -m venv .venv
.venv\Scripts\pip install -e .

# 2. Configurar
cp .env.example .env
# Para modo local-only, deixe chaves cloud vazias.

# 3. CEO Server (modelo local)
powershell -ExecutionPolicy Bypass -File scripts/serve_ceo_llamacpp.ps1 -Port 8082
# → http://127.0.0.1:8082/v1 (OpenAI-compatible)

# 4. API Server
python -m agent_server.main
# → http://127.0.0.1:8002

# 5. Testar
python -m pytest tests/ -q
python -m ruff check src tests
```

---

## Arquitetura

```
superezio/
├── src/
│   ├── core/
│   │   ├── pipeline/         # Pipeline v4 (LangGraph, nodes puros, model-agnostic)
│   │   ├── model_serving/    # ModelGateway: local_orchestrator + ceo + deepseek experts
│   │   ├── rag/              # ForensicRAG engine
│   │   ├── config/           # UniversalConfig + secrets
│   │   ├── data_collector/   # ProfessionalCollector multi-fonte
│   │   ├── math/             # Fonte unica: formulas canonicas
│   │   ├── investor/         # Family Investor Committee
│   │   ├── observability/    # Logs, metricas, event hub
│   │   └── paths.py
│   ├── experts/
│   │   ├── pennylab/         # 4 experts: whale, pump, trap, liquidity (escala 0-1)
│   │   └── crisis/           # 12 modelos de crise financeira
│   ├── f51/                  # Verdict engine (grafo + formulas + memoria)
│   ├── agent_server/         # FastAPI endpoints + SSE streaming
│   ├── data/                 # Providers: yfinance, Reddit, Alpha Vantage, BOC...
│   └── tools/                # Registry de tools para LangGraph
├── tests/                    # smoke, contract, integration
├── scripts/                  # serve_ceo_llamacpp.ps1, eval, dataset/runtime tools
├── frontend/                 # UI ChatGPT-style (HTML+CSS+JS inline)
└── pyproject.toml
```

### Fluxo de uma analise

```
Usuario → agent_server (FastAPI)
  → Orchestrator (intent parse + route)
  → Collector (yfinance + Reddit + News + BOC + ...)
  → Experts fan-out (PennyLab + CrisisMath + Quantum)
  → F51 Engine (grafo → veredito deterministico)
  → RAG Forensics (contexto historico)
  → CEO Qwen3.6-35B CEO+Intent Merged (consolida conflitos, output final)
  → Explanation (NDJSON streaming)
```

---

## Modelo CEO

**SuperEzio CEO+Intent Merged Qwen3.6-35B-A3B Q4_K_M GGUF** via llama.cpp `llama-server`.

- 100% local, sem custo de API, sem censura
- OpenAI-compatible em `http://127.0.0.1:8082/v1`
- Modelo esperado: `models/superezio-ceo-intent-merged.Q4_K_M.gguf`
- n_ctx=8192, GPU layers configuraveis no script PowerShell

Para subir o CEO server:
```bash
powershell -ExecutionPolicy Bypass -File scripts/serve_ceo_llamacpp.ps1 -Port 8082
```

---

## Comandos

```bash
# CEO Server (modelo local)
powershell -ExecutionPolicy Bypass -File scripts/serve_ceo_llamacpp.ps1 -Port 8082

# API Server
python -m agent_server.main

# Testes
python -m pytest tests/ -q

# Lint
python -m ruff check src tests
python -m ruff format --check src tests
```

---

## Variaveis de Ambiente

Todas documentadas em [`.env.example`](.env.example). Minimo para modo local-only:

| Variavel | Descricao |
|----------|-----------|
| `SUPEREZIO_CEO_BASE_URL` | Endpoint OpenAI-compatible do CEO local |
| `SUPEREZIO_HOST` | Bind address (default: 127.0.0.1) |
| `SUPEREZIO_PORT` | Porta (default: 8002) |
| `SUPEREZIO_DEEPSEEK_API_KEY` | Chave para experts cloud (opcional) |

`SUPEREZIO_DEEPSEEK_API_KEY` e opcional e so habilita providers externos para experts/orquestracao; o CEO final permanece local-only.

---

## Estado Operacional

- `python -m pytest tests/contracts -q`: 167 passed, 2 warnings.
- `python -m pytest tests/test_runtime_smoke.py -q`: 20 passed.
- `python -m pytest tests/test_integration_runtime.py -q`: 7 passed when CEO/API are live.
- Gate runtime: `docs/runbooks/RUNBOOK.md` and `runtime/checkpoints/latest.json`.

---

## Stack Tecnica

| Componente | Tecnologia |
|------------|------------|
| API Server | FastAPI + uvicorn + SSE |
| Pipeline | LangGraph 1.0.5 |
| Validacao | Pydantic v2 |
| CEO Model | SuperEzio CEO+Intent Merged Qwen3.6-35B-A3B GGUF via llama.cpp |
| Fine-tuning | PyTorch + PEFT/LoRA + transformers |
| Dados | yfinance, Reddit PRAW, httpx |
| Testes | pytest + pytest-asyncio + pytest-cov |
| Lint | ruff |

---

## Licenca

Proprietario — Fabria Labs.
