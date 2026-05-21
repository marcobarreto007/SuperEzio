# SuperEzio Clean Tree Report

Date: 2026-05-21

## Current State

The active tree no longer carries archived runtime modules, retired architecture reports, or generic third-party Claude skill bundles. The remaining project-local skill surface is limited to:

- `.claude/skills/f51-*`
- `.claude/skills/arqueologist`
- `.claude/skills/frontend-design`

## Removed From Active Tree

- `archive/`
- `retired architecture report bundle/`
- non-F51 generic `.claude/skills/*` bundles
- stale relocation and archaeology reports under `.f51/`
- retired provider alias path `local_orchestrator`
- retired edge-gateway placeholder code in `agent_server.main`
- retired RAG alias exports

## Current Runtime Truth

- API entrypoint: `python -m agent_server.main`
- CEO entrypoint: `powershell -ExecutionPolicy Bypass -File scripts/serve_ceo_llamacpp.ps1 -Port 8082`
- Canonical orchestrator provider: `local_orchestrator`
- Runtime checkpoints: `.f51/checkpoints/latest.json` and `runtime/checkpoints/latest.json`

## Verification Gate

Every future cleanup must pass:

- `python -m ruff check .`
- targeted contract tests for changed modules
- full `python -m pytest tests -q` before local commit
