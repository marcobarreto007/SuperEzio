# SuperEzio v3.2.0

**AI Financial Analysis Platform** — Plataforma de analise financeira com experts deterministicos, motor de veredito F51 e gateway FastAPI.

---

## Quickstart

```bash
# 1. Ambiente
python -m venv .venv
.venv\Scripts\pip install -e .

# 2. Configurar
cp .env.example .env
# Para modo local-only, deixe chaves cloud vazias.

# 3. Rodar
python -m agent_server.main                # API FastAPI
# → http://127.0.0.1:8002

# 4. Testar
python -m pytest tests/ -q
python -m ruff check src tests
```

---

## Arquitetura

```
superezio/
├── src/
│   ├── core/               ← Dominio (19 modulos)
│   │   ├── mathcore/        # Fonte unica: formulas canonicas
│   │   ├── data_collector/  # Coleta de dados multi-fonte
│   │   ├── investor/        # Family Investor Committee
│   │   ├── model_serving/   # Gateway OpenAI-compatible
│   │   ├── f51_adapter/     # Ponte F51 ↔ dados reais
│   │   ├── observability/   # Logs, metricas, event hub
│   │   └── ...
│   ├── experts/
│   │   ├── pennylab/        # 4 experts: whale, pump, trap, liquidity (escala 0-1)
│   │   ├── crisis/          # 12 modelos de crise financeira (BIS, Shiller, Minsky...)
│   │   └── quantum_expert.py
│   ├── f51/                 # Verdict engine (grafo + formulas + memoria)
│   ├── agent_server/        # FastAPI + A2A protocol
│   ├── data/                # Providers: yfinance, Reddit, Alpha Vantage, BOC...
│   └── tools/               # Registry de tools para LangGraph
├── tests/                   # 496 testes deterministicos
├── data/                    # cache, fraud_patterns, memory, traces
├── scripts/                 # eval, benchmark, finetune
├── desktop/                 # Launcher Windows (SuperEzio.bat)
├── docs/internal/audits/    # Relatorios internos de auditoria e benchmark
└── pyproject.toml
```

### Fluxo de uma analise

```
Usuario → agent_server (FastAPI)
  → DataCollector (yfinance + Reddit + News + BOC + ...)
  → Experts (Pennylab + CrisisMath + Quantum)
  → F51 Engine (grafo → veredito deterministico)
  → InvestorCommittee (7 agentes com guardrails)
  → ModelGateway (modelo em transicao)
       → OutputGuardian → Usuario
```

---

## Modelo

O stack de servidor CEO legado (`scripts/serve_ceo.py`) foi removido para migração de modelo.
Use `python -m agent_server.main` como entrada principal enquanto o novo runtime é integrado.

---

## Comandos

```bash
# Servidor
python -m agent_server.main

# Merge QLoRA adapters
python .f51/tmp/merge_adapters.py \
    --adapter1 C:\Users\marco\Desktop\nemotron-adapter \
    --adapter2 .f51/tmp/phase1-adapter \
    --output .f51/tmp/superezio-merged

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
| `SUPEREZIO_CEO_BASE_URL` | Endpoint OpenAI-compatible do modelo ativo |
| `SUPEREZIO_HOST` | Bind address (default: 127.0.0.1) |
| `SUPEREZIO_PORT` | Porta (default: 8002) |
| `SUPEREZIO_EDGE_AUTH` | Gateway auth (default ligado) |
| `SUPEREZIO_EDGE_SECRET` | Secret JWT/API gateway quando auth esta ligado |

`SUPEREZIO_DEEPSEEK_API_KEY` e opcional e so habilita providers externos para experts/orquestracao; o veredito CEO final permanece local-only.

Para desenvolvimento local, `.env.example` usa `SUPEREZIO_EDGE_AUTH=0` para o servidor subir sem secret. Em producao, use `SUPEREZIO_EDGE_AUTH=1` e configure `SUPEREZIO_EDGE_SECRET` ou `SUPEREZIO_API_KEYS`.

`/health` e publico e minimal. `/health/details`, `/metrics`, `/capabilities`, `/product/manifest`, `/api/chart-data/*` e `/neural/logs` seguem ativos no servidor principal.

## Estado Operacional

- `python -m pytest tests/ -q`: 496 passed, 0 failed, 2 warnings.
- `python -m ruff check src tests`: passed.
- `pyright`: nao instalado neste ambiente.
- Gate E2E de entrega: `docs/internal/audits/e2e_delivery_2026-05-13.md`.

---

## Stack Tecnica

| Componente | Tecnologia |
|------------|------------|
| API Server | FastAPI + uvicorn |
| Pipeline | LangGraph 1.0.5 |
| Validacao | Pydantic v2 |
| Modelos | PyTorch + PEFT/LoRA + transformers |
| Dados | yfinance, Reddit PRAW, httpx |
| Testes | pytest + pytest-asyncio + pytest-cov |
| Lint | ruff |

---

## Licenca

Proprietario — Fabria Labs.
