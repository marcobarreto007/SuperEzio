# Official Runbook - SuperEzio Runtime v4.2.0

Updated: 2026-09-12
Policy: DISK ONLY. GitHub is blocked by `.f51/GITHUB_POLICY.json`.
Model policy: external cloud APIs only, at the official DeepSeek HTTPS API.
Per-role split in effect since 2026-09-12: the deciding roles — Bob/CEO (`agent`)
and the orchestrator — run `deepseek-v4-pro`; the supporting roles — financial
experts, daytrade judge, and auditor — stay on `deepseek-v4-flash`. Until
2026-09-10 every role ran `deepseek-v4-flash`. The Z.ai GLM-5.3 Coding Plan path
is optional and re-armable per role via `SUPEREZIO_PRIMARY_MODEL` / `SUPEREZIO_AGENT_MODEL` plus
`SUPEREZIO_GLM_CODING_PLAN_API_KEY`; without that key no `glm` provider is built
and the runtime boots DeepSeek-only. A role set to a glm model without the key
still fails closed.

Version boundary: Python package and public API `4.0.0`; runtime configuration and model manifest `4.2.0`.

## Runtime Definition

SuperEzio has one official local runtime process for the product:

| Component | Entrypoint | Bind | Purpose |
| --- | --- | --- | --- |
| FastAPI agent server | `python -m agent_server.main` | `127.0.0.1:8002` | Browser UI, A2A envelope, pipeline, health, product routes. |

External dependency: official DeepSeek HTTPS API (`https://api.deepseek.com`).
Store `SUPEREZIO_DEEPSEEK_API_KEY` only in ignored local environment files
(`.env.local`) or the process environment. Never print or commit credentials.

Official config file: `config/runtime.yml`.

Current official model routing (all roles on the official DeepSeek HTTPS API;
per-role split in effect since 2026-09-12):

- `agent`: `deepseek-v4-pro` (deciding role) for Bob's investment-assistant responses.
- `local_orchestrator`: historical provider identifier, now routed to cloud `deepseek-v4-pro` (deciding role).
- `deepseek`: financial experts use `deepseek-v4-flash` (supporting role).
- `daytrade_judge` and `daytrade_auditor`: separate roles using `deepseek-v4-flash` (supporting roles).
- `glm`: optional Z.ai Coding Plan provider (`glm-5.3`), built only when `SUPEREZIO_GLM_CODING_PLAN_API_KEY` is present; requesting a glm model without it fails closed.
- Missing/invalid cloud configuration fails closed; no local model installation is required.

Official Windows launcher: `start.ps1`, invoked directly or through `setup_superezio.bat run`.

## Start and Stop

From the project root on Windows:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File check.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File start.ps1
```

`start.ps1` launches only the API, waits for liveness and opens the browser.
`-SkipBrowser` suppresses the browser. `-HealthTimeoutMinutes` controls the wait
(default 6). A successful launch confirms API liveness, not authenticated model
inference or market-data coverage.

For isolated validation:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File start.ps1 -SkipBrowser -IsolatedValidation
```

Validation uses separate storage under `runtime/validation`, disables scanning,
and freezes execution. It still uses the configured API port and fails if occupied.
Stop a process started by this launcher with:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File stop.ps1
```

The launcher records `runtime/api-process.json`; stop checks both PID and process
start time before terminating it. It never kills an arbitrary port owner. Processes
started manually must be stopped through their owning terminal or supervisor.

For a foreground launch (stop with Ctrl+C):

```powershell
$env:PYTHONPATH = "src;$env:PYTHONPATH"
python -m agent_server.main
```

The client release is validated on Windows. The source repository also contains
`setup_superezio.sh`; Linux/macOS are not included in this release validation.

## Healthchecks

```powershell
curl.exe -fsS http://127.0.0.1:8002/health
curl.exe -fsS http://127.0.0.1:8002/health/details
```

`/health` reports API liveness. `/health/details` reports readiness and returns
503 when a required provider is unavailable or unconfigured. Inspect the returned
secret-safe status, then verify provider configuration and outbound HTTPS. Never
paste credentials into logs or diagnostics. GPU availability is not a cloud-model
prerequisite. Market-data and broker availability must be evaluated separately
before relying on an analysis or a simulation.

## Public API Surface

Contract file: `.f51/contracts/agent-server.contract.md`.

Critical routes:

- `GET /`
- `GET|HEAD /health`
- `GET /health/details`
- `GET /metrics`
- `GET /neural/logs`
- `GET /api/chart-data/{ticker}`
- `GET /api/chart-sse/{ticker}`
- `POST /task/submit`
- `GET /capabilities`
- `GET /product/manifest`
- `POST /api/sdca/evaluate`
- `POST /experts/neural-decision/predict`

## Logs

Runtime log directory:

```text
runtime/logs
```

Current log files are operational artifacts from prior local runs. They are not a source of truth by themselves. Use them for diagnosis after reproducing a failure.

Useful commands:

```powershell
Get-ChildItem runtime\logs | Sort-Object LastWriteTime -Descending
Get-Content runtime\logs\<file>.log -Tail 80
curl.exe -N http://127.0.0.1:8002/neural/logs
```

## Checkpoints

Required checkpoints:

- Operational checkpoint: `.f51/checkpoints/latest.json`
- Runtime checkpoint: `runtime/checkpoints/latest.json`

Every `/f51-contracts`, `/f51-runtime`, and `/f51-tests` pass must update:

- `.f51/TASK_BOARD.md`
- `.f51/RISK_REGISTER.md`
- `runtime/checkpoints/latest.json`

## Minimum Verification Matrix

Offline contracts and smoke:

```powershell
python -m pytest tests\contracts -q
python -m pytest tests\test_runtime_smoke.py -q
```

Integration with live servers:

```powershell
python -m pytest tests\test_integration_runtime.py -q
```

The integration file may skip when its required services are not running. A skip is acceptable only when reported as not live-validated.

Quality checks for changed Python/test files:

```powershell
python -m ruff check tests\contracts\test_contract_runtime_official.py tests\test_runtime_smoke.py tests\test_integration_runtime.py
python -m ruff format --check tests\contracts\test_contract_runtime_official.py tests\test_runtime_smoke.py tests\test_integration_runtime.py
```

## Troubleshooting

### API port already in use

```powershell
Get-NetTCPConnection -LocalPort 8002 -State Listen -ErrorAction SilentlyContinue
```

If the managed application is already running, use `stop.ps1` before restarting.
If the owner came from another launcher, stop it through that launcher. Do not
terminate a process merely because it occupies the requested port.

### Cloud provider unavailable

Check the configured endpoint/model names in `config/runtime.yml`, provider
account availability, and `/health/details`. Supply credentials in the local
configuration without exposing their contents. Restart the managed API after
changing process environment variables. Do not report readiness until the provider
checks and a real assistant request succeed.

### API offline

Check:

```powershell
Test-Path src\agent_server\main.py
python -c "import fastapi, uvicorn, sse_starlette"
python -m agent_server.main
```

Then validate:

```powershell
curl.exe -fsS http://127.0.0.1:8002/health
curl.exe -fsS http://127.0.0.1:8002/health/details
```

## Regression Rule

Do not change product behavior while updating runtime docs/contracts. If a runtime inconsistency requires product code, stop, record the risk, and patch in a separate task.
