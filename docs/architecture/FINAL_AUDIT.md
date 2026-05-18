# FINAL AUDIT - SuperEzio v4.0.0

**Date:** 2026-05-17T22:05:49-04:00
**Mode:** f51-audit + f51-release blocker fix, hostile production/commercial audit
**Source of truth:** local disk only. No GitHub push was executed.
**Commit observed:** local working tree after engineering-gate repair

## Executive Verdict

SuperEzio is demonstrable under operator control, but it is not clean enough to sell as a reliable product yet.

The runtime is alive: API health, product manifest, capabilities, CEO health, and CEO model listing all returned 200 locally. The full test suite passed: `635 passed, 5 warnings`. The local engineering gate now passes: Ruff lint, Ruff format check, and diff whitespace checks are clean after formatting and cache untracking.

Commercial readiness still fails because there is no off-disk remote/CI, production still contains rule/mocking shortcuts in the neural decision path, config is scattered, local model/binary/env dependencies are not packaged, and commercial claims/docs still overstate or contradict the runtime.

## Evidence Collected

| Check | Result | Evidence |
|---|---:|---|
| API health | PASS | `http://127.0.0.1:8002/health` -> 200 |
| Product manifest | PASS | `http://127.0.0.1:8002/product/manifest` -> 200 |
| Capabilities | PASS | `http://127.0.0.1:8002/capabilities` -> 200 |
| CEO health | PASS | `http://127.0.0.1:8082/health` -> 200 |
| CEO models | PASS | `http://127.0.0.1:8082/v1/models` -> 200, `qwen36-35b-f51.Q4_K_M.gguf` |
| Full pytest | PASS | `python -m pytest -q` -> `635 passed, 5 warnings` |
| Ruff lint | PASS | `python -m ruff check src tests` -> `All checks passed!` |
| Ruff format check | PASS | `python -m ruff format src tests --check` -> `196 files already formatted` |
| Diff whitespace | PASS | `git diff --check` -> no errors after report refresh |
| Tracked collector cache | PASS | `.f51/cache/collector/*.json` removed from Git index only; files remain on disk |
| Push safety | OPEN | `origin` still points to GitHub locally; do not push until the remote/backup policy is explicit |

## Findings

### F1 - Local Engineering Gate Was Repaired

**Severity:** RESOLVED LOCALLY
**Evidence:** `python -m ruff check src tests` passes. `python -m ruff format src tests --check` passes. `python -m pytest -q` passes with `635 passed, 5 warnings`.

This removes the immediate local engineering blocker. It does not make the project sale-ready because continuity, reproducibility, and runtime truth are still open.

### F2 - Production Neural Decision Contains Mock/Heuristic Core

**Severity:** HIGH
**Evidence:** `src/experts/neural_decision/neural_decision_expert.py` initializes `up_prob = 0.33`, `down_prob = 0.33`, `sideways_prob = 0.34`, and includes the comment `Mocking real distribution matching the regime and technical features`.

The active pipeline uses `NeuralDecisionExpert`. That component is a rule/regime gate with hardcoded probabilities, not a trained neural model. The lower-level `PriceMLP` and `PriceTorchMLP` exist under `src/experts/technical_neural/`, but the default `ProfessionalCollector` path does not call them directly.

Commercial risk: do not sell this as "dynamic neural prediction" until the active runtime really uses the ML path or the claim is rewritten.

### F3 - Architecture Documentation Overstates Runtime

**Severity:** HIGH
**Evidence:** `.f51/NEURAL_EXPERT_ARCHITECTURE.md` describes an LSTM/MLP trained on the last 600 bars and providing a tensor probability. Runtime evidence shows:

- `PriceMLP` can train on candle data and return `mlp_score`.
- `PriceTorchMLP` exists.
- The active graph calls `NeuralDecisionExpert`, which is rule/regime logic.

The document is useful as a target architecture, not as a true production description.

### F4 - Config Is Scattered Across Too Many Places

**Severity:** MEDIUM
**Evidence:** env/config lookup is spread across `.env.example`, `config/runtime.yml`, `config/model_manifest.json`, `src/agent_server/main.py`, `src/core/model_serving/providers.py`, `src/core/pipeline/nodes/*.py`, `src/data/data_hub.py`, `src/core/data_collector/professional.py`, and training scripts.

Concrete drift:

- `pyproject.toml` still describes CEO as `Gemma-4-26B-A4B-abliterated`.
- `scripts/finetune_gemma_sft.py`, `scripts/vastai_setup_gemma.sh`, and `scripts/generate_system_knowledge_sft.py` still contain old Gemma runtime claims.
- `.f51/RISK_REGISTER.md` still lists stale risks already partly fixed.

### F5 - Runtime Is Duplicated Across Launch Paths

**Severity:** MEDIUM
**Evidence:** runtime/startup information exists in `desktop/SuperEzio.bat`, `scripts/serve_ceo_llamacpp.ps1`, `scripts/run_qwen36.ps1`, `config/runtime.yml`, `README.md`, and `src/agent_server/main.py`.

This is demo-risky. The API and CEO were reachable during audit, but a clean machine or a double-click launcher can still drift from the manual path.

### F6 - Hidden/External Dependencies Are Not Packaged

**Severity:** MEDIUM
**Evidence:** critical runtime depends on local assets outside Git:

- `models/qwen36-35b-f51.Q4_K_M.gguf` is ignored and required for CEO runtime.
- `llama.cpp/` is ignored and required for `llama-server.exe`.
- `.env` is ignored and required for paid providers.
- `requirements-ci.txt` is only a test-focused subset; it does not represent the complete runtime/training dependency graph.

This is acceptable for one local workstation, not for a reproducible commercial install.

### F7 - Tracked Operational Cache Was Removed From Git Index

**Severity:** RESOLVED LOCALLY
**Evidence:** collector cache files under `.f51/cache/collector/*.json` were removed from the Git index with `git rm --cached`. They remain physically present on disk.

This fixes the noisy tracked-cache problem for future commits without deleting runtime cache from the workstation.

### F8 - Contract Fragility Remains In Public Endpoints

**Severity:** MEDIUM
**Evidence:** `/task/submit` uses a Pydantic envelope, but `/experts/neural-decision/predict` accepts raw `payload: dict` and validates manually. Several internal graph/state paths rely on loose `dict[str, Any]`.

This is not fatal because tests cover the endpoint, but it is fragile for external consumers.

### F9 - Tests Pass But Some Tests Are Synthetic/Smoke-Only

**Severity:** LOW
**Evidence:** `tests/test_neural_decision.py` explicitly says it uses synthetic test cases. `tests/test_rag_engine_smoke.py` uses print-style smoke behavior.

This is acceptable for regression coverage, but it is not market-quality proof of predictive validity or RAG truth quality.

### F10 - Security/Secrets Posture Is Local-Only

**Severity:** HIGH for sale, MEDIUM for internal demo
**Evidence:** `.env` is ignored, but the product depends on plaintext local secrets. There are internal docs about leaked keys and `.env` is on disk.

No sale until there is an explicit key rotation and secret-handling plan for demos and deployments.

## Orphan / Dead / Misleading Areas

| Area | Finding | Action |
|---|---|---|
| `scripts/finetune_gemma_sft.py` | Legacy Gemma training path | Archive or mark deprecated |
| `scripts/vastai_setup_gemma.sh` | Legacy Gemma setup | Archive or mark deprecated |
| `scripts/generate_system_knowledge_sft.py` | Emits old Gemma CEO claims | Update before any generated dataset/demo |
| `src/experts/technical_neural/` | Functional but not default runtime path | Promote or explicitly label experimental |
| `.f51/cache/collector/*.json` | Tracked cache despite ignore rule | Untrack or move to runtime-only storage |
| `docs/architecture/archives/` | Old Qwen/Gemma claims | Keep archived, never use as current truth |

## Release Classification

| Category | Status |
|---|---|
| Internal local demo | CONDITIONAL PASS |
| Client/prospect live demo | FAIL until cold-start and `/task/submit` smoke are re-proved |
| Commercial sale | FAIL |
| Engineering release | LOCAL PASS |

## Hostile Bottom Line

The system is no longer "lost"; it is alive, test-covered, and locally clean on Ruff. But commercial readiness is still blocked by continuity, reproducibility, and truth-in-marketing issues, not by missing code.
