# Phase 10 — Organism truth and remediation

Date: 2026-07-19  
Scope: crisis math, data routing, adaptive learning, expert consensus, execution, persistence, grounding, runtime, frontend, and repository gates.  
Credential policy: no credential file, secret value, or credential configuration was read or changed.

## Executive verdict

The project now implements the intended authority hierarchy: deterministic data, math, evidence, and risk policy are primary; LLMs are assistants. The organism can continue measuring, recording, blocking, and adapting when an LLM provider is absent. A generated recommendation has no direct path around the shared execution policy.

Before remediation, several important pieces existed but did not form a reliable closed loop. Crisis values mixed percentages and unit intervals, order submission could be mistaken for learning success, duplicate outcomes could be replayed, learned expert weights did not consistently control execution, some submit paths bypassed shared policy, provider routing accepted structurally empty payloads, and RAG persistence trusted pickle-capable files. Those gaps are closed and covered by tests.

This is not a claim that financial predictions are guaranteed. It is a claim that the software now preserves causal accounting and risk invariants while it tries to improve predictions from past terminal outcomes and current validated evidence.

## Real architecture

```text
Market providers ---> capability validation ---> observations
                                                   |
Historical outcomes ---> durable outcome ledger    |
          |                                        v
          +--> expert reliability ----------> math + deterministic consensus
                                                   |
LLM assistants ---> interpretations/debate --------+
                                                   |
                                                   v
                         shared adaptive execution policy
                         | consensus | stop | size | freeze |
                                                   |
                                      BLOCK or paper execution
                                                   |
                                        terminal close only
                                                   |
                                      reward + causal attribution
                                                   |
                                      updated durable reliability
```

## Findings and remediation

### 1. Crisis math had conflicting units

Problem: classifiers and consumers mixed `[0, 1]` values with percentage-like values. Status labels could disagree with severity, and ensemble confidence rewarded incomplete coverage.

Remediation:

- Crisis contracts strictly bound scores and confidence to `[0, 1]`.
- Severity is derived from the canonical score rather than a conflicting status field.
- All crisis models and consumers use the same unit interval.
- Ensemble confidence combines mean confidence with sensor coverage.
- Property tests exercise 1,000 generated inputs plus high-risk end-to-end cases.

Primary commit: `af84440`.

### 2. The adaptive loop learned too early

Problem: order submission was treated as positive feedback even though no profit or loss existed. That creates self-confirming weights and corrupts causal learning.

Remediation:

- Learning occurs only when a trade reaches a terminal outcome.
- The terminal outcome ledger uses SQLite transactions and immutable event IDs (`trade_id:v1`).
- Duplicate events are idempotent; conflicting hashes are rejected.
- Reward uses ex-ante risk, fees, and slippage.
- Decision confidence, risk, and expert attribution survive through the paper journal.
- Closed trades are projected once into XP and expert reliability.

Primary commits: `8203107`, `cf1ab7e`, `2625a0f`, `d59cc70`, `9d0ddbc`, `6d21283`, `20472ce`.

### 3. Learned weights did not govern the full organism

Problem: reliability statistics existed, but not every expert consumer or order path used them. Two submit routes could bypass consensus and adaptive sizing.

Remediation:

- Effective expert weights blend durable reliability with conservative priors.
- Expert aggregation produces deterministic `SUPPORT`, `BLOCK`, or `NEUTRAL` consensus.
- The shared execution policy applies consensus, learned stop adjustment, and position cap.
- Agent-generated, tool-generated, and automatic paper orders all use that same policy.
- Executed stop risk, not merely proposed stop risk, is recorded for later learning.

Primary commits: `a64fcc9`, `31871e1`, `e22801f`, `c2210b4`, `dd715df`, `3558acf`, `c1e0ae6`, `16bfe3d`.

### 4. Data routing confused presence with validity

Problem: a provider payload could be non-null yet unusable, preventing fallback to the next provider.

Remediation:

- Prices must be positive and finite.
- Candle results must contain a usable, nonempty series.
- Profiles and fundamentals must contain capability-relevant content.
- Empty notes, zero prices, NaN values, and malformed payloads fall through to the next provider.

Primary commit: `d11e121`.

### 5. Persistence was not sufficiently crash-safe

Problem: several durable writes could be interrupted, and RAG loaded NumPy data with pickle enabled.

Remediation:

- Durable file updates use a temporary file in the destination directory, flush, `fsync`, and atomic replacement.
- RAG writes immutable generations containing JSONL documents, FAISS bytes, and a SHA-256 manifest.
- A verified generation is activated through an atomic `CURRENT` pointer.
- Tampered or incomplete generations are rejected.
- Obsolete tracked pickle-era test fixtures were removed; Git history remains the recovery path.

Primary commits: `40e4d30`, `4f661fa`, `1274d58`.

### 6. Generated claims were weakly tied to evidence

Problem: prose could mention a symbol or price inconsistent with the evidence that actually drove the run.

Remediation:

- Security claims carry ticker, evidence ID, source, timestamp, and price.
- Post-generation validation checks symbol identity and price contradictions.
- The guard no longer performs a hidden broker connection as a fallback truth source.

Primary commits: `d61bee9`, `86752c4`.

### 7. Runtime-only defects

The live smoke exposed issues that unit tests had not revealed:

- The internal `__HEARTBEAT__` journal sentinel was sanitized into a real-looking ticker and triggered a failing market-data request. The frontend now rejects that sentinel.
- The containment notification passed `timeout` to `urllib.request.Request`, which does not accept it. Timeout is now applied to `urlopen`.
- Duplicate pytest configuration made one set of quality options silently dead. `pytest.ini` is now the single authority and strict markers are enabled.
- Ten maintained Python files were normalized with the configured formatter.

Primary commits: `6ce89c3`, `8c4e1de`, `d6d2b01`.

### 8. Broker transport was split across incompatible authorities

Problem: the pipeline could prepare a safe order but then invoke a raw CLI transport directly; the live engine constructed orders without the metadata demanded by the low-level adapter. A JSON envelope passed through environment variables was initially added, but the independent reviewer correctly demonstrated that a local process could forge it.

Remediation:

- `Order` now has an explicit gate metadata contract.
- Metadata can be created only from an `ALLOW` F51 decision bound to the same ticker and run, a resolved approval, and a non-blocking weighted consensus.
- The adapter requires evidence that adaptive sizing and the pipeline preparation ran.
- The raw CLI is a retired compatibility shim and never imports or calls IBKR, regardless of environment variables or forged envelopes.
- Order placement moved to an internal isolated worker referenced only by the validated adapter.
- Cancellation uses the same isolated boundary and remains available as a risk-reducing operation.
- Journal health checks no longer append synthetic `__HEARTBEAT__` or `__LOW_LEVEL_GATE__` trades.
- The legacy live engine remains fail-closed when it cannot present a prepared envelope; no authorization is fabricated for availability.

Primary commits: `4c40b33`, `08cd41d`, `654190e`.

## Verification evidence

Completed gates on the final implementation:

- `python -m ruff check src/ tests/` — passed.
- `python -m ruff format --check src/ tests/` — identified ten old formatting deviations; all ten were normalized.
- `python -m pytest tests/ -q` — 1,452 passed, 11 skipped, 0 failed in 107.62 seconds (1,463 collected).
- Runtime API — `/health` returned HTTP 200 on port 8002.
- Playwright browser smoke — passed with a real UI load, 124 AAPL candles, nonblank 685x640 canvas, a 2,302-character chat answer, and zero browser console errors.
- Runtime containment — when the optional local CEO on port 8082 was absent, the organism entered `MAN_AT_WORK`, blocked orders, and continued diagnostics.
- Runtime defect regression — 40 focused tests passed after the heartbeat and notification fixes.
- Broker shielding regression — 35 focused tests passed after the prepared submit and cancellation worker fixes.
- Independent subagent re-audit — no remaining P0/P1 submit bypass; forged raw-CLI environments remain blocked by the retired transport.

The 11 skipped tests are live-service integration scenarios; they are explicitly marked and do not represent hidden unit-test failures.

## Honest residual limits

- Predictive quality still requires forward, out-of-sample evaluation. Passing software tests does not prove alpha.
- Reliability weights are causal only to the extent that journal attribution is accurate and terminal outcomes are sufficiently numerous.
- Champion/candidate promotion with formal off-policy evaluation and calibrated probability monitoring is the next research-grade evolution; it is not falsely represented as complete here.
- Provider freshness cannot be universally enforced when an upstream response supplies no trustworthy source timestamp. Such data can be structurally valid but should not be called fresh without evidence.
- The runtime used the configured fallback cascade for chat while the local port-8082 model was absent. Core math, gates, journaling, and containment remained available.
- Optional `ib_insync` was not installed in the Python environment used for the smoke; broker health degraded safely and no live order was authorized.

## Repository hygiene

- All project changes were committed locally in small commits.
- No GitHub network operation was performed.
- User-owned runtime data, diagnostics, traces, dedup records, and the pre-existing deletion of `scripts/_debug_open_questrade.py` were not staged or reverted.
- No credential was inspected, edited, staged, or reported.

## Final assessment

The corrected system matches the intended organism more closely: validated present evidence and durable past outcomes feed deterministic mathematics; expert relationships adjust from terminal results; risk policy remains sovereign; LLMs help reason and communicate without becoming the source of execution truth. The codebase is green at the unit/contract level and the real browser flow is operational, while the remaining scientific uncertainty is stated rather than hidden.
