# Official Runbook - SuperEzio Runtime v4.0.0

Updated: 2026-05-20
Policy: DISK ONLY. GitHub is blocked by `.f51/GITHUB_POLICY.json`.

## Runtime Definition

SuperEzio has two official local runtime processes:

| Component | Entrypoint | Bind | Purpose |
| --- | --- | --- | --- |
| Agent llama.cpp server | `powershell -ExecutionPolicy Bypass -File scripts/serve_agent_llamacpp.ps1 -Port 8082` | `127.0.0.1:8082` | Local OpenAI-compatible Agent model endpoint. |
| FastAPI agent server | `python -m agent_server.main` | `127.0.0.1:8002` | Browser UI, A2A envelope, pipeline, health, product routes. |

Official config file: `config/runtime.yml`.

Official CEO model:

```text
models/superezio-ceo-intent-merged.Q4_K_M.gguf
```

Current official model routing:

- `ceo`: local OpenAI-compatible llama.cpp endpoint at `http://127.0.0.1:8082/v1`.
- `local_orchestrator`: local orchestrator route using the same CEO endpoint.
- `deepseek`: cloud expert provider at `https://api.deepseek.com`.

Official launcher:

```cmd
C:\Users\marco\Desktop\SuperEzio\desktop\SuperEzio.bat
```

The launcher loads `.env`, validates Python/curl/basic files, cleans ports `8082` and `8002`, starts the CEO, waits for CEO health, starts the API, waits for API health, then opens the browser unless `SUPEREZIO_NO_BROWSER=1`.

## Manual Start

From `C:\Users\marco\Desktop\SuperEzio`:

```powershell
# Terminal 1 - CEO
powershell -ExecutionPolicy Bypass -File scripts/serve_agent_llamacpp.ps1 -Port 8082

# Terminal 2 - API
$env:PYTHONPATH = "src;$env:PYTHONPATH"
python -m agent_server.main
```

For launcher validation without starting servers:

```powershell
$env:SUPEREZIO_LAUNCHER_CHECK = "1"
$env:SUPEREZIO_NO_BROWSER = "1"
cmd /c desktop\SuperEzio.bat
```

Expected result: `[OK] Launcher checks passed.`

## Healthchecks

```powershell
curl.exe -fsS http://127.0.0.1:8082/health
curl.exe -fsS http://127.0.0.1:8082/v1/models
curl.exe -fsS http://127.0.0.1:8002/health
curl.exe -fsS http://127.0.0.1:8002/health/details
```

Expected:

- CEO `/health`: JSON with `status=ok`.
- CEO `/v1/models`: OpenAI-compatible model listing.
- API `/health`: JSON with `status=ok`.
- API `/health/details`: JSON with `checks`.

An open TCP port is not enough. Treat the runtime as healthy only after HTTP health responses pass.

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

### Port 8082 or 8002 already in use

```powershell
Get-NetTCPConnection -LocalPort 8082 -ErrorAction SilentlyContinue
Get-NetTCPConnection -LocalPort 8002 -ErrorAction SilentlyContinue
```

Use the launcher for normal cleanup. Kill individual owners only after confirming the process:

```powershell
Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -eq <PID> } | Select-Object ProcessId,CommandLine
Stop-Process -Id <PID> -Force
```

### CEO offline

Check:

```powershell
Test-Path models\superezio-ceo-intent-merged.Q4_K_M.gguf
Test-Path llama.cpp\bin\llama-server.exe
powershell -ExecutionPolicy Bypass -File scripts\serve_agent_llamacpp.ps1 -Port 8082
```

Then validate:

```powershell
curl.exe -fsS http://127.0.0.1:8082/health
curl.exe -fsS http://127.0.0.1:8082/v1/models
```

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
