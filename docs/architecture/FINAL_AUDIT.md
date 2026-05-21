# SuperEzio Final Audit

Updated: 2026-05-21T00:00:00-04:00

## Verdict

The active tree is runtime-only. The production model artifact is the merged GGUF under `models/` and is served by the llama.cpp launcher.

## Runtime Contract

- CEO server: `scripts/serve_ceo_llamacpp.ps1 -Port 8082`
- API server: `python -m agent_server.main`
- Model: `models/superezio-ceo-intent-merged.Q4_K_M.gguf`
- API health: `/health`, `/health/details`
- CEO health: `/health`, `/v1/models`
- Stream route: `POST /task/submit`

## Removed Surface

Archived code, generic non-F51 skills, stale provider aliases, edge placeholders, model build data, model build launchers, and merge helpers are out of the active tree.

## Required Evidence

- Ruff lint and format check.
- Pytest suite.
- JSON validation.
- CEO direct chat completion.
- API stream reaching `STREAM_END`.