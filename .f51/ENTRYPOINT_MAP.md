# F51 Entrypoint Map

Updated: 2026-05-21T20:30:00-04:00
Session: f51-inventory-full-sweep

## Primary Entrypoints

### 1. API Server — `python -m agent_server.main`

| Property | Value |
|----------|-------|
| Classification | app |
| File | `src/agent_server/main.py` (368 lines) |
| Host | `127.0.0.1:8002` |
| Framework | FastAPI + uvicorn |
| Config | `config/runtime.yml` + `.env` |
| Dependencies | CEO model on :8082, `.env` with provider keys |
| Boot sequence | Load env -> load config -> create gateway -> build pipeline -> serve |

### 2. CEO llama.cpp Server — `scripts/serve_agent_llamacpp.ps1 -Port 8082`

| Property | Value |
|----------|-------|
| Classification | app |
| File | `scripts/serve_agent_llamacpp.ps1` |
| Host | `127.0.0.1:8082` |
| Model | `models/Huihui-Qwen3-Next-80B-A3B-Instruct-abliterated.IQ4_XS.gguf` (~40 GB) |
| Architecture | MoE (512 experts, 10 active + 1 shared per token) |
| Interface | OpenAI-compatible `/v1/chat/completions` |
| Context | 262144 tokens (256K) |
| Nitro | Layers 1-4 active (Persistence Cache, Async Streams, Lookahead, KV Tiering) |
| Dependency | llama.cpp binary in `llama.cpp/` |

### 3. Desktop Launcher — RETIRED

The `desktop/SuperEzio.bat` launcher has been retired. Start services directly:
- CEO: `powershell -ExecutionPolicy Bypass -File scripts/serve_agent_llamacpp.ps1 -Port 8082`
- API: `python -m agent_server.main`

### 4. Eval Pipeline — `python scripts/eval_pipeline.py`

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
