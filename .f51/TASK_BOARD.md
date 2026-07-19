# F51 Task Board

## Backlog

- [ ] Re-run a browser E2E pass after any future UI changes.

## In Progress

- [x] 2026-06-01 - **Phase 1 (f51-contracts):** Defined `live-modules.contract.md` covering 26 modules. Created 108 new contract tests (all passing): model-serving (13), config (15), crisis (24), trading (16), investor (8), aux-modules (32). Contract coverage now spans 100% of inventory modules.

- [x] 2026-06-01 - **Phase 2 (f51-runtime):** Runtime verified. Entrypoints confirmed: CEO :8082 (llama.cpp), API :8002 (FastAPI). Healthchecks: /health, /health/details, /metrics. Logs: runtime/logs/. Checkpoints: runtime/checkpoints/latest.json. Runbook: docs/runbooks/RUNBOOK.md.

- [x] 2026-06-01 - **Phase 3 (f51-tests):** Full suite: 977 passed, 2 failed (pre-existing: CEO GGUF offline, launcher path), 8 skipped in 27.60s. Smoke + contract + integration coverage confirmed. No fake tests.

## Done

- [x] 2026-07-19 - Safety gate unification (Claude Code): fixed CRITICAL gap from
  phase6 audit — F51_TRADING_EXECUTION_FREEZE and SUPEREZIO_LIVE_TRADING_DISABLED
  were independent, non-communicating safety families. is_execution_frozen() now
  checks both; SUPEREZIO_LIVE_TRADING_DISABLED default changed False -> True
  (fail-safe). Fixed 1 test that relied on the old unsafe default. Full suite:
  1367 passed, 0 failed, 11 skipped. Commit 47404b2. Also folded in phase5-8
  audit reports (F51/SDCA/Neural, RAG/PennyLab/execution, idempotency/security,
  executive summary) produced by a separate agent run via
  docs/audit/SUBAGENT_RESEARCH_PROMPT.md, plus scripts/questrade_order_assist.py
  (Playwright fills the Questrade order ticket, never clicks submit/confirm —
  that stays a human action in the real browser window).
- [x] 2026-07-19 - Component-by-component audit (Claude Code): 4 phases documented in
  `docs/audit/phase1-4b`. Confirmed and fixed: quantum_module fixed RNG seed (math_hub.py),
  f51_module hardcoded consensus=0.65, silent gateway fallback with no opt-out on the sync
  expert path, and all experts/judge/auditor sharing identical unfiltered data_context.
  Rewrote EXPERT_PROMPTS with per-role data isolation (EXPERT_CONTEXT_MODULES) and
  build_judge_context(), informed by TradingAgents (arXiv:2412.20138), FinRobot
  (arXiv:2405.14767), AIMM (arXiv:2512.16103). runtime.yml context_length divergence
  (4096 vs 65536) documented as unverifiable — no GGUF present on disk. Commit 7f77357.
  Full suite: 498 passed, 5 pre-existing failures unaffected, 2 skipped.
- [x] 2026-06-13 - Career bootstrapping: created professional Portuguese & English resumes, LinkedIn strategy, and GitHub portfolio optimization guide under docs/career/.
- [x] 2026-06-01 - Phase 3 (f51-tests): 977/979 pass. 2 pre-existing failures documented in RISK_REGISTER (INV-R13, INV-R14).
- [x] 2026-06-01 - Phase 2 (f51-runtime): Runtime verified with healthchecks, logs, checkpoints, runbook.
- [x] 2026-06-01 - Phase 1 (f51-contracts): Contract definitions + 108 tests passing.
- [x] 2026-05-21 - Removed model build surfaces from the active tree and kept the merged GGUF runtime path.
- [x] 2026-05-21 - Clean tree pass: removed archived runtime/docs surfaces, generic non-F51 skill bundles, retired provider alias path, edge placeholder hooks, and stale F51 map content.
- [x] 2026-05-20 - Frontend/runtime/contracts/tests delivery saved locally.

## Policy

- GitHub is blocked by `.f51/GITHUB_POLICY.json`; do not run `git push`, `git pull`, `git fetch`, or `gh`.
- No archived runtime tree in the active repo.
- No model build pipeline in the active runtime tree.