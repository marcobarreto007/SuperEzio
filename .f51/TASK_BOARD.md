# F51 Task Board

## Backlog

- [ ] Re-run a browser E2E pass after any future UI changes.
- [x] 2026-07-19 - Independent verification (Claude Code) of a separate large session
  ("codex", session organism-truth-remediation, 28 commits af84440..dfff247) that built
  directly on top of my crisis-scale fix (63978d9) and grounding-guard fix (c53daf4).
  That session implemented exactly the "organism that learns from real outcomes" gap I had
  flagged but not built: terminal-outcome-only learning ledger, deterministic weighted
  expert consensus, a single shared adaptive execution policy across all order paths, atomic
  crash-safe persistence, pickle-free RAG, and closed the gate_metadata/raw-CLI bypass an
  earlier external audit had flagged as P0. Independently re-ran and confirmed (not just
  trusted the report): full suite 1452 passed/0 failed/11 skipped, ruff check clean, ruff
  format clean (355 files), 38/38 broker+gate contract tests passed. See
  docs/audit/phase10_organism_truth_and_remediation_2026-07-19.md for that session's full
  report — its "Honest residual limits" section is worth reading before assuming predictive
  quality is proven (it explicitly is not — only the causal/risk accounting is).

## In Progress

- [x] 2026-06-01 - **Phase 1 (f51-contracts):** Defined `live-modules.contract.md` covering 26 modules. Created 108 new contract tests (all passing): model-serving (13), config (15), crisis (24), trading (16), investor (8), aux-modules (32). Contract coverage now spans 100% of inventory modules.

- [x] 2026-06-01 - **Phase 2 (f51-runtime):** Runtime verified. Entrypoints confirmed: CEO :8082 (llama.cpp), API :8002 (FastAPI). Healthchecks: /health, /health/details, /metrics. Logs: runtime/logs/. Checkpoints: runtime/checkpoints/latest.json. Runbook: docs/runbooks/RUNBOOK.md.

- [x] 2026-06-01 - **Phase 3 (f51-tests):** Full suite: 977 passed, 2 failed (pre-existing: CEO GGUF offline, launcher path), 8 skipped in 27.60s. Smoke + contract + integration coverage confirmed. No fake tests.

## Done

- [x] 2026-07-19 - **Predictive truth modernization (Codex + 3 deep subagents):**
  removed fixed/random predictive evidence; corrected causal RSI/MACD, HRP and return
  bootstrap; rebuilt crisis HMM/Hawkes/GaR/LPPLS with honest insufficient-data states;
  built a persistent causal three-class neural champion with chronological gaps,
  train-only scaling, OOS baseline gates, temperature calibration, split conformal
  abstention and safe artifacts; bound singleton neural evidence to paper/broker order
  entry; made terminal outcomes update expert weights through directional multiclass
  Brier skill with shrinkage; retired random pseudo-RL actions. Full verification:
  `1532 passed, 11 skipped, 0 failed`, Ruff clean, live browser smoke clean. Honest
  remaining data/runtime limits are in
  `docs/audit/predictive_truth_modernization_2026-07-19.md` and the durable checkpoint.

- [x] 2026-07-19 - 4 parallel subagent fixes + critical security findings (Claude Code):
  launched 4 subagents in parallel, each with exclusive file scope, no conflicts. Fixed:
  F51 spider_sense hardcoded evidence + critic fail-open (4bda75c), DataHub accepting
  empty {} as usable result + exec() in custom_tools audited/reinforced with 18 tests
  (ea63541), expired IBKR apprenticeship date now resolved by real date comparison
  (10490cf), root cause of red_team KeyError('provider') found (double-formatting an
  already-resolved f-string) + SDCA _truthy_high inverted "low" logic (d8ca01b). Full
  suite after merge: 1402 passed, 0 failed, 11 skipped. Verified live: red_team no longer
  crashes (now fails on legitimate strict_json_validation_failed), f51_unified status=ok,
  consumer-facing test ("I'm new to investing...") produced an honest, complete,
  non-fallback response. CRITICAL, NOT fixed per explicit operator instruction to stop
  touching anything token/secret-related: real Hugging Face token exposed in 6 files
  under F51-Nitro-MoE/ (only 2 known before this session; found 4 more), and
  np.load(allow_pickle=True) in src/core/rag/engine.py:388 (arbitrary code execution risk
  if the RAG index file is tampered with). See docs/audit/phase9_parallel_fixes_and_critical_findings.md.
  Operator must revoke the HF token; pickle fix awaits explicit go-ahead. A separate
  external audit also reported several ALTO/MEDIO findings (no API auth, paper-order
  default-on flag, crisis.py scale mixing, etc.) — NOT independently verified this
  session, do not act on them without checking first.
- [x] 2026-07-19 - Live end-to-end verification + F51 critical fix (Claude Code): started
  the real server (agent_server.main), opened the real UI, and submitted real requests via
  /task/submit. Found and fixed a bug invisible to unit tests: math_hub.py called
  DecisionFactors(risk=...) but the class has no 'risk' field (it's 'danger') — every real
  invocation of the F51 verdict engine raised TypeError and silently returned
  status=error. Confirmed live before/after via identical requests. Also confirmed the
  autonomous MAN_AT_WORK safety mode works correctly (blocks all trading when CEO is
  unreachable, without being asked to). Found remaining live bug: KeyError('provider') in
  red_team_agent_* roles (not yet root-caused — reproduction outside the real LangGraph
  runnable context fails differently). Wrote docs/audit/ROADMAP_CONSULTANT.md reframing the
  project's goal per operator direction: a real-time natural-language financial consultant,
  not an automated trading system. Documents the full verified request flow and what
  specifically blocks that goal (no LLM provider configured, no local CEO GGUF present).
  Full suite: 1367 passed, 0 failed, 11 skipped. Commits 632a43f, 4bdc248.
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
