# Runtime Contract — SuperEzio v4.0.0

**Session:** f51-contracts-runtime-tests-2026-05-21
**Status:** CANONICAL

## Scope

This contract defines the official runtime surface of SuperEzio. It references and
incorporates the detailed module contracts but does not duplicate them.

## Canonical References

| Contract | File | Scope |
| --- | --- | --- |
| Agent Server | `.f51/contracts/agent-server.contract.md` | FastAPI routes, A2A protocol, frontend serving |
| Pipeline | `.f51/contracts/pipeline.contract.md` | 10-node LangGraph topology, PipelineState, node contracts |
| CEO | `.f51/contracts/ceo.contract.md` | CEO prompt builder, module coverage, advisor boundary |
| F51 Engine | `.f51/contracts/f51-engine.contract.md` | F51 scoring, veracity gate, consensus, uncertainty |
| DataHub | `.f51/contracts/data-hub.contract.md` | Data collection, provider mesh, price/profile queries |
| Neural Decision | `.f51/contracts/neural-decision.contract.md` | Feature extraction, directional probability, regime |
| A2A Protocol | `.f51/contracts/a2a-protocol.contract.md` | Message types, TASK.SUBMIT envelope |
| Blood Pact | `.f51/contracts/f51-blood-pact-operational-runtime.json` | Operational gates, Marco↔Deep responsibilities |

## Runtime Processes

| Component | Command | Port | Health URL |
| --- | --- | --- | --- |
| CEO (llama.cpp) | `scripts/serve_ceo_llamacpp.ps1 -Port 8082` | 8082 | `http://127.0.0.1:8082/health` |
| API (FastAPI) | `python -m agent_server.main` | 8002 | `http://127.0.0.1:8002/health` |

## Configuration

- **Canonical:** `config/runtime.yml` (UniversalConfig schema)
- **Secrets:** `.env` / `.env.local` (never committed)
- **Template:** `.env.example`
- **Test config:** `pytest.ini`

## Health Check Layers

1. CEO server `:8082/health` — HTTP 200, `{"status":"ok"}`
2. API public `:8002/health` — HTTP 200, `{"status":"ok","agent":"superezio","version":"3.0.0"}`
3. API deep `:8002/health/details` — GPU, models, Redis, providers, cost guard
4. DataHub `check_health()` — provider key availability

## Checkpoints

- `.f51/checkpoints/latest.json` — session-level operational checkpoint
- `runtime/checkpoints/latest.json` — runtime parameter checkpoint

## Minimum Verification

```powershell
python -m pytest tests/contracts -q           # All contracts
python -m pytest tests/test_runtime_smoke.py -q  # Runtime smoke
python -m pytest tests/test_pipeline_smoke.py -q # Pipeline smoke
python -m pytest tests/test_integration_runtime.py -q  # Live integration
```

## Non-Negotiables

1. GitHub is BLOCKED — disk-only per `.f51/GITHUB_POLICY.json`
2. No feature before inventory, contracts, runtime, tests
3. No mock for critical integration — only for unit isolation
4. Every task updates TASK_BOARD, RISK_REGISTER, and checkpoint
