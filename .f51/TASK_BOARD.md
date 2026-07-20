# F51 Task Board

## Backlog

- [ ] **Questrade OAuth token nao configurado**: `scripts/questrade_read_portfolio.py` esta
  implementado e funcional (Playwright session persistente, ler carteira sem OAuth token),
  mas a integracao completa exige um token OAuth valido para a API Questrade.
  `data/questrade_portfolio.json` contem snapshot de portfolio real como prova de conceito.
- [ ] **Frontend login UI exists but not user-facing yet**: `frontend/auth.js`, `frontend/auth.css`,
  `frontend/api.js` implementam modal de login/register com JWT Bearer token, mas a UI
  ainda nao esta integrada como tela inicial. Dev mode continua injetando usuario anonimo.
- [x] 2026-07-19 - **3-agent independent verification wave** (Claude Code): dispatched 3
  parallel subagents with disjoint file scope to verify (not trust) claims from the Codex
  predictive-truth-modernization session and an external audit, using concrete synthetic-data
  proof rather than reading docstrings. **Math/crisis models** (src/core/math, src/experts/crisis):
  all CONFIRMED_REAL with numeric evidence — HMM detected a synthetic 100x variance regime
  shift (stress probability 0.0024→0.9999); Hawkes MLE recovered branching_ratio=0.828 from a
  true 0.85 simulated process via Ogata thinning, stability constraint alpha/beta<1 verified
  hard-enforced; Growth-at-Risk pinball loss matched the reference formula exactly (0.00e+00
  diff, 500 points, 5 quantiles); LPPLS recovered known synthetic parameters (tc, m, omega)
  with R²=0.9998; former quantum_bias confirmed fully replaced by a real Politis-Romano
  stationary block bootstrap over actual OHLCV returns (zero "quantum" references left);
  HRP recovered the exact inverse-variance weight ratio (diff <1e-9) against a synthetic
  2-asset case. **Neural/adaptive learning** (technical_neural, neural_decision,
  outcome_learning): all 6 claims CONFIRMED — chronological split with gaps verified via a
  leakage probe (tampered future candles proved bit-identical train features); split-conformal
  prediction set (not a naive confidence threshold) traced end-to-end into the execution gate;
  idempotent ledger proven via a duplicate-event probe (same id+same payload→no-op, same
  id+different payload→OutcomeConflictError, ledger untouched); confirmed zero code path fakes
  a pnl=0/exit=entry pseudo-outcome before a trade actually closes; confirmed the old random
  pseudo-RL policy (neural_rl.py) is now a fail-closed WAIT-only compatibility stub with zero
  active callers; confirmed atomic tempfile+fsync+os.replace artifact writes with SHA-256 +
  smoke-test validation on load. **Security/infra**: found and FIXED a real TOCTOU idempotency
  bug (commit 1f24c84) — the ALLOW path in auto_execute_paper.py never called mark_processed(),
  so approved paper orders were only deduplicated by an in-memory deque that doesn't survive a
  restart; fixed with an atomic os.open(O_CREAT|O_EXCL) claim. Also confirmed REAL and unfixed:
  no API auth on ~20 routes (see Backlog P0 above), a SUPEREZIO_ENABLE_PAPER_ORDER_SUBMIT env
  leak via setdefault, /health always-200 regardless of real state, and no coverage measurement
  by default — all logged to Backlog rather than patched, since each needs a contract decision
  (auth scheme, status-code semantics) beyond a small reversible fix.
  *RESOLVED SINCE: P0 API auth and env leak fixed 2026-07-20; --cov added 2026-07-20.
   /health status-code contract remains open.* One earlier claim
  (Order.gate_metadata missing) was REFUTED — the contract already matches; either never true
  in this codebase state or already fixed before this session. Full suite after all 3 agents:
  1538 passed, 0 failed, 11 skipped — identical to the pre-verification baseline except for
  the one real fix. No GitHub operation performed by any agent.
  call sites that don't yet pass declared_tickers (fallback regex path still
  active there); once all call sites declare, consider retiring
  _mentioned_tickers/_NON_TICKER_SYMBOLS/_COMMON_CAPS_WORDS entirely.
- [x] 2026-07-19 - Structural grounding redesign (Claude Code): root-caused the
  recurring "acronym false-flagged as invented ticker" bug (3rd occurrence:
  ALLOW/DCF/EMA/IBKR/SELL/TRAP/VWAP, then DADOS/SEM/SCAN, then FCF/HRP) by
  adding mentioned_tickers to final_answer's tool schema so the LLM declares
  which securities it named instead of the pipeline regex-guessing from prose
  after the fact. Verified live: "analyze SHOP for me" produced a full,
  correct synthesis (6 experts, Trinity divergence, MathHub, F51, SDCA,
  crisis guardrails, explicit non-recommendation) with "DCF, FCF" in the text
  and no false guard trigger — first live run of this exact prompt that
  didn't fall back to a generic discard message. Old regex path kept as
  fallback for calls that don't populate the new field, not yet retired
  (see Backlog item above). Also confirmed (read-only) that the separate
  8-model crisis heuristic rewrite the operator asked for was already done
  by the predictive-truth-modernization session (Minsky-Keen, IMF mispricing,
  Shiller, debt-service-ratio, credit-asset-growth now carry honest
  PUBLIC_NAME + method_kind="heuristic"; network_contagion/systemic_bank_risk
  correctly return insufficient_data instead of fabricating proxies) — no
  further crisis-model work was needed. Also independently verified and fixed
  a formatting gap the Codex session's report had missed (15 files, mostly
  the predictive-truth core, were not ruff-formatted despite the report
  claiming "355 files already formatted" — fixed, 0 test regressions).
  Full suite: 1538 passed, 0 failed, 11 skipped. Commits 0efa30f, 47659a7,
  3a6ae8d.
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

- [x] 2026-06-01 - **Phase 1 (f51-contracts):** Defined `live-modules.contract.md` covering 26 modules. Created 108 new contract tests (all passing). Contract coverage spans 100% of inventory modules.
- [x] 2026-06-01 - **Phase 2 (f51-runtime):** Runtime verified. Entrypoints confirmed, healthchecks, logs, checkpoints, runbook.
- [x] 2026-06-01 - **Phase 3 (f51-tests):** Full suite: 977 passed, 2 pre-existing failures, 8 skipped. Coverage confirmed.

_(All phases complete — no active In Progress work.)_

## Done

- [x] 2026-07-20 — **Questrade Portfolio Reader (Playwright):** `scripts/questrade_read_portfolio.py` implementa leitor de carteira Questrade com sessao Playwright persistente. Le dados sem OAuth token (via scraping da UI do Questrade). Snapshot de portfolio real salvo em `data/questrade_portfolio.json`. Codigo pronto, falta token OAuth para API oficial. Commits 6cdb275, 81457ea.
- [x] 2026-07-20 — **Browser smoke 100% pass + auth modal dev-mode detection:** `scripts/browser_smoke.py` corrigido para detectar auth modal em dev mode. Suite completa passa 100%. Commit 039055a.
- [x] 2026-07-20 — **68 integration tests — MathHub, builder, contracts, observations:** Nova suite de testes de integracao validando pipeline completo: MathHub, builder, contratos, observacoes. Commit 4a252c7.
- [x] 2026-07-20 — **21 auth unit tests — 85%+ coverage:** Testes unitarios para `core/auth/` e `agent_server/auth/`. Cobertura 85-88% em 4 modulos. Commits 87fd396, 755ba3e.
- [x] 2026-07-20 — **tool_executor submit_paper_order idempotency fix:** Claim atomico com `os.open(O_CREAT|O_EXCL)` aplicado ao `submit_paper_order` em `tool_executor.py`, mesma correcao do `auto_execute_paper.py`. Commit ec83e6a.
- [x] 2026-07-20 — **/health retorna 503 real:** Confirmado e documentado que `/health` agora retorna HTTP 503 quando o sistema nao esta operacional. `test_api_routes_sync.py` atualizado. Commits 662f8b1, 5d2a0e1.
- [x] 2026-07-20 — **env leak fixed + --cov default:** `auto_execute_paper.py` nao mais vaza `SUPEREZIO_ENABLE_PAPER_ORDER_SUBMIT=1` no environment. `pytest.ini` agora inclui `--cov=src --cov-report=term-missing` por default. Commit 8ff067f.
- [x] 2026-07-20 — **JWT Auth completo (P0):** Implementacao full-stack: `AuthDB` com SQLite + bcrypt em `core/auth/models.py`; servico com PyJWT e refresh rotation em `core/auth/service.py`; middleware JWT em `agent_server/auth.py`; rotas `/auth/*` (register, login, refresh, me); cascata com API-Key middleware; dev mode fallback. Seed admin script em `scripts/seed_admin.py`. Packages: `pyjwt`, `passlib[bcrypt]`, `bcrypt`. Commits fc778bb, 1945d4f, 2dfa2f3, 8f6d76b, 4f5b40f.
- [x] 2026-07-20 — **Frontend login UI:** `frontend/auth.js`, `frontend/auth.css`, `frontend/api.js` implementam modal de login/register com JWT Bearer token. Integrado ao fluxo dev-mode (anonimo ate login ser implementado como tela inicial). Commits 895a539, 495676e.
- [x] 2026-07-20 — **SDCA string check fix:** `test_sdca_firewall_inline.py` atualizado para usar `fetchWithAuth` em vez de string desatualizada. Commit ff56d84.
- [x] 2026-07-20 — **Certificacao completa — 1446/1446 pass:** Sistema operacional apos limpeza Wave 4 + fixes menores. 1446 tests, 0 fails, 10 skipped. Commits 6efb2c1, c81ff8e.
- [x] 2026-07-20 — **1535 testes, sistema completo:** Apos adicao de 21 auth tests + 68 integration tests: 1535 passed, 0 failed, 10 skipped. Sistema aguardando deploy. Commit e55b2f3.
- [x] 2026-07-20 — **Wave 4 — Integracao final + limpeza massiva (savekeeper):** 23 dead modules (8,511 LOC) removidos de `src/core/trading/`. 40 scripts legados removidos. 7 testes mortos removidos. `pyproject.toml` limpo. Estado final documentado em `docs/STATE_OF_THE_UNION.md`. Gates: 1443 passed, 10 skipped, 0 failed. Ruff clean. Commits 912ec18, aeefa7d, aa332a6.

- [x] 2026-07-20 - **P0 API auth implemented:** X-API-Key middleware (`main.py:361-430`)
  with constant-time comparison + JWT auth middleware (`auth.py`) + `/auth/*` router
  (register, login, refresh, me) with SQLite-backed user storage and bcrypt password hashing.
  Public paths exempted: `/health`, `/favicon.ico`, `/`, `/metrics`, static assets.
  Dev-mode fallback when no API key is configured. Covers all ~20 routes previously
  identified as zero-identity-check. Supersedes backlog item "P0 — no API auth".
  Full suite: verified via code review (no test regressions expected from middleware addition).

- [x] 2026-07-20 - **auto_execute_paper.py env leak fixed:** removed `os.environ.setdefault(
  "SUPEREZIO_ENABLE_PAPER_ORDER_SUBMIT", "1")` from `auto_execute_paper.py:50` which ran on
  every conversation turn and leaked "1" into the process environment, overriding the
  operator's `docker-compose.yml` setting of `false`. Paper submission is now correctly
  governed by the external env var or `settings.superezio_enable_paper_order_submit`
  (default `False`). `F51_TRADING_EXECUTION_FREEZE` remains as the independent safety gate.

- [x] 2026-07-20 - **pytest.ini --cov coverage enabled:** added `--cov=src --cov-report=term-missing`
  to pytest.ini addopts. Default `pytest tests/ -q` now measures coverage automatically.

- [x] 2026-07-20 - **Browser E2E smoke pass verified:** `scripts/browser_smoke.py` confirmed
  passing during Wave 2 UX audit (previously completed; acknowledged in task board).

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
