# F51 Entrypoint Map

Updated: 2026-08-21
Session: hybrid-qwen38-deepseek-v4

Version boundary: package/public API `4.0.0`; runtime configuration/model manifest `4.2.0`.

## Primary Entrypoints

### 1. API Server â€” `python -m agent_server.main`

| Property | Value |
|----------|-------|
| Classification | app |
| File | `src/agent_server/main.py` |
| Host | `127.0.0.1:8002` |
| Framework | FastAPI + uvicorn |
| Config | `config/runtime.yml` + `.env` |
| Dependencies | Shared local Qwen3.8-27B endpoint on `:8080`; required DeepSeek key for external experts; optional market-data credentials |
| Boot sequence | Load env -> load config -> create gateway -> build pipeline -> serve |

### 2. Shared llama.cpp Server â€” `powershell -ExecutionPolicy Bypass -File scripts/serve_agent_llamacpp.ps1 -Port 8080`

| Property | Value |
|----------|-------|
| Classification | app |
| File | `scripts/serve_agent_llamacpp.ps1` |
| Config | `config.ps1` |
| Host | `127.0.0.1:8080` |
| Model | `models/Qwen3.8-27B-UD-IQ2_XXS.gguf` or `SUPEREZIO_MODEL_PATH` |
| LoRA | None |
| Architecture | Qwen3.8-27B dense |
| GPU | All layers, RTX 3060 12 GB + RTX 2070 8 GB, tensor split `12,8` |
| Interface | OpenAI-compatible `/v1/chat/completions` |
| Context | 8192 tokens |
| Dependency | `llama-server.exe` resolved by `config.ps1` |
| Policy | Serves CEO and orchestrator only; never receives expert fallback traffic |

### 3. Windows Launcher â€” `setup_superezio.bat run` / `start.ps1`

| Property | Value |
|----------|-------|
| Classification | app |
| Files | `setup_superezio.bat`, `start.ps1`, `stop.ps1` |
| Purpose | Resolve portable paths, start CEO `:8080`, then API/UI `:8002`, and verify HTTP health |
| Policy | Single lifecycle owner; legacy restart/watchdog wrappers are retired |

### 4. Quality Probe â€” `python scripts/quality_probe.py`

| Property | Value |
|----------|-------|
| Classification | test |
| File | `scripts/quality_probe.py` |
| Purpose | Validate live response transport, content, latency and quality invariants |
| Dependency | Isolated live runtime on `:8080`/`:8002` |

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
  -> orchestrator_primary (passthrough; opens case and cognitive tool contract)
    -> auto_full_analysis
      -> trinity
        -> agent (Bob decides and may call tools)
          <-> tool_executor
          -> auto_execute_paper (guarded paper-only path)
            -> explanation -> END
        -> respond_blocked -> END
```

## Docker Entrypoints

| Target | Base | CMD | Classification |
|--------|------|-----|----------------|
| `cpu` | python:3.12-slim | `python -m agent_server.main` | config |
| `gpu` | nvidia/cuda:12.4-runtime-ubuntu22.04 | `python -m agent_server.main` | config |
