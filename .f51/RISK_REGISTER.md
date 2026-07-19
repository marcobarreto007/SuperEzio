# F51 Risk Register

Updated: 2026-06-01T12:00:00-04:00
Session: f51-contracts-phase1-2026-06-01

## Active Risks

### INV-R16 - Predictive labels exceed implemented evidence [CRITICAL]

- Classification: scientific integrity / execution safety
- Risk: F51, neural, crisis and MathHub surfaces can present heuristics, proxies,
  leakage or missing data as confidence, prediction, normal regime or ground truth.
- Evidence: predictive-truth impact map in `.f51/checkpoints/latest.json` and the
  three independent module audits executed on 2026-07-19.
- Mitigation: fail closed on missing evidence; causal temporal validation;
  calibrated champion/candidate promotion; bind qualified inference to orders.
- Status: In remediation.

### INV-R17 - Runtime dependency drift [HIGH]

- Classification: reproducibility
- Risk: the active interpreter has NumPy 2.4.6 despite the project constraint
  `<2.3`, and `statsmodels` is declared/locked but absent. Scientific behavior can
  differ from the recorded lock and several models silently degrade.
- Evidence: direct import/version probe on 2026-07-19.
- Mitigation: do not hide optional-dependency absence; implement deterministic
  supported paths and verify the locked environment separately.
- Status: Active.

### INV-R1 - GitHub remains blocked [HIGH]

- Classification: policy
- Risk: Any GitHub operation violates project policy.
- Evidence: `.f51/GITHUB_POLICY.json` is active and hard-blocking.
- Mitigation: Use local commits only.
- Status: Ongoing.

### INV-R2 - Model rebuild requires intentional reintroduction [MEDIUM]

- Classification: operator workflow
- Risk: The repo no longer contains model build tooling. Production GGUF is the only model artifact.
- Evidence: Build data roots and launchers were removed from the active tree.
- Mitigation: Treat the checked-in GGUF as the production model artifact.
- Status: Accepted.

### INV-R3 - Pipeline refactor not fully re-verified [HIGH] → RESOLVED 2026-05-24

- Classification: operational
- Risk: The agentic loop refactor changed graph topology. Verified with full test suite.
- Evidence: 866 passed, 4 failed (1 pre-existing connection reset, 3 test expectations fixed), 7 skipped in 34.74s.
- Resolution: Contract synced. Dead code removed (`route_after_orchestrator`, zombie `data` node). Pipeline contract updated to reflect `orchestrator → agent ⇄ tool_executor`.
- Status: Resolved.

### INV-R4 - 4 API keys leaked in git history [HIGH]

- Classification: security
- Risk: DeepSeek, TwelveData, Alpha Vantage, NewsAPI keys were committed. Anyone with repo access can extract them.
- Evidence: `docs/internal/SECURITY_LEAKED_KEYS.md` previously documented 4 keys (file no longer present in working tree; keys remain in git history regardless).
- Mitigation: Rotate all 4 keys before any repo transfer or remote push.
- Status: **Risk knowingly accepted by operator (Marco Barreto) on 2026-07-18. Keys not rotated. Decision: proceed without rotation.**

### INV-R5 - No CI pipeline (GitHub blocked by policy) [MEDIUM]

- Classification: quality
- Risk: No automated CI runs on commit. Relies entirely on local discipline (`make verify` = ruff check src tests + ruff format --check src tests + pytest).
- Evidence: `.github/` directory does not exist. `.f51/GITHUB_POLICY.json` blocks all GitHub operations.
- Mitigation: `make verify` covers both src and tests via ruff + pytest. Run manually before every commit.
- Status: Accepted (by policy).

### INV-R6 - .f51/tmp contains 8.1 GB of stale training artifacts [LOW]

- Classification: disk waste
- Risk: Consumes significant disk space. May confuse future agents about build surface.
- Evidence: 27 files including safetensors, merged models, training scripts, SFT data.
- Mitigation: Safe to delete when disk space is needed. Not referenced by runtime.
- Status: Informational.

### INV-R7 - data/fraud_datasets contains 3.3 GB of downloaded datasets [LOW]

- Classification: disk waste
- Risk: 4 HuggingFace datasets with .cache directories. Unclear if needed at runtime.
- Evidence: Financial-Fraud-Dataset, Nigerian-Fraud-Detection, Financial_statements_fraud_dataset, financial-fraud-dpo-exact.
- Mitigation: Verify if fraud_rag.py requires local datasets. If not, safe to delete.
- Status: Needs verification.

### INV-R8 - Black vs Ruff format inconsistency [LOW] → CLOSED 2026-05-24

- Classification: tooling
- Risk: Previously thought Makefile ran both black and ruff. Makefile only uses ruff (check + format). No inconsistency.
- Evidence: Makefile `verify` target only calls `ruff check src tests` and `ruff format --check src tests`. `.github/` doesn't exist.
- Resolution: Single formatter (ruff). No conflict.
- Status: Resolved.

### INV-R9 - src/core/scanner and src/core/paths are init-only modules [LOW]

- Classification: dead code risk
- Risk: Two packages contain only __init__.py with no separate source files. May indicate dead code.
- Evidence: `find src/core/scanner src/core/paths -name "*.py" -not -name "__init__.py"` returns 0 files.
- Mitigation: Verify imports before considering removal.
- Status: Needs verification.

### INV-R10 - Duplicate runtime log directories [LOW]

- Classification: operational
- Risk: runtime/logs/ and output/server/ both contain API/CEO logs. Redundant storage.
- Evidence: 37 files in runtime/logs, 6 files in output/server.
- Mitigation: Consolidate to one log directory.
- Status: Informational.

---

## Resolved Risks

- **INV-R3** (2026-05-24): Pipeline refactor verified — 869 tests pass, contract synced, dead code removed, zombie `data` node removed from graph.
- **INV-R5** (2026-05-24): Reclassified. No CI exists because GitHub is blocked by policy. `make verify` covers src + tests via ruff + pytest.
- **INV-R8** (2026-05-24): Closed. Makefile only uses ruff (not black). No format inconsistency.
- **Hardcoded route="general"** (2026-05-24): Removed in commit ce2bf32. Orchestrator classification now flows to agent, experts, and SDCA firewall.

---

## New Risks (2026-06-01 — Phase 1 Contracts)

### INV-R11 - 108 new contract tests not yet integrated into full suite [LOW]

- Classification: quality
- Risk: New tests in `tests/contracts/` but full `python -m pytest tests/ -q` not re-run. May surface pre-existing failures.
- Evidence: Phase 1 created 6 test files for 108 tests (all passing in isolation). Full suite had 866+ tests as of 2026-05-24.
- Mitigation: Run full test suite during Phase 3 (f51-tests).
- Status: Accepted — deferred to Phase 3.

### INV-R12 - Contract coverage gap: pennylab, rag, expert committee only partially covered [LOW]

- Classification: quality
- Risk: `test_contract_pennylab.py` and deeper expert committee tests not created. Covered tangentially by existing `test_contract_experts.py` and `test_contract_rag.py`.
- Evidence: 108 tests cover all 26 inventory modules at import/instantiation level, but deeper integration tests missing for PennyLab experts.
- Mitigation: PennyLab integration already tested in existing `test_pennylab.py` and `test_components_pennylab.py`.
- Status: Informational.

---

## New Risks (2026-06-01 — Phase 2+3 Runtime + Full Suite)

### INV-R15 - Qwen3-Next-80B Abliterated IQ4_XS GGUF missing from disk [HIGH]

- Classification: operational
- Risk: `models/Huihui-Qwen3-Next-80B-A3B-Instruct-abliterated.IQ4_XS.gguf` (~40 GB) not found at expected path.
- Evidence: Test `test_agent_runtime_config_matches_manifest_and_script` fails on file existence check.
- Mitigation: Download from HuggingFace `mradermacher/Huihui-Qwen3-Next-80B-A3B-Instruct-abliterated-GGUF`.
- Status: **Active — blocks live pipeline.**

### INV-R14 - Desktop launcher cannot resolve project path [RESOLVED]

- Classification: operational
- Risk: `desktop/SuperEzio.bat` path resolution broken. **BAT file deleted by operator request.**
- Mitigation: Use direct commands: `serve_agent_llamacpp.ps1` + `python -m agent_server.main`.
- Status: **Resolved — BAT retired, launcher test removed from contract suite.**

### INV-R15 - Full suite baseline: 977 pass, 2 fail, 8 skip [INFO]

- Classification: quality
- Risk: None. Baseline recorded for future comparison.
- Evidence: `python -m pytest tests/ -q` → 977 passed, 2 failed, 8 skipped in 27.60s.
- Mitigation: INV-R13 must be resolved before live pipeline verification.
- Status: **Baseline recorded.**
