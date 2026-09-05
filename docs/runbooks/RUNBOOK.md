# Official Runbook - SuperEzio Runtime v4.2.0

Updated: 2026-08-21
Policy: DISK ONLY. GitHub is blocked by `.f51/GITHUB_POLICY.json`.
Model policy: CLOUD MODEL APIs — CEO/orchestrator use Z.ai GLM-5.3 (or DeepSeek V4 Pro)
via HTTPS API; financial experts, judge, and auditor use the official DeepSeek HTTPS API.
No local model server (:8080) is required.

Version boundary: Python package and public API `4.0.0`; runtime configuration and model manifest `4.2.0`.

## Runtime Definition

SuperEzio has one official local runtime process for the product:

| Component | Entrypoint | Bind | Purpose |
| --- | --- | --- | --- |
| FastAPI agent server | `python -m agent_server.main` | `127.0.0.1:8002` | Browser UI, A2A envelope, pipeline, health, product routes. |

External dependencies:
- Z.ai Coding Plan API (`https://api.z.ai/api/coding/paas/v4`) for Bob CEO / orchestrator (`glm-5.3`).
- Official DeepSeek API (`https://api.deepseek.com`) for financial experts, day-trade judge, and auditor (`deepseek-v4-pro`).
Store keys (`SUPEREZIO_GLM_CODING_PLAN_API_KEY`, `SUPEREZIO_DEEPSEEK_API_KEY`) only in ignored local environment files (`.env.local`).

Official config file: `config/runtime.yml`.

Current official model routing:

- `agent`: Z.ai Coding Plan endpoint (`https://api.z.ai/api/coding/paas/v4`, model `glm-5.3`) running the CEO prompt/mandamentos, or official DeepSeek API (`deepseek-v4-pro`).
- `local_orchestrator`: orchestrator route using the same cloud model.
- `deepseek`: financial experts pinned to `deepseek-v4-pro` at `https://api.deepseek.com`.
- `daytrade_judge` and `daytrade_auditor`: independently pinned DeepSeek roles using the same authenticated external endpoint.
- Missing/invalid cloud configuration fails closed (MAN_AT_WORK).

Official Windows launcher: `start.ps1`, invoked directly or through `setup_superezio.bat run`.

## Manual Start

### Production Mode (100% Cloud Models)
From the project root, start the API server directly (models are served via external HTTPS APIs):

```powershell
$env:PYTHONPATH = "src;$env:PYTHONPATH"
python -m agent_server.main
```

Before starting, configure your cloud secrets in `.env.local` (never commit it):

```ini
SUPEREZIO_DEEPSEEK_API_KEY=your-deepseek-api-key
SUPEREZIO_GLM_CODING_PLAN_API_KEY=your-zai-api-key
```

### Standby / Historical Local Serving Profile (Optional)
If testing or running the legacy local model server on `:8080`:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/serve_agent_llamacpp.ps1 -Port 8080
```

For launcher validation without starting servers:

```powershell
# Validate config integrity
python -c "import yaml; cfg=yaml.safe_load(open('config/runtime.yml')); print('[OK] Config valid')"
# Validate model script exists
Test-Path scripts\serve_agent_llamacpp.ps1
```

Expected result: `[OK] Config valid` + `True`.

## Healthchecks

```powershell
curl.exe -fsS http://127.0.0.1:8080/health
curl.exe -fsS http://127.0.0.1:8080/v1/models
curl.exe -fsS http://127.0.0.1:8002/health
curl.exe -fsS http://127.0.0.1:8002/health/details
```

Expected:

- CEO `/health`: JSON with `status=ok`.
- CEO `/v1/models`: OpenAI-compatible model listing.
- API `/health`: JSON with `status=ok`.
- API `/health/details`: HTTP 200 only when the local CEO is reachable and the external expert tier is configured; otherwise HTTP 503 with a secret-safe status such as `unconfigured_missing_api_key`.

An open TCP port is not enough. Treat the runtime as healthy only after HTTP health responses pass.

If CEO `/health` fails: the system is expected to be in MAN_AT_WORK mode (no trading orders). Do not point the CEO at DeepSeek as a workaround; restart the local server instead. If DeepSeek readiness fails, validate the key, official base URL, model id, and outbound HTTPS separately; do not redirect experts to Qwen.

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

The integration file skips when CEO/API are not running. A skip is acceptable only when reported as not live-validated.

Quality checks for changed Python/test files:

```powershell
python -m ruff check tests\contracts\test_contract_runtime_official.py tests\test_runtime_smoke.py tests\test_integration_runtime.py
python -m ruff format --check tests\contracts\test_contract_runtime_official.py tests\test_runtime_smoke.py tests\test_integration_runtime.py
```

## Troubleshooting

### Port 8080 or 8002 already in use

```powershell
Get-NetTCPConnection -LocalPort 8080 -ErrorAction SilentlyContinue
Get-NetTCPConnection -LocalPort 8002 -ErrorAction SilentlyContinue
```

Kill individual owners only after confirming the process:

```powershell
Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -eq <PID> } | Select-Object ProcessId,CommandLine
Stop-Process -Id <PID> -Force
```

### CEO offline

Check the portable configuration resolved by `config.ps1`:

```powershell
. .\config.ps1
Write-SuperEzioConfig
Test-Path -LiteralPath $ModelPath
Test-Path -LiteralPath $LlamaServerPath
powershell -ExecutionPolicy Bypass -File scripts\serve_agent_llamacpp.ps1 -Port 8080
```

Then validate:

```powershell
curl.exe -fsS http://127.0.0.1:8080/health
curl.exe -fsS http://127.0.0.1:8080/v1/models
```

Note: the two GPUs cannot hold two llama-server instances. If the port is
busy with a working cc server, reuse it — do not start a second one.

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
