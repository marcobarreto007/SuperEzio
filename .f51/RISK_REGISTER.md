# F51 Risk Register - SuperEzio

> Atualizado: 2026-05-20T12:03:55-04:00 | Session: f51-inventory-codex-2026-05-20 | Fonte: disk inventory, no product code edits

## Active Inventory Risks
### INV-R1 - .github/ [MEDIUM]

- Classification: `config`
- Risk: Repo contains GitHub workflow/config surface while .f51/GITHUB_POLICY.json says DISK ONLY.
- Mitigation: Keep ignoring GitHub tooling; do not run gh/git push/pull/fetch.

### INV-R2 - Makefile [MEDIUM]

- Classification: `config`
- Risk: Makefile install-deps references requirements.txt, but only requirements-ci.txt is present.
- Mitigation: Next config pass should reconcile install command with pyproject/requirements-ci.

### INV-R3 - src/experts/technical_neural/expert/ [MEDIUM]

- Classification: `core`
- Risk: Subpackage has Python files but no __init__.py, which can break package imports.
- Mitigation: Contracts/refactor pass can add a minimal __init__.py if import path is intended.

### INV-R4 - .env [HIGH]

- Classification: `config`
- Risk: .env exists on disk and was intentionally not read by inventory; treat as potential secret-bearing local file.
- Mitigation: Keep gitignored, avoid screenshots/log dumps, rotate keys if exposure is suspected.

### INV-R5 - .f51/tmp/mamba-ssm-src/ [MEDIUM]

- Classification: `experimental`
- Risk: Operational tmp contains nested third-party source and its own .git metadata; can confuse searches/inventory and bloat disk.
- Mitigation: Do not delete in this task; audit separately before cleanup.

### INV-R6 - .env.example [MEDIUM]

- Classification: `config`
- Risk: 70 env-like names appear in code/docs but not in .env.example.
- Mitigation: Run config/contracts pass to distinguish real env vars from constants and document the real ones.

### INV-R7 - repository [LOW]

- Classification: `duplicate`
- Risk: 46 exact duplicate content groups found among small scanned files.
- Mitigation: Use duplicate map before refactor; avoid deleting until contracts prove canonical owners.

## Regression Notes
- No product code was edited.
- No product tests were run during inventory generation; only artifact validation should be trusted for this turn.
- GitHub is blocked by `.f51/GITHUB_POLICY.json`; do not use `gh`, `git push`, `git pull`, or `git fetch`.
