# F51 Entrypoint Map — SuperEzio
Generated: 2026-05-15

## Production EntryPoints

| EntryPoint | File | Trigger | Description |
|---|---|---|---|
| Agent Server | `src/agent_server/main.py` | `python -m agent_server.main` | FastAPI server (uvicorn). A2A protocol + EdgeGateway. Env: `A2A_PORT` (default 8002), `A2A_BIND` (default 127.0.0.1) |

## Utility EntryPoints

| EntryPoint | File | Trigger | Description |
|---|---|---|---|
| PennyLab CLI | `src/experts/pennylab/cli.py` | `python -m experts.pennylab.cli` | CLI para analise penny stock |
| Data Hub | `src/data/data_hub.py` | `python src/data/data_hub.py` | Runner standalone do data hub |
| Subprocess Collector | `src/adapters/data_collector/subprocess_collector.py` | subprocess spawn | Coleta dados em subprocess isolado |

## Console Scripts (pyproject.toml)

**Nenhum definido.** Nao ha `[project.scripts]` no pyproject.toml.

## Comandos Registrados (CLAUDE.md)

```bash
python -m agent_server.main          # Servidor principal
python -m pytest tests/ -q           # 344 testes deterministicos
python -m ruff check src tests       # Lint
```

## Pipeline (Internal)

| EntryPoint | File | Description |
|---|---|---|
| `create_pipeline()` | `src/core/pipeline/runtime.py` | Factory que instancia `UniversalPipeline` |
| `UnifiedPipeline` | `src/core/pipeline/runtime.py` | Alias para `UniversalPipeline` |
| `UniversalPipeline` | `src/core/pipeline/runtime.py` | Classe principal com `chat()`, `chat_sync()`, `stream_events()` |

## Scripts

| Script | File | Status |
|---|---|---|
| `build_hf_intent_dataset.py` | `scripts/` | Utilidade de ML dataset |
| `finetune_glm_sft.py` | `scripts/` | Fine-tuning GLM |
| `eval_pipeline.py` | `scripts/` | Avaliacao de pipeline |
| `financial_quality_benchmark.py` | `scripts/` | Benchmark de qualidade financeira |
| `server.py` | `scripts/` | **Orfao** — nao referenciado |
