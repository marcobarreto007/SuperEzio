# Runtime Contract — SuperEzio v4.0.0

**Session:** product-delivery-v1-runtime-truth-2026-08-20
**Status:** CANONICAL

## Scope

This contract defines the official runtime surface of SuperEzio. It references and
incorporates the detailed module contracts but does not duplicate them.

## Canonical References

| Contract | File | Scope |
| --- | --- | --- |
| Agent Server | `.f51/contracts/agent-server.contract.md` | FastAPI routes, A2A protocol, frontend serving |
| Pipeline | `.f51/contracts/pipeline.contract.md` | LangGraph ReAct topology, PipelineState, node contracts |
| CEO | `.f51/contracts/ceo.contract.md` | CEO prompt builder, module coverage, advisor boundary |
| F51 Engine | `.f51/contracts/f51-engine.contract.md` | F51 scoring, veracity gate, consensus, uncertainty |
| DataHub | `.f51/contracts/data-hub.contract.md` | Data collection, provider mesh, price/profile queries |
| Neural Decision | `.f51/contracts/neural-decision.contract.md` | Feature extraction, directional probability, regime |
| A2A Protocol | `.f51/contracts/a2a-protocol.contract.md` | Message types, TASK.SUBMIT envelope |
| Blood Pact | `.f51/contracts/f51-blood-pact-operational-runtime.json` | Operational gates, Marco↔Deep responsibilities |

## Runtime Processes

| Component | Command | Port | Health URL |
| --- | --- | --- | --- |
| Product launcher | `setup_superezio.bat run` -> `start.ps1` | 8080 + 8002 | both URLs below |
| CEO (llama.cpp) | `scripts/serve_agent_llamacpp.ps1 -Port 8080` | 8080 | `http://127.0.0.1:8080/health` |
| API (FastAPI) | `python -m agent_server.main` | 8002 | `http://127.0.0.1:8002/health` |

The production runtime operates 100% on external cloud model APIs: Z.ai (`https://api.z.ai/api/coding/paas/v4`, `glm-5.3`)
for Bob CEO / orchestrator, and the official DeepSeek HTTPS API (`https://api.deepseek.com`, `deepseek-v4-pro`)
for financial experts, day-trade judge, and auditor.
The local llama.cpp server profile with `Ornith-1.0-9B-Q4_K_M` (~5.9GB) on `:8080` remains documented as a historical/standby reference.
No cross-provider fallback is permitted. API keys (`SUPEREZIO_DEEPSEEK_API_KEY`, `SUPEREZIO_GLM_CODING_PLAN_API_KEY`)
are external machine prerequisites stored only in `.env.local`.

## Configuration

- **Canonical model/runtime:** `config/runtime.yml` and `config/model_manifest.json`
- **Canonical Windows process composition:** `config.ps1`, `start.ps1`, `stop.ps1`
- **Secrets:** `.env` / `.env.local` (never committed)
- **Template:** `.env.example`
- **Test config:** `pytest.ini`

## Health Check Layers

1. CEO server `:8080/health` — HTTP 200
2. API public `:8002/health` — HTTP 200, `{"status":"ok","agent":"superezio","version":"4.0.0"}`
3. API deep `:8002/health/details` — GPU, models, Redis, providers, cost guard; 503 when the local CEO or external expert tier is not ready
4. DataHub `check_health()` — provider key availability

Liveness, readiness, market-data state and broker state are separate. An offline
broker does not make the local research product offline.

## Checkpoints

- `.f51/checkpoints/latest.json` — session-level operational checkpoint
- `runtime/checkpoints/latest.json` — runtime parameter checkpoint

## Minimum Verification

```powershell
python -m pytest tests/contracts -q           # All contracts
python -m pytest tests/test_runtime_smoke.py tests/test_integration_runtime.py -q
python -m ruff check src/ tests/
python scripts/browser_smoke.py
```

## Non-Negotiables

1. GitHub is BLOCKED — disk-only per `.f51/GITHUB_POLICY.json`
2. No feature before inventory, contracts, runtime, tests
3. No mock for critical integration — only for unit isolation
4. Every task updates TASK_BOARD, RISK_REGISTER, and checkpoint
5. V1 is research-only; no broker transport or real-capital authorization
6. Canonical surfaces must not refer to retired model/port/launcher contracts
