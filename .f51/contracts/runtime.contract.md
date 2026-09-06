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
| Product launcher | `setup_superezio.bat run` -> `start.ps1` | 8002 | `http://127.0.0.1:8002/health` |
| API (FastAPI) | `python -m agent_server.main` | 8002 | `http://127.0.0.1:8002/health` |

The production runtime uses official DeepSeek HTTPS APIs (`https://api.deepseek.com`):
`deepseek-v4-pro` for Bob CEO and orchestrator, and `deepseek-v4-flash` for financial
experts, judge, and auditor. No local inference server or GPU is required.
`SUPEREZIO_DEEPSEEK_API_KEY` is supplied through ignored local configuration or the
process environment. No cross-provider fallback is permitted.

`start.ps1` accepts `-SkipBrowser`, `-IsolatedValidation`, and
`-HealthTimeoutMinutes` (default 6). It refuses occupied API ports. Isolated
validation separates storage and freezes execution. Launch success proves API
liveness only. `stop.ps1` terminates only the PID and start time recorded in
`runtime/api-process.json`; it refuses reused PIDs and leaves other launchers alone.

## Configuration

- **Canonical model/runtime:** `config/runtime.yml` and `config/model_manifest.json`
- **Canonical Windows process composition:** `config.ps1`, `start.ps1`, `stop.ps1`
- **Secrets:** `.env` / `.env.local` (never committed)
- **Template:** `.env.example`
- **Test config:** `pytest.ini`

## Health Check Layers

1. API public `:8002/health` — HTTP 200, `{"status":"ok","agent":"superezio","version":"4.0.0"}`
2. API deep `:8002/health/details` — provider readiness; 503 when required cloud providers are not ready
3. DataHub `check_health()` — provider key availability

A successful provider configuration check does not substitute for a successful
real assistant request. Market coverage and data freshness remain separate gates.

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
