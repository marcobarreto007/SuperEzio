# SuperEzio — Model Setup (Qwen local CEO)

The local CEO model (Bob) is **Qwen3.8-27B-Q4_K_M** (GGUF, ~15.9 GB).

## Current machine state (2026-08-21)

- **GPU**: single working NVIDIA RTX 3060 12GB (driver 560.94 / CUDA 12.6).
  A machine also has an RTX 2070 8GB that is physically present but in a
  FAILED state (Windows Code 31, mismatched OEM driver packages) and a
  P106-100 mining card. The runtime assumes 1 GPU until the 2070 is
  repaired; if repaired, total VRAM is 20GB and the 2-GPU tensor-split
  profile becomes viable again.
- **Model file**: **NOT INSTALLED**. `models/` contains only this README.
  Until `Qwen3.8-27B-Q4_K_M.gguf` is present, the CEO server on :8080 is
  fail-closed: `scripts/serve_agent_llamacpp.ps1` aborts with
  `ERROR: Model not found`.
- **LoRA**: the current runtime config (`config.ps1`) uses no LoRA adapter.

## Expected Files

```text
models\Qwen3.8-27B-Q4_K_M.gguf          (base model, ~15.9 GB)
```

Optional user-profile fallback probed by `config.ps1`:

```text
%USERPROFILE%\models\qwen3.8-27b\Qwen3.8-27B-Q4_K_M.gguf
```

## How To Provide

Option 1: copy the GGUF from an existing verified SuperEzio installation
into `models\`.

Option 2: download the Qwen3.8-27B Q4_K_M GGUF from the official source and
place it in `models\`.

Option 3: use a compatible GGUF elsewhere and point `SUPEREZIO_MODEL_PATH`
(or edit `config.ps1`) at it.

## Verify

Run the launch script — it fails fast if the model is missing:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\serve_agent_llamacpp.ps1 -Port 8080
```

Expected: the banner prints the model path and the server starts. Any
`ERROR: Model not found` means the file is still absent.

## Packaging Rule

Do not include `*.gguf` files in source-only packages unless explicitly agreed.
