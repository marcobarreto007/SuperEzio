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

## 2026-05-20 Bob Unified Frontend

### UI-R1 - Legacy panel assets can re-enter first viewport [LOW]

- Classification: `frontend`
- Risk: The old drawer-based system panels made the UI look operationally noisy and could drift from the new Bob/market workspace.
- Evidence: Removed the legacy panel drawer and deleted unused panel assets: `frontend/css/panels.css`, `frontend/js/metrics.js`, `frontend/js/manifest.js`, `frontend/js/neural-logs.js`, `frontend/js/capabilities.js`, and `frontend/js/journal.js`.
- Mitigation: Added `test_frontend_contract_uses_bob_unified_workspace_without_legacy_panels` to block reloading those assets.

### UI-R2 - Bob chat session rate-limit contamination [MEDIUM]

- Classification: `runtime`
- Risk: A fixed browser `session_id` can make unrelated users/prompts share rate-limit and memory behavior.
- Evidence: Replaced the fixed `sz-session` frontend payload with browser-local generated session IDs and proved `/task/submit` streamed `STREAM_START`, pipeline events, `CHUNK`, and `STREAM_END`.
- Mitigation: Keep the contract test checking that `session_id: "sz-session"` is not present in `frontend/js/init.js`.

### UI-R3 - SSE streams can look idle until a producer emits [LOW]

- Classification: `streaming`
- Risk: `/neural/logs` can return no bytes until model activity occurs, which may look broken if checked before a task runs.
- Evidence: Initial 8s stream read was idle; after `/task/submit`, `/neural/logs` emitted `NEURAL_LOG` entries for `local_orchestrator` and `ceo`.
- Mitigation: Stream validation should include a producer action before judging `/neural/logs`.

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

### RT-R3 - Legacy provider alias preserved [LOW]

- Classification: `runtime`
- Risk: Old callers may still request `primary_external`.
- Evidence: Runtime provider was renamed to `local_orchestrator`; `ModelGateway` maps the legacy alias to the new canonical name.
- Mitigation: Keep alias until historical tests/tools stop using the old name.

## 2026-05-20 Arqueologist Cleanup

### ARC-R1 - Archived Gemma scripts are historical only [LOW]

- Classification: `legacy`
- Risk: Legacy Gemma training scripts still contain old Gemma paths inside archived instructions.
- Evidence: `scripts/finetune_gemma_sft.py` and `scripts/vastai_setup_gemma.sh` were moved to `archive/experimental/training/legacy_gemma/`.
- Mitigation: Do not use archived Gemma scripts as current runtime/training truth.

### ARC-R2 - `.f51/tmp` cleanup was intentionally partial [LOW]

- Classification: `cleanup`
- Risk: Some `.f51/tmp` training artifacts remain because they may be useful for local training provenance.
- Evidence: Removed only duplicated third-party build trees and build logs; preserved `merge_adapters.py`, local SFT JSONL, phase1 adapter, and merged tokenizer artifacts.
- Mitigation: Delete more `.f51/tmp` artifacts only after a separate training provenance audit.

## 2026-05-20 Tree Cleanup

### TREE-R1 - Skill registration files are product-adjacent [LOW]

- Classification: `cleanup`
- Risk: `.agents/skills/frontend-design/`, `.claude/skills/frontend-design/`, and `skills-lock.json` can look like clutter, but `.f51/SKILLS_CHECK.md` documents them as the registered frontend-design skill.
- Evidence: `git ls-files` shows the skill files are tracked; `rg frontend-design .f51 .claude .agents skills-lock.json docs` links them to the F51 skill check.
- Mitigation: Preserved these files. Remove only in a dedicated skill de-registration pass.

### TREE-R2 - Deleted local scratch/cache artifacts are recoverable [LOW]

- Classification: `cleanup`
- Risk: Local scratch scripts, Playwright/cache artifacts, and an unreferenced untracked prompt draft were removed from the active tree.
- Evidence: Created local backup `C:\Users\marco\Desktop\SuperEzio_LOCAL_BACKUPS\pre-tree-audit-20260520-140340.zip` before deletion.
- Mitigation: Restore from the backup if any removed scratch/prompt artifact is needed.

### TREE-R3 - Stale Playwright snapshot was tracked [LOW]

- Classification: `cleanup`
- Risk: `.playwright-cli/page-2026-05-11T02-42-03-389Z.yml` was versioned despite being a dated browser snapshot with no references.
- Evidence: `git log -- .playwright-cli/page-2026-05-11T02-42-03-389Z.yml` showed initial import; `rg ".playwright-cli|page-2026-05-11" .` found no active references.
- Mitigation: Removed the snapshot and added `.playwright-cli/` to `.gitignore` to prevent recurrence.
