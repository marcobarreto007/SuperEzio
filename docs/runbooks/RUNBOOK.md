# Official Runbook - SuperEzio Runtime v4.2.0

Updated: 2026-08-18
Policy: DISK ONLY. GitHub is blocked by `.f51/GITHUB_POLICY.json`.
Model policy: ZERO-CLOUD — every LLM role is served by the shared local
llama-server (perfil cc) on `127.0.0.1:8080`. No cloud fallback exists.

## Runtime Definition

SuperEzio has two official local runtime processes:

| Component | Entrypoint | Bind | Purpose |
| --- | --- | --- | --- |
| CEO llama-server (shared cc) | `powershell -ExecutionPolicy Bypass -File scripts/serve_agent_llamacpp.ps1 -Port 8080` (or the operator's `run-cc.ps1`) | `127.0.0.1:8080` | Local OpenAI-compatible LLM endpoint — serves CEO, orchestrator, experts, judge and auditor. |
| FastAPI agent server | `python -m agent_server.main` | `127.0.0.1:8002` | Browser UI, A2A envelope, pipeline, health, product routes. |

Official config file: `config/runtime.yml`.

Official CEO model (2026-08-18):

```text
C:\Users\marco\models\qwen3.8-27b\Qwen3.8-27B-Q4_K_M.gguf
```

Model: Qwen3.8-27B (dense)
Quantization: Q4_K_M (15.9 GB file)
Context: 16384 tokens (24576 CUDA OOM on RTX 2070 KV/compute buffers; MTP also OOM — disabled)
GPU: all layers offloaded, split across RTX 3060 12GB + RTX 2070 8GB (`-ngl all -sm layer -ts 12,8`)
Cache: KV q8_0, flash attention on. MTP disabled (CUDA OOM on 2070 with Q4).
Slots: 1 (shared with the Claude Code perfil cc — one server, one queue)

Current official model routing (zero-cloud):

- `agent`: local OpenAI-compatible llama.cpp endpoint at `http://127.0.0.1:8080/v1`. Never falls back to another provider — if the server is down the system enters MAN_AT_WORK.
- `local_orchestrator`: local orchestrator route using the same endpoint.
- `deepseek`: legacy routing name for the financial experts — serves the same local endpoint at `http://127.0.0.1:8080/v1` (NOT api.deepseek.com).

Official launcher: **RETIRED.** The `desktop/SuperEzio.bat` has been deleted. Start services directly.

## Manual Start

From the project root:

```powershell
# Terminal 1 - CEO (shared cc server; run-cc.ps1 is the preferred profile)
C:\Users\marco\models\qwen3.8-27b\run-cc.ps1
# ...or, equivalently:
powershell -ExecutionPolicy Bypass -File scripts/serve_agent_llamacpp.ps1 -Port 8080

# Terminal 2 - API
$env:PYTHONPATH = "src;$env:PYTHONPATH"
python -m agent_server.main
```

For launcher validation without starting servers (BAT retired, use direct validation):

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
- API `/health/details`: JSON with `checks`.

An open TCP port is not enough. Treat the runtime as healthy only after HTTP health responses pass.

If CEO `/health` fails: the system is expected to be in MAN_AT_WORK mode (no trading orders). Do NOT point any provider at a cloud API to "work around" it — that violates the zero-cloud policy. Restart the local server instead.

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

Check (paths are real, from `config.ps1`):

```powershell
Test-Path C:\Users\marco\models\qwen3.8-27b\Qwen3.8-27B-Q4_K_M.gguf
Test-Path C:\Users\marco\tools\llama.cpp\llama-server.exe
C:\Users\marco\models\qwen3.8-27b\run-cc.ps1
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
