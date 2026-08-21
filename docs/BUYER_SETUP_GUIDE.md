# SuperEzio V1 — Windows Setup Guide

This guide covers the deliverable V1: a local, authenticated financial-research
copilot. It never submits live/real-capital orders. IBKR paper orders can be
transmitted only when explicitly enabled and all safety/readiness gates pass.
TD Direct Investing remains a manual workflow with no broker transport, and
real-capital automation is **NO-GO**.

## 1. Prerequisites

- Windows 10/11, 64-bit.
- Python 3.11 or 3.12, 64-bit.
- NVIDIA drivers and a CUDA-capable `llama.cpp` build for GPU acceleration.
- Enough RAM/VRAM and SSD space for the 15.9 GB Q4_K_M model.
- Network access for the initial dependency install and optional market-data providers.

The validated operator runtime uses the local
`Qwen3.8-27B-UD-IQ2_XXS.gguf` model with an 8192-token context. Hardware with less
available memory can be slower or may fail to load the model.

## 2. Install the local model runtime

Install `llama-server.exe`, then either place it at:

```text
llama.cpp\bin\llama-server.exe
```

or define its location for the current PowerShell session:

```powershell
$env:SUPEREZIO_LLAMA_SERVER_EXE = "C:\path\to\llama-server.exe"
```

The GGUF is not included in a source-only package. Place it at:

```text
models\Qwen3.8-27B-UD-IQ2_XXS.gguf
```

or define:

```powershell
$env:SUPEREZIO_MODEL_PATH = "D:\models\Qwen3.8-27B-UD-IQ2_XXS.gguf"
```

## 3. Bootstrap the product

From the extracted SuperEzio directory, set a unique first-operator password in
the current process and run the locked bootstrap:

```powershell
$env:SUPEREZIO_ADMIN_PASSWORD = "replace-with-a-unique-long-password"
.\setup_superezio.bat
```

The bootstrap:

- creates `.venv`;
- installs the exact versions in `requirements-lock.txt`;
- installs the local package without resolving a second dependency graph;
- installs Playwright Chromium;
- creates `.env.local` and a random JWT secret when needed;
- seeds the first local operator without putting the password in command history.

Do not distribute `.env`, `.env.local`, databases, journals, logs, traces or
saved browser sessions.

## 4. Start and stop

Start through the only supported launcher:

```powershell
.\setup_superezio.bat run
```

It starts:

- local CEO/model server: `http://127.0.0.1:8080`;
- API and browser product: `http://127.0.0.1:8002`.

Stop with:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\stop.ps1
```

`start_all.bat` and `superezio_launcher.bat` are compatibility shims that now
delegate to the same official launcher.

## 5. Verify

After the services are healthy:

```powershell
python -m ruff check src tests
python -m pytest tests\contracts tests\test_windows_bootstrap_contract.py -q
python scripts\browser_smoke.py
```

The browser smoke uses `TD.TO`, verifies a non-empty chart and canvas, sends one
bounded chat request, and fails on visible or console errors.

The response-quality gate must only run against a separately started isolated
validation runtime. It refuses the normal product runtime by design:

```powershell
python scripts\quality_probe.py --api http://127.0.0.1:8002
```

## 6. Product boundary

- V1 is research and decision support, not financial advice.
- IBKR transport is paper-only, explicitly enabled and protected by readiness and safety gates.
- TD Direct Investing remains manual; SuperEzio does not transport TD orders.
- Broker offline does not mean core offline.
- No successful HTTP request is treated as broker confirmation.
- No TD credential is required or stored.
- Any future real-capital pilot requires a new Money Gate decision, independent
  release evidence and explicit human approval.

## Troubleshooting

| Problem | Action |
|---|---|
| Port 8080 or 8002 in use | Run `stop.ps1`, then start again. |
| Model not found | Set `SUPEREZIO_MODEL_PATH` or use the documented `models` path. |
| `llama-server.exe` not found | Set `SUPEREZIO_LLAMA_SERVER_EXE` or use the bundled path. |
| CUDA unavailable | Check NVIDIA drivers and the llama.cpp build. |
| Login unavailable | Re-run bootstrap so `.env.local` gets a JWT secret. |
| Quality probe refuses runtime | Start an isolated validation runtime; refusal is fail-closed behavior. |
