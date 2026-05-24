# F51 Risk Register

Updated: 2026-05-24T11:15:00-04:00
Session: arqueologist-cleanup-risk-resolution

## Active Risks

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
- Evidence: `docs/internal/SECURITY_LEAKED_KEYS.md` documents 4 keys.
- Mitigation: Rotate all 4 keys before any repo transfer or remote push.
- Status: Pending key rotation.

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
