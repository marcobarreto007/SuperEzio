# F51 Task Board

## Backlog

- [ ] Re-run a browser E2E pass after any future UI changes.

## In Progress

- [x] 2026-06-01 - **Phase 1 (f51-contracts):** Defined `live-modules.contract.md` covering 26 modules. Created 108 new contract tests (all passing): model-serving (13), config (15), crisis (24), trading (16), investor (8), aux-modules (32). Contract coverage now spans 100% of inventory modules.

- [ ] Phase 2 (f51-runtime): Define official runtime — entrypoint config, healthchecks, logs, checkpoints, runbook.
- [ ] Phase 3 (f51-tests): Smoke tests, contract tests, and minimum integration tests for the official runtime.

## Done

- [x] 2026-06-01 - Phase 1 (f51-contracts): Contract definitions + 108 tests passing.
- [x] 2026-05-21 - Removed model build surfaces from the active tree and kept the merged GGUF runtime path.
- [x] 2026-05-21 - Clean tree pass: removed archived runtime/docs surfaces, generic non-F51 skill bundles, retired provider alias path, edge placeholder hooks, and stale F51 map content.
- [x] 2026-05-20 - Frontend/runtime/contracts/tests delivery saved locally.

## Policy

- GitHub is blocked by `.f51/GITHUB_POLICY.json`; do not run `git push`, `git pull`, `git fetch`, or `gh`.
- No archived runtime tree in the active repo.
- No model build pipeline in the active runtime tree.