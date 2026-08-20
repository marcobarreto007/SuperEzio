# Delivery Checklist

Date: 2026-05-21

> **HISTORICO / SUPERSEDED.** Esta checklist preserva o gate de 2026-05-21. Para entrega atual use `docs/runbooks/DELIVERY_CHECKLIST_v3.md` e `docs/runbooks/RUNBOOK.md`.

## Required Before Delivery

- [ ] `git status --short` reviewed.
- [ ] `.f51/GITHUB_POLICY.json` confirmed as disk-only.
- [ ] `python -m ruff check .` passes.
- [ ] `python -m pytest tests -q` passes.
- [ ] Live runtime endpoints checked when API/CEO behavior changed:
  - `http://127.0.0.1:8082/health`
  - `http://127.0.0.1:8082/v1/models`
  - `http://127.0.0.1:8002/health`
  - `http://127.0.0.1:8002/health/details`
- [ ] `.f51/checkpoints/latest.json` updated.
- [ ] `runtime/checkpoints/latest.json` updated for runtime-facing changes.
- [ ] Local commit created when Marco asks to save.

## Blockers

- Do not use GitHub commands or GitHub connectors.
- Do not reintroduce archived runtime trees.
- Do not add generic tool bundles under `.claude/skills`; keep that directory project-scoped.
