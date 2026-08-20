# Runtime Single Authority Audit - 2026-06-02

> **HISTORICO / SUPERSEDED.** Esta auditoria preserva a antiga autoridade da porta `8082`. A autoridade atual e Qwen3.8-27B local em `:8080`; use `docs/runbooks/RUNBOOK.md`.

## Objective

Make the Bob runtime unambiguous: one owner for port 8082, one owner for port 8002, and one explicit inference engine path.

## Finding

The previous runtime surface had a dangerous ambiguity:

- `scripts/serve_agent_llamacpp.ps1` claimed "F51 Nitro" but always launched the repo-local binary:
  - `llama.cpp\bin\llama-server.exe`
  - observed version: `9186 (3a92bc99d)`
  - observed decode in current live logs: roughly 14-20 tok/s
- The patched F51 runtime identified by prior F51 work lives outside this repo:
  - `C:\llama.cpp\build-cuda\bin\llama-server.exe`
  - observed version: `3 (579fe01)`
  - branch: `f51-nitro-layer1`
  - source tree contains active F51 changes in CUDA/backend/model-loader files
- Several operational documents and scripts referenced "Nitro" without declaring which binary is authoritative.

## Root Cause

The runtime contract described a capability ("F51 Nitro MoE") instead of pinning the executable authority. That allowed a correct-looking launcher to start the wrong binary.

## Applied Fix

- `scripts/serve_agent_llamacpp.ps1` now resolves the inference engine in this order:
  1. `SUPEREZIO_LLAMA_SERVER_EXE` or `-LlamaServerPath`
  2. `C:\llama.cpp\build-cuda\bin\llama-server.exe`
  3. repo fallback `llama.cpp\bin\llama-server.exe`
- The launcher prints the resolved binary path, version, F51-build boolean, and warning when falling back.
- F51 environment knobs are set by the launcher:
  - `F51_MOE_CACHE=1`
  - `F51_MOE_CACHE_ENABLED=1`
  - `F51_MOE_SCHED_SKIP=1`
  - `F51_MOE_CACHE_CAPACITY=16`
- `runtime/do_restart.ps1` now kills only official ports 8082/8002 and exact runtime process patterns. It no longer kills broad substrings such as `SuperEzio` or `llama.cpp`.
- `config/runtime.yml` now records preferred and fallback llama-server paths.
- Runtime contract tests now assert the preferred F51 binary and F51 env knobs.

## Remaining Risk

The historical 38-42 tok/s Qwen numbers are not treated as proven-current until rerun from raw logs. The next validation must restart Bob with the patched F51 binary and capture a fresh decode speed line.

## Next Verification

1. Stop current Bob/API.
2. Run `runtime/do_restart.ps1`.
3. Confirm `runtime/logs/bob-8082-latest.log` reports:
   - `Server     : C:\llama.cpp\build-cuda\bin\llama-server.exe`
   - `F51 build  : True`
4. Run a short `/v1/chat/completions` speed probe.
5. Only then run browser/financial QA.
