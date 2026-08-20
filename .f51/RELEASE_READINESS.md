# F51 Release Readiness

Updated: 2026-08-20

## Status

**PENDING CURRENT GATE EVIDENCE.** Documentation now targets the canonical zero-cloud runtime, but readiness is established only by a fresh successful gate run on the delivery tree. Historical pass counts are evidence snapshots, not permanent release claims.

## Canonical Runtime

- Shared local Qwen3.8-27B-Q4_K_M llama-server: `127.0.0.1:8080`.
- FastAPI and browser UI: `127.0.0.1:8002`.
- All LLM roles use the shared local endpoint; no cloud-LLM fallback exists.
- If the local model server is unavailable, the system must enter `MAN_AT_WORK` and block order submission.
- Agent army: 22 versioned agents.
- Test discovery snapshot: 1,885 tests collected on 2026-08-20. Always record the current collection and outcome.

Canonical operational sources: `config/runtime.yml`, `config/model_manifest.json`, and `docs/runbooks/RUNBOOK.md`.

## Required Checks

```powershell
python -m ruff check src/ tests/
python -m ruff format --check src/ tests/
python scripts/check_agents.py
python -m pytest tests/ -q
```

With the local model and API running:

```powershell
curl.exe -fsS http://127.0.0.1:8080/health
curl.exe -fsS http://127.0.0.1:8080/v1/models
curl.exe -fsS http://127.0.0.1:8002/health
curl.exe -fsS http://127.0.0.1:8002/health/details
python scripts/browser_smoke.py
```

Readiness also requires proof that stopping `:8080` produces fail-closed `MAN_AT_WORK` behavior without a cloud-LLM call, followed by successful recovery when the local server returns.

## Sign-off Record

Record the current timestamp, commit, collected/passed/failed/skipped counts, model ID returned by `/v1/models`, health results, browser-smoke result, and fail-closed/recovery result. Do not copy results from an older checkpoint.

## Policy

DISK ONLY. Never run `git push`, `git pull`, `git fetch`, or `gh`.
