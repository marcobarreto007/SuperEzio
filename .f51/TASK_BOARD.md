# F51 Task Board

## Backlog

- [ ] Reconcile Makefile install target with `pyproject.toml` / `requirements-ci.txt`.

## In Progress

- [ ] None.

## Blocked

- [ ] None.

## Done

- [x] 2026-05-20 - `/f51-contracts`: added live `agent_server` contract, aligned runtime provider config, and added official runtime contract tests.
- [x] 2026-05-20 - `/f51-runtime`: updated official runbook, logs/checkpoint definition, runtime config, and checkpoint contract.
- [x] 2026-05-20 - `/f51-tests`: contracts 167 passed, runtime smoke 20 passed, live integration 7 passed, ruff check/format passed.
- [x] 2026-05-20 - Arqueologist cleanup: renamed `primary_external` to `local_orchestrator`, reconciled model manifest token metadata, and preserved a legacy alias.
- [x] 2026-05-20 - Arqueologist cleanup: archived legacy Gemma training scripts and removed duplicated `.f51/tmp` build trees/logs.
- [x] 2026-05-20 - Tree cleanup: saved local backup, removed ignored caches/scratch, removed stale tracked Playwright snapshot, removed unreferenced untracked prompt draft, and preserved registered frontend-design skill files.
- [x] 2026-05-20 - Operational F51 layer revalidation, 8 skill standardization, checkpoint/report update.
- [x] Phase 3: f51-tests - smoke (20), contract (158), integration (5 pass, 2 skip with 500). 183/185 passing.
- [x] Phase 2: f51-runtime - runtime.yml updated, RUNBOOK.md precise, runtime/checkpoints/latest.json created.
- [x] Phase 1: f51-contracts - 6 contracts (.f51/contracts/) + 4 test files (158 contract tests passing).
- [x] NLP intent pipeline correction against fake ticker hijack.
- [x] Clean local CEO launch and live tests completed.
- [x] Orphan folder cleanup and legacy engine resolution.
- [x] Operational contracts and port-runtime tests hardening.
- [x] Initial operational bootstrap.
- [x] Inventory mapping and TEST_MAP / DUPLICATE_MAP creation.
- [x] Runtime definition and official RUNBOOK creation.
- [x] Contract verification and 22 local tests executed.

## Policy

- One main task at a time.
- No new front without checkpoint.
- GitHub is blocked by `.f51/GITHUB_POLICY.json`; do not run `git push`, `git pull`, `git fetch`, or `gh`.
