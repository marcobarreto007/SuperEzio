# Swarm — Full Army Audit

Goal: $ARGUMENTS

## Execution Plan

### Phase 1: Reconnaissance (parallel)
Run these agents simultaneously:
1. **recon-researcher** — map architecture, entrypoints, orphans
2. **runtime-verifier** — health checks, ports, GPU, processes
3. **api-contract-verifier** — validate all public contracts

### Phase 2: Deep Audit (parallel)
4. **security-reviewer** — secrets, vulns, attack vectors
5. **code-quality-reviewer** — lint, dead code, complexity
6. **training-verifier** — classify scripts, validate checkpoints
7. **frontend-ux-reviewer** — browser smoke, accessibility
8. **kb-domain-reviewer** — domain accuracy, doc consistency

### Phase 3: Meta-Evaluation (sequential)
9. **agent-explorer** — evaluate agent quality, detect duplication
10. **savekeeper** — integrate findings, update truth docs

## Rules
- Every claim needs evidence (file:line or command output)
- No shared write ownership — only savekeeper writes to docs
- No secrets/raw photos/models in git
- Final result must pass gates or state blockers
- Checkpoint mandatory: `.f51/checkpoints/latest.json` updated

## Stop Conditions
- Server unreachable → report blocker, do not proceed
- GitHub policy violation detected → halt, report
- Critical security finding → halt, report immediately
- 3+ agents report same issue → escalate to orchestrator

## Output
Consolidated report with:
- Executive summary (3-5 bullets)
- Findings by category (security, quality, runtime, contracts, frontend, KB)
- Risk register update
- Recommended next action
