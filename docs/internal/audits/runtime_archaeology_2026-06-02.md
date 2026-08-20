# Runtime archaeology - SuperEzio Financeiro

> **HISTORICO / SUPERSEDED.** Evidencia arqueologica de 2026-06-02. O runtime atual esta em `docs/runbooks/RUNBOOK.md`.

Date: 2026-06-02
Scope: `C:\Users\marco\Desktop\SuperEzio Financeiro`
Mode: codebase archaeology, duplicate hunt, runtime speed and math-core focus

## Objective

Turn SuperEzio into a faster, cleaner, competition-grade runtime where Bob is the
brain, tools are servants, and the math core is a visible product asset instead
of hidden plumbing.

## Current runtime shape

- Active graph: `orchestrator_primary -> agent -> tool_executor -> agent -> explanation`.
- Current Bob direction: sovereign mode already committed in `56ac575`.
- Active API command: `python -m agent_server.main`.
- Active model command: `powershell -ExecutionPolicy Bypass -File scripts/serve_agent_llamacpp.ps1 -Port 8082`.
- Runtime is disk-only. No GitHub path is allowed.

## Evidence collected

- Tree was clean before this archaeology pass.
- Largest Python files:
  - `src/core/pipeline/intents.py`: 2124 lines.
  - `src/core/pipeline/nodes/agent.py`: 1395 lines.
  - `src/agent_server/endpoints.py`: 1103 lines.
  - `src/core/pipeline/nodes/collector.py`: 1076 lines.
  - `src/core/data_collector/professional.py`: 877 lines.
- Disk footprint:
  - `models`: about 61 GB.
  - `.venv`: about 9.1 GB.
  - `llama.cpp`: about 680 MB.
  - `data`: about 8 MB.
  - `output`: about 7 MB.
- `data/traces` is present with hundreds of trace JSON files, but `git ls-files data/traces` returned 0 tracked files.
- Tracked artifact/log/archive files still include 24 files under:
  - `output/playwright`
  - `runtime/logs`
  - `scripts/_archive`

## P0 - cleanup that improves speed and correctness

### P0-1: Technical indicators are duplicated outside the math core

Evidence:
- `src/core/data_collector/professional.py` defines `_compute_rsi`, `_compute_ema`, `_compute_macd`, `_compute_bollinger`.
- `src/core/math/financial_engine.py` defines the same indicator family.

Impact:
- The product has a math module, but the hot collector path reimplements math locally.
- Divergent indicator formulas can produce different Bob evidence depending on which path ran.
- This hides the math module from the product story.

Action:
- Make `src/core/math/financial_engine.py` or a new `src/core/math/indicators.py` the only source for RSI, EMA, MACD, Bollinger, stoch.
- Replace local functions in `professional.py` with imports from `core.math`.
- Add one contract test that asserts collector technicals come from math-core-compatible values.

### P0-2: CircuitBreaker is duplicated

Evidence:
- `src/core/data_collector/professional.py` has local `class CircuitBreaker`.
- `src/core/pipeline/circuit_breaker.py` has canonical `CircuitBreaker`.

Impact:
- Provider failure behavior can diverge between single-ticker collection and scan enrichment.
- This is exactly the kind of hidden duplication that makes a fast engine unreliable under competition pressure.

Action:
- Use `src/core/pipeline/circuit_breaker.py` as canonical.
- Delete the local class from `professional.py` after adapting constructor/status expectations.

### P0-3: PennyLab is still routed through a stub in the ReAct tool executor

Evidence:
- `src/core/pipeline/nodes/tool_executor.py` routes `pennylab` to `_pennylab_stub`.
- Real PennyLab exists under `src/experts/pennylab`.
- `src/experts/pennylab/mathcore_adapter.py` already exposes a `mathcore_verdict`.

Impact:
- Bob can call `pennylab`, but the tool is not yet the real forensic/math module.
- The math-core story is weakened exactly where penny-stock competitions need it most.

Action:
- Replace `_pennylab_stub` with `run_pennylab_analysis(ticker)` from `src/experts/pennylab/pipeline_hook.py`.
- Return `mathcore_verdict`, scores, risks, and evidence into `data_context`.
- Add a Bob sovereign test: `market_scan -> pennylab -> final_answer`.

### P0-4: Agent/orchestrator/intent logic is too large for a fast runtime

Evidence:
- `intents.py` is 2124 lines.
- `agent.py` is 1395 lines.
- `collector.py` is 1076 lines.

Impact:
- Slow comprehension, risky patches, and high regression probability.
- Bob sovereign mode reduces orchestrator authority, so old intent complexity now has lower product value.

Action:
- Keep Bob sovereign path small and explicit.
- Move legacy deterministic routing into a legacy module.
- Split `agent.py` into prompt, response repair, market-scan answer rendering, and node execution.

## P1 - repo hygiene and duplicate pressure

### P1-1: Tracked runtime artifacts should be archived or removed from Git

Evidence:
- `git ls-files output/playwright runtime/logs scripts/_archive` returns 24 tracked files.

Impact:
- Demo screenshots and old JSONL logs pollute diffs and make product changes harder to review.

Action:
- Keep latest proof artifacts only when they are part of a release checklist.
- Move old tracked logs/screenshots to an evidence bundle or remove from Git after Marco approves.

### P1-2: `data/traces` is untracked noise

Evidence:
- Hundreds of trace files exist in `data/traces`.
- None are tracked by Git.

Impact:
- Local scans and tooling become noisy.
- Easy to accidentally include stale traces in future commits.

Action:
- Add or verify `.gitignore` coverage for `data/traces/`.
- Keep a single curated trace fixture under `tests/fixtures` if tests need it.

### P1-3: Previous archaeology report still contains stale items

Evidence:
- `runtime/checkpoints/ARCHAEOLOGY-DUPLICATES-2026-05-22.md` references older paths and pipeline shape.

Impact:
- Old cleanup plans can send agents to delete or fix things that no longer exist.

Action:
- Treat the 2026-06-02 report as the new cleanup source of truth.
- Use the older report only as historical context.

## Math core as vedette

Make the math module visible in three places:

1. Collector output:
   - Add `mathcore`: `{indicators, risk_metrics, source: "core.math"}`.
2. Tool output:
   - Every math-backed tool should return a `mathcore_verdict`.
3. Bob final answer:
   - Bob should cite math evidence as "math core verdict", not bury it under generic data context.

Immediate implementation order:

1. Replace indicator duplication in `professional.py`.
2. Wire real PennyLab in `tool_executor.py`.
3. Add `mathcore_verdict` to Bob observations and final answer context.
4. Benchmark scan path before/after with a fixed prompt and fixed env.

## Decision

Do not start by deleting broad folders. The fastest path to a smarter engine is:

1. canonical math functions;
2. canonical circuit breaker;
3. real PennyLab tool;
4. artifact cleanup with explicit approval.

This preserves demo safety while removing the duplications that directly affect runtime quality.
