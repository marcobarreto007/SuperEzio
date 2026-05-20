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

## 2026-05-20 Contract Pass

### CTR-R1 - Runtime metadata drift [MEDIUM]

- Classification: `contract`
- Risk: `config/runtime.yml`, `config/model_manifest.json`, launcher script, and provider factory can drift independently.
- Evidence: Added `tests/contracts/test_contract_runtime_official.py` to cross-check official entrypoints, ports, model path, provider routing, launcher check mode, and checkpoint fields.
- Mitigation: Keep this contract test in the required gate for `/f51-contracts` and `/f51-runtime`.

### CTR-R2 - Agent server public route drift [MEDIUM]

- Classification: `contract`
- Risk: Browser/API clients depend on stable routes such as `/health`, `/task/submit`, `/product/manifest`, and `/api/sdca/evaluate`.
- Evidence: Added `.f51/contracts/agent-server.contract.md`; contract tests now verify registered FastAPI paths from the live app object.
- Mitigation: Any route rename/removal must update the contract and tests in the same patch.

### RT-R1 - Checkpoint schema regression [MEDIUM]

- Classification: `runtime`
- Risk: Rewriting `runtime/checkpoints/latest.json` can accidentally drop fields required by downstream tests or operators.
- Evidence: `tests/contracts/test_contract_runtime_official.py` initially failed when `runtime_parameters` was missing.
- Mitigation: `runtime_parameters` is restored and now covered by the official runtime contract test.

### RT-R2 - Live runtime not yet proven in this pass [MEDIUM]

- Classification: `runtime`
- Risk: Docs and offline contracts can pass while CEO/API are not currently running.
- Evidence: Mitigated in `/f51-tests`; `tests/test_integration_runtime.py` passed 7 live tests against CEO/API on 2026-05-20.
- Mitigation: Keep this risk as a watch item because future runs still need live health proof, not only open ports.

### RT-R3 - Runtime provider naming is misleading [LOW]

- Classification: `runtime`
- Risk: Provider name `primary_external` currently routes to the local CEO endpoint in the official runtime, while `deepseek` remains the cloud expert provider.
- Evidence: Direct `/health/details` showed `primary_external` base URL as `http://127.0.0.1:8082/v1`; `config/runtime.yml` and runbook now document this instead of hiding it.
- Mitigation: Rename/refactor provider labels only in a separate product/config cleanup pass; do not mix with contract/runtime/test hardening.
