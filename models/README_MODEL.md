# SuperEzio - Model Setup

The local CEO model is not included in source-only packages because it is about 40 GB.

## Expected File

```text
models\Huihui-Qwen3-Next-80B-A3B-Instruct-abliterated.IQ4_XS.gguf
```

## How To Provide It

Option 1: copy from an existing verified SuperEzio installation.

Option 2: download the same GGUF model from the provider or model host used by the seller.

Option 3: use a compatible GGUF model and update `config.ps1` so `$ModelName` matches the filename.

Smaller models may start more easily but can reduce analysis quality. Validate output quality before calling a substituted model buyer-ready.

## Verify

After placing the model file under `models\`, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\check.ps1
```

Expected: the model check reports a present GGUF file and an approximate size.

## Packaging Rule

Do not include `models\*.gguf` in a source-only package unless the sale explicitly includes the model file and the buyer has storage capacity for it.
