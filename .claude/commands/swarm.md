# Swarm — Risk-Selected Product Delivery

Goal: $ARGUMENTS

## Execution Plan

### Phase 0: Slice (sequential)

1. **product-delivery-orchestrator** — outcome, non-goals, Given/When/Then, ownership, risks

### Phase 1: Reconnaissance (parallel only when independent)

2. **recon-researcher** — architecture, entrypoints and impact
3. **runtime-verifier** — liveness/readiness on API 8002 and CEO 8080
4. **api-contract-verifier** — public contract impact

### Phase 2: Implementation (sequential)

5. **product-implementer** — one approved ticket, explicit files, targeted regression

### Phase 3: Independent verification (risk-selected)

6. **ai-eval-verifier** — agent/output regression and baselines
7. **security-reviewer** — auth, secrets and financial surface when affected
8. **api-contract-verifier** — API/schema when affected
9. **frontend-ux-reviewer** — browser journey when affected

### Phase 4: Operate, release and save (sequential)

10. **reliability-sre-operator** then **runtime-verifier** — recovery and independent health
11. **release-readiness-manager** — reproducible candidate or BLOCK
12. **savekeeper** — durable truth after evidence

## Rules

- Every claim needs evidence (file:line or command output).
- Do not dispatch all agents when risk does not require them.
- Product implementer owns product files; savekeeper owns truth docs.
- Implementer cannot verify or release its own patch.
- No secrets, operator data, models or broker credentials in delivery artifacts.
- GitHub is blocked; local commits are scoped.
- Capital, TD credentials and real-money go-live require the human operator.

## Stop Conditions

- Missing acceptance criteria or file ownership → do not implement.
- Server unreachable → SRE runbook or blocker; never hide with a mock.
- Critical security/contract/eval finding → return to implementer.
- Same failure repeated twice → stop the loop and record a blocker.
- Any real-money action → stop for explicit human authority.

## Output

- Slice and acceptance criteria
- File ownership and agents selected by risk
- Original gate evidence
- Release candidate or explicit BLOCK
- Checkpoint and scoped local commits
