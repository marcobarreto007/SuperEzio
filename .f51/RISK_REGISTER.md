# F51 Risk Register

Updated: 2026-05-21T20:30:00-04:00
Session: f51-inventory-full-sweep

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

### INV-R3 - Pipeline refactor not fully re-verified [HIGH]

- Classification: operational
- Risk: The agentic loop refactor (commit 2c52405) changed graph topology. Checkpoint says "next step: run tests and verify UI behavior" — unconfirmed.
- Evidence: `.f51/checkpoints/latest.json` next_step field.
- Mitigation: Run full test suite and manual E2E pass before declaring stable.
- Status: Action required.

### INV-R4 - 4 API keys leaked in git history [HIGH]

- Classification: security
- Risk: DeepSeek, TwelveData, Alpha Vantage, NewsAPI keys were committed. Anyone with repo access can extract them.
- Evidence: `docs/internal/SECURITY_LEAKED_KEYS.md` documents 4 keys.
- Mitigation: Rotate all 4 keys before any repo transfer or remote push.
- Status: Pending key rotation.

### INV-R5 - CI only tests and lints tests/, not src/ [MEDIUM]

- Classification: quality
- Risk: Source code quality is not gated by CI. Lint violations in src/ go undetected.
- Evidence: `.github/workflows/ci.yml` runs `ruff check tests` and `ruff format tests`, not `src`.
- Mitigation: Extend CI to lint src directory.
- Status: Known gap.

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

### INV-R8 - Black vs Ruff format inconsistency [LOW]

- Classification: tooling
- Risk: Makefile runs both `ruff check` and `black --check`, but CI only runs ruff. Format drift possible.
- Evidence: Makefile verify target vs `.github/workflows/ci.yml`.
- Mitigation: Standardize on ruff for both local and CI.
- Status: Informational.

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

_(None resolved this session.)_
