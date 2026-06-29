# SuperEzio - Model Setup

The local CEO model (Bob) is **Bob Core Q4_K_M GGUF** (~17 GB) with F51 LoRA adapter.

## Expected Files

```text
C:\llama.cpp\models\Bob Core-q4_k.gguf           (base model, ~17 GB)
C:\llama.cpp\models\bob-lora-best.gguf                     (LoRA adapter, ~150 MB)
```

## Bob Core Architecture

- **Base**: Bob Core (dense, 48 layers, 262K context)
- **Quantization**: Q4_K_M (17.28 GB)
- **LoRA**: F51 v9 calibration adapter (rank 16, alpha 32)
- **Hardware**: RTX 5060 Ti 16GB (24 layers GPU, 12 frozen)
- **Training**: QLoRA via llama.cpp, calibrated with 500 samples

## How To Provide

Option 1: copy from an existing verified SuperEzio installation.

Option 2: download Bob Core Q4_K_M from the official source.

Option 3: use a compatible GGUF model and update `config.ps1` accordingly.

## Verify

After placing the model file, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\check.ps1
```

Expected: model check reports present GGUF and LoRA files.

## Packaging Rule

Do not include `*.gguf` files in source-only packages unless explicitly agreed.

