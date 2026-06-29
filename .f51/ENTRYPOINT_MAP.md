# F51 Entrypoint Map

Updated: 2026-06-28T23:59:00-04:00
Session: bob-core-lora

## Primary Entrypoints

### 1. API Server â€” `python -m agent_server.main`

| Property | Value |
|----------|-------|
| Classification | app |
| File | `src/agent_server/main.py` (368 lines) |
| Host | `127.0.0.1:8002` |
| Framework | FastAPI + uvicorn |
| Config | `config/runtime.yml` + `.env` |
| Dependencies | CEO model on :8082, `.env` with provider keys |
| Boot sequence | Load env -> load config -> create gateway -> build pipeline -> serve |

### 2. CEO llama.cpp Server â€” `powershell -ExecutionPolicy Bypass -File scripts/serve_agent_llamacpp.ps1 -Port 8082`

| Property | Value |
|----------|-------|
| Classification | app |
| File | `scripts/serve_agent_llamacpp.ps1` |
| Config | `config.ps1` |
| Host | `127.0.0.1:8082` |
| Model | `C:\llama.cpp\models\Bob Core-q4_k.gguf` (17.3 GB) |
| LoRA | `C:\\llama.cpp\\models\\bob-lora-best.gguf` (42 MB) |
| Architecture | qwen3moe (128 experts, 8 active, 48 layers) |
| GPU | 49/49 layers on VRAM (RTX 5060 Ti 16GB) |
| Interface | OpenAI-compatible `/v1/chat/completions` |
| Context | 65536 tokens (64K) |
| Dependency | llama.cpp binary in `C:\llama.cpp\build\bin\` |

### 3. Desktop Launcher â€” RETIRED

The `desktop/SuperEzio.bat` launcher has been retired. Start services directly:
- CEO: `powershell -ExecutionPolicy Bypass -File scripts/serve_agent_llamacpp.ps1 -Port 8082`
- API: `python -m agent_server.main`

### 4. Eval Pipeline â€” `python scripts/eval_pipeline.py`

| Property | Value |
|----------|-------|
| Classification | test |
| File | `scripts/eval_pipeline.py` |
| Purpose | Evaluate CEO model intent classification |
| Data | `data/eval_questions.jsonl`, `data/intent_golden.jsonl` |

## API Endpoints (FastAPI)

| Route | Method | Purpose | Classification |
|-------|--------|---------|----------------|
| `/` | GET | Frontend SPA | app |
| `/health` | GET,HEAD | Liveness probe | app |
| `/health/details` | GET | Deep health (GPU, models, Redis) | app |
| `/metrics` | GET | Operational metrics | app |
| `/neural/logs` | GET | Neural decision log stream | app |
| `/task/submit` | POST | Main pipeline entry (NDJSON streaming) | pipeline |
| `/api/chart-data/{ticker}` | GET | OHLCV + indicators | app |
| `/api/chart-sse/{ticker}` | GET | Real-time SSE candle stream | app |
| `/capabilities` | GET | Product capabilities | app |
| `/product/manifest` | GET | Product contract for UI | app |
| `/api/sdca/evaluate` | POST | SDCA risk evaluation | core |
| `/experts/neural-decision/predict` | POST | Neural prediction | core |

## Pipeline Graph Topology

```
START
  -> orchestrator_primary (3-layer intent: regex -> golden -> CEO LLM)
    -> agent (ReAct loop, "Bob", max 7 iterations)
      <-> tool_executor (maps tool calls to pipeline nodes)
        -> collector / experts / f51 / pennylab / neural_decision / sdca / rag / market_scan
    -> explanation (streaming interpretability)
      -> END
    -> respond_blocked (SDCA block)
      -> END
```

## Docker Entrypoints

| Target | Base | CMD | Classification |
|--------|------|-----|----------------|
| `cpu` | python:3.12-slim | `python -m agent_server.main` | config |
| `gpu` | nvidia/cuda:12.4-runtime-ubuntu22.04 | `python -m agent_server.main` | config |


