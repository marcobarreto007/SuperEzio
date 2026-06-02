# SuperEzio v4.0.0

**AI Financial Analysis Platform** — Plataforma de analise financeira com experts deterministicos, motor de veredito F51, CEO local Qwen3-Next-80B Abliterated (F51 Nitro MoE) e gateway FastAPI.

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
powershell -ExecutionPolicy Bypass -File scripts/serve_agent_llamacpp.ps1 -Port 8082
# → http://127.0.0.1:8082/v1 (OpenAI-compatible)

# 4. API Server
python -m agent_server.main
# → http://127.0.0.1:8002

# 5. Testar
python -m pytest tests/ -q
python -m ruff check src tests

# 6. Pre-delivery gate (recomendado antes de qualquer release)
pwsh -File scripts/verify_zero_garbage_runtime.ps1
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
├── scripts/                  # serve_agent_llamacpp.ps1, eval, dataset/runtime tools
├── frontend/                 # UI ChatGPT-style (HTML+CSS+JS inline)
└── pyproject.toml
```

### Fluxo de uma analise (pipeline v4 — grafo ativo)

```
Usuario → agent_server (FastAPI, :8002)
  → orchestrator_primary (intent + route)
  → data (ProfessionalCollector / market_scan via DataHub)
  → agent (Bob CEO ReAct — Qwen local :8082 ou gateway)
       ⇄ tool_executor (F51, experts, neural, RAG, PennyLab, market_scan, …)
  → explanation (streaming NDJSON) → END
```

Preço de mercado no scan: **DataHub** (Finnhub → Twelve Data → yfinance → Stooq). O nó legado `ceo.py` foi removido completamente; a resposta final passa pelo `agent`.

---

## Modelo CEO

**Qwen3-Next-80B-A3B Abliterated IQ4_XS GGUF** via llama.cpp `llama-server` + F51 Nitro MoE.

- 100% local, sem custo de API, sem censura (Abliterated — Arbitrary-Rank Ablation)
- MoE: 512 experts, 10 ativos + 1 compartilhado por token, ~59 MB por expert
- OpenAI-compatible em `http://127.0.0.1:8082/v1`
- Modelo esperado: `models/Huihui-Qwen3-Next-80B-A3B-Instruct-abliterated.IQ4_XS.gguf`
- n_ctx=262144 (256K), GPU layers=999 (max offload), --cpu-moe
- VRAM budget: ~6.3 GB, RAM budget: ~39 GB
- F51 Nitro Layers 1-4: Persistence Cache, Async PCIe Streams, Router Lookahead, KV Cache Tiering

Para subir o CEO server:
```bash
powershell -ExecutionPolicy Bypass -File scripts/serve_agent_llamacpp.ps1 -Port 8082
```

---

## Comandos

```bash
# CEO Server (modelo local)
powershell -ExecutionPolicy Bypass -File scripts/serve_agent_llamacpp.ps1 -Port 8082

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
| `FINNHUB_API_KEY` | Chave Finnhub para price/profile/short-term catalyst (opcional, fallback gracioso) |

`SUPEREZIO_DEEPSEEK_API_KEY` e `FINNHUB_API_KEY` sao opcionais. Sem elas o sistema continua funcional via providers locais/fallback; o CEO final permanece local-only.

> Hygiene: nunca commite `.env`. Use `.env.example` como template. O script `scripts/verify_zero_garbage_runtime.ps1` inclui um guard que bloqueia commits acidentais de chaves no padrao Finnhub.

---

## Estado Operacional

- `python -m pytest tests/contracts -q`: contratos passam (167+; veja `scripts/verify_zero_garbage_runtime.ps1` para o numero atual).
- `python -m pytest tests/test_runtime_smoke.py -q`: 20 passed.
- `python -m pytest tests/test_integration_runtime.py -q`: 7 passed quando CEO/API estao no ar.
- Gate runtime: `docs/runbooks/RUNBOOK.md`, `runtime/checkpoints/latest.json` e `DELIVERY.md` (handoff de release).
- Pre-delivery: `pwsh -File scripts/verify_zero_garbage_runtime.ps1` roda contratos, runtime, trace e secret-leak guard.

---

## Stack Tecnica

| Componente | Tecnologia |
|------------|------------|
| API Server | FastAPI + uvicorn + SSE |
| Pipeline | LangGraph 1.0.5 |
| Validacao | Pydantic v2 |
| CEO Model | Qwen3-Next-80B-A3B Abliterated IQ4_XS GGUF via llama.cpp + F51 Nitro MoE |
| Fine-tuning | PyTorch + PEFT/LoRA + transformers |
| Dados | yfinance, Reddit PRAW, httpx |
| Testes | pytest + pytest-asyncio + pytest-cov |
| Lint | ruff |

---

## Licenca

Proprietario — Fabria Labs.
