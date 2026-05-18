# DELIVERY CHECKLIST - SuperEzio v4.0.0

**Date:** 2026-05-17T22:05:49-04:00
**Mode:** local disk only
**Purpose:** minimum checklist before demo, release, and sale.

## Current Gate

| Gate | Status | Evidence |
|---|---:|---|
| Local API health | PASS | `GET :8002/health` -> 200 |
| Local CEO health | PASS | `GET :8082/health` -> 200 |
| Product manifest | PASS | `GET :8002/product/manifest` -> 200 |
| Capabilities | PASS | `GET :8002/capabilities` -> 200 |
| CEO model listing | PASS | `GET :8082/v1/models` -> 200 |
| Full tests | PASS | `635 passed, 5 warnings` |
| Ruff lint | PASS | `python -m ruff check src tests` |
| Ruff format | PASS | `python -m ruff format src tests --check` |
| Diff whitespace | PASS | `git diff --check` after report refresh |
| GitHub remote | FAIL | remote repository deleted/unsafe; `origin` still points to GitHub locally; no push executed |
| Dirty tracked cache | PASS | collector cache removed from Git index; files remain on disk |

## Demo Checklist

- [x] API server responds on `http://127.0.0.1:8002/health`.
- [x] CEO server responds on `http://127.0.0.1:8082/health`.
- [x] `/product/manifest` returns 200.
- [x] `/capabilities` returns 200.
- [x] Full tests pass locally.
- [ ] Run one scripted `/task/submit` demo request immediately before showing the system.
- [ ] Confirm end-to-end latency for that exact demo script.
- [ ] Confirm `desktop/SuperEzio.bat` starts CEO + API from a cold state.
- [ ] Prepare a fallback demo path if CEO generation takes too long.
- [ ] Keep `.env`, keys, and browser tabs with private material off-screen.

## Release Checklist

- [x] Fix Ruff lint errors in `src` and `tests`.
- [x] Run `python -m ruff format src tests` or apply equivalent formatting and re-run `--check`.
- [x] Resolve tracked `.f51/cache/collector/*.json` cache files: untrack them or explicitly justify them.
- [ ] Update stale Gemma/Qwen documentation and metadata:
  - `pyproject.toml`
  - `scripts/finetune_gemma_sft.py`
  - `scripts/vastai_setup_gemma.sh`
  - `scripts/generate_system_knowledge_sft.py`
  - `.f51/RISK_REGISTER.md`
- [ ] Decide the neural truth:
  - either promote `PriceTorchMLP`/`PriceMLP` into the default runtime path,
  - or rewrite neural documentation and sales language as rule/regime gating.
- [ ] Centralize env/config documentation into one canonical runbook.
- [x] Re-run:
  - `python -m pytest -q`
  - `python -m ruff check src tests`
  - `python -m ruff format src tests --check`
  - `git diff --check`

## Sale Checklist

- [ ] Create a new remote backup/repository or another off-disk backup strategy.
- [ ] Decide push policy before any `git push`; current `origin` still points to GitHub locally.
- [ ] Restore CI on the new remote with the same gates used locally.
- [ ] Rotate and document API keys before any screen share, investor demo, or customer handoff.
- [ ] Produce a reproducible setup path for:
  - Python environment
  - llama.cpp server binary
  - Qwen GGUF model
  - `.env` template
  - provider keys
- [ ] Add a product disclaimer and scope boundary: analysis aid, not investment advisor.
- [ ] Replace or clearly label mock/heuristic neural probabilities.

## No-Go Conditions

Do not demo to a prospect if any of these are true:

- CEO/API health is red.
- `/task/submit` does not reach `STREAM_END`.
- Response latency is unknown.
- `.env` or private keys are visible.
- The pitch claims "trained neural predictor" while default runtime uses `NeuralDecisionExpert` heuristics.

Do not sell if any of these are true:

- No off-disk backup.
- No CI/release gate.
- Lint/format gate red.
- Runtime requires undocumented local binaries/models.
- Product claims exceed code evidence.
