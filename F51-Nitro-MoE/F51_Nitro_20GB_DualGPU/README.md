# Mixtral 8x7B Local Kit

Operational focus: Mixtral 8x7B Instruct Q4_K_M on the local RTX 5060 Ti 16GB machine.

## What This Kit Does

This kit starts a local `llama-server` for:

- model: `models\Mixtral-8x7B-Instruct-v0.1-GGUF\mixtral-8x7b-instruct-v0.1.Q4_K_M.gguf`
- runtime: `bin_mixtral_legacy\llama-server.exe`
- server URL: `http://127.0.0.1:8080`

The legacy runtime is intentional. The current F51 runtime expects consolidated Mixtral tensors such as `blk.0.ffn_down_exps.weight`; this downloaded GGUF uses the older tensor layout, so it fails on the newer runtime.

## Start Command

From this directory:

```bat
START_MIXTRAL_FINANCE.bat
```

From the project root:

```bat
START_MIXTRAL_LOCAL_16GB.bat
```

## Proof It Works

Health:

```powershell
Invoke-WebRequest http://127.0.0.1:8080/health -UseBasicParsing
```

Expected:

```json
{"status":"ok"}
```

Completion:

```powershell
$body = @{
  prompt = "[INST] Explain MoE in one sentence. [/INST]"
  n_predict = 64
  temperature = 0
} | ConvertTo-Json -Compress

Invoke-RestMethod http://127.0.0.1:8080/completion -Method Post -ContentType "application/json" -Body $body
```

## Current Local Result

Validated on 2026-05-31:

- runtime loaded: `llama.cpp b3989`
- GPU offload: `-ngl 18`
- context: `-c 2048`
- prompt throughput observed: up to about `77 tok/s` on a short batched prompt
- decode throughput observed: about `14 tok/s`
- quality caveat: general completions work, but factual self-knowledge about Mixtral hallucinated in Portuguese. Do not use this model as a factual authority without retrieval or verification.

Evidence:

```text
evidencias\validation\20260531_235731_mixtral_legacy
C:\F51_LAB\mixtral_legacy_cli_20260531_235433.log
```

## Verdict

Mixtral is usable as a fast local instruct model on this machine, but this specific GGUF is not compatible with the current F51 runtime. Treat it as a Mixtral legacy-runtime profile, not as an F51 cache result.
