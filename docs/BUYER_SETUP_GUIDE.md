# SuperEzio - Buyer Setup Guide

This guide is for a technical buyer or evaluator setting up SuperEzio on a clean Windows machine.

## 1. Hardware Requirements

| Component | Minimum | Verified On |
|-----------|---------|-------------|
| OS | Windows 10/11 64-bit | Windows 11 Pro |
| RAM | 48 GB | 64 GB |
| GPU | NVIDIA RTX, 8 GB VRAM | RTX 5060 Ti, 16 GB VRAM |
| Storage | 60 GB free SSD | NVMe SSD |
| Network | Required for initial setup and optional data providers | Local runtime tested |

The 80B GGUF model is large. Machines below the minimum may boot slowly, swap heavily, or fail to load the model.

## 2. Install Prerequisites

Install these before running the kit:

- Python 3.12.x or 3.11.x, 64-bit.
- Microsoft Visual C++ Redistributable x64.
- NVIDIA driver and CUDA-compatible runtime if GPU acceleration is expected.
- Git is optional. It is useful for source history, but not required if the seller provides a ZIP or folder transfer.

Verify from PowerShell:

```powershell
python --version
nvidia-smi
```

## 3. Install llama.cpp

SuperEzio starts a local `llama-server.exe` on port 8082.

Recommended path:

```text
C:\llama.cpp\build-cuda\bin\llama-server.exe
```

Alternative: set an explicit path before starting:

```powershell
$env:SUPEREZIO_LLAMA_SERVER_EXE = "C:\path\to\llama-server.exe"
```

If you are using a custom F51/Nitro build, verify acceleration from the server logs. The launcher no longer claims F51 just because the executable lives in a CUDA folder.

## 4. Add The Model

The model is not included in source-only packages. See `models/README_MODEL.md`.

Expected filename:

```text
models\Huihui-Qwen3-Next-80B-A3B-Instruct-abliterated.IQ4_XS.gguf
```

## 5. Install SuperEzio

From the SuperEzio root folder:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
```

`requirements.txt` is provided as a dependency mirror, but `pip install -e .` is the primary install path because `pyproject.toml` is the source of truth.

## 6. Configure Environment

Copy the template:

```powershell
Copy-Item .env.example .env
```

The local CEO can run without cloud model keys, but market-data and expert coverage may be reduced.

Common optional keys:

- `FINNHUB_API_KEY`: market data.
- `SUPEREZIO_DEEPSEEK_API_KEY`: optional expert sub-analysis.
- `GEMINI_API_KEY`: optional sentiment or fallback analysis.

Do not ship a real `.env` file to a buyer. Ship `.env.example` and let the buyer add their own keys.

## 7. Verify Installation

Run:

```powershell
powershell -ExecutionPolicy Bypass -File .\check.ps1
```

Expected on a clean stopped system: all required checks pass. If ports 8082 or 8002 are already in use, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\stop.ps1
```

Then run `check.ps1` again.

## 8. Start SuperEzio

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

The script starts:

- CEO model server at `http://127.0.0.1:8082/v1`
- API and UI at `http://127.0.0.1:8002`

The first model load can take several minutes.

## 9. Test The Product

Open:

```text
http://127.0.0.1:8002
```

Try a bounded research prompt:

```text
I have CAD 25,000 to allocate. Build a serious framework with risk limits.
```

Expected: a structured educational analysis with risk framing and a bounded next step. This is not financial advice and does not execute trades.

## 10. Stop

```powershell
powershell -ExecutionPolicy Bypass -File .\stop.ps1
```

The stop script only targets processes listening on the official SuperEzio ports.

## Troubleshooting

| Problem | Action |
|---------|--------|
| Port 8082 or 8002 in use | Run `stop.ps1`, then retry |
| Model not found | Put the GGUF file under `models\` with the expected filename |
| `llama-server.exe` not found | Install llama.cpp or set `SUPEREZIO_LLAMA_SERVER_EXE` |
| CUDA unavailable | Check NVIDIA driver, CUDA runtime, and llama.cpp build |
| Missing Python package | Run `python -m pip install -e .` |
| Slow responses | Expected for complex prompts on an 80B local model |
