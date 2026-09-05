# SuperEzio — Model Setup (Qwen local CEO)

The local CEO model (Bob) is **Qwen3.8-27B-Q4_K_M** (GGUF, ~15.9 GB).

## Current machine state (2026-08-21)

- **GPU** (re-measured 2026-09-04): single **live** NVIDIA RTX 2070 8GB
  (driver 610.60 / CUDA UMD 13.3). The RTX 3060 12GB is still in the
  machine but `Get-PnpDevice` reports `Status=Error Problem=CM_PROB_FAILED_ADD`
  and `nvidia-smi` enumerates only the 2070. Dual-GPU `-ts 8,6` is NO-GO
  until Marco repairs the 3060 in Device Manager (same driver family as
  the 2070). The runtime uses 1 live GPU.
- **Model files**: **PRESENT** at `C:\Users\marco\models\qwen3.8-27b\`
  (downloaded 2026-08-14/15) — `config.ps1` probes this path automatically:

```text
Qwen3.8-27B-Q4_K_M.gguf        15.9 GB   (2-GPU / offload profile)
Qwen3.8-27B-UD-IQ2_XXS.gguf     8.4 GB   (single-GPU 12GB VRAM, Unsloth Dynamic v3)
Qwen3.8-27B-UD-IQ3_XXS.gguf    11.1 GB   (single-GPU, tight KV headroom)
mmproj-BF16.gguf                0.9 GB   (vision projector for image input)
```

- **llama-server**: present at `C:\Users\marco\tools\llama.cpp\llama-server.exe`
  (build 10435, 0.1.0-dev) — `config.ps1` probes this path automatically.
- **LoRA**: the current runtime config (`config.ps1`) uses no LoRA adapter.

## Single-GPU recommendation (12GB VRAM)

Use `Qwen3.8-27B-UD-IQ2_XXS.gguf` (8.4GB): fits VRAM-only with ~3.4GB
headroom for an 8-16K context. Unsloth recommends `presence_penalty >= 1.5`
for quants below Q2_K_XL to avoid repetition loops. The Q4_K_M build needs
either 2 working GPUs or CPU offload (48GB system RAM available).

## How To Add Variants

Option 1: copy a GGUF from an existing verified SuperEzio installation
into `models\` (project dir) or `%USERPROFILE%\models\qwen3.8-27b\`.

Option 2: download Qwen3.8-27B quants from the official source
(`unsloth/Qwen3.8-27B-GGUF` on Hugging Face) into either path above.

Option 3: point `SUPEREZIO_MODEL_PATH` at any other compatible GGUF.

## Verify

Run the launch script — it fails fast if the model is missing:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\serve_agent_llamacpp.ps1 -Port 8080
```

Expected: the banner prints the model path and the server starts. Any
`ERROR: Model not found` means the file is still absent.

## Packaging Rule

Do not include `*.gguf` files in source-only packages unless explicitly agreed.
