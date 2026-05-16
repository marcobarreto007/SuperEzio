# SuperEzio v4.0.0

**AI Financial Analysis Platform** — Plataforma de analise financeira com experts deterministicos, motor de veredito F51, CEO local Gemma-4-26B e gateway FastAPI.

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
python scripts/server.py --model C:\Users\marco\models\gemma-4-26b-abliterated-Q4_K_M.gguf
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
│   │   ├── model_serving/    # ModelGateway multi-provider (cascade: ceo → deepseek)
│   │   ├── rag/              # ForensicRAG engine
│   │   ├── config/           # UniversalConfig + secrets
│   │   ├── data_collector/   # ProfessionalCollector multi-fonte
│   │   ├── mathcore/         # Fonte unica: formulas canonicas
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
├── tests/                    # 344 testes deterministicos
├── scripts/                  # server.py (llama-cpp CEO), eval, benchmark
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
  → CEO Gemma-4-26B (consolida conflitos, output final)
  → Explanation (NDJSON streaming)
```

---

## Modelo CEO

**Gemma-4-26B-A4B-abliterated Q4_K_M GGUF** (~16.8 GB) via llama-cpp-python.

- 100% local, sem custo de API, sem censura
- OpenAI-compatible em `http://127.0.0.1:8082/v1`
- Requer GGUF baixado de huggingface.co (bartowski/gemma-4-26b-abliterated-GGUF)
- n_ctx=8192, n_gpu_layers configurável via env

Para subir o CEO server:
```bash
python scripts/server.py --model <caminho-do-gguf>
```

---

## Comandos

```bash
# CEO Server (modelo local)
python scripts/server.py

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

- `python -m pytest tests/ -q`: 344 passed, 2 failed (timeout flaky).
- `python -m ruff check src tests`: clean (exceto E402 pre-existente em main.py).
- Gate E2E: `.f51/RELEASE_READINESS.md`.

---

## Stack Tecnica

| Componente | Tecnologia |
|------------|------------|
| API Server | FastAPI + uvicorn + SSE |
| Pipeline | LangGraph 1.0.5 |
| Validacao | Pydantic v2 |
| CEO Model | Gemma-4-26B GGUF via llama-cpp-python |
| Fine-tuning | PyTorch + PEFT/LoRA + transformers |
| Dados | yfinance, Reddit PRAW, httpx |
| Testes | pytest + pytest-asyncio + pytest-cov |
| Lint | ruff |

---

## Licenca

Proprietario — Fabria Labs.
