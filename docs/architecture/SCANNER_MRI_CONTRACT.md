# Scanner MRI Contract v1.0

**Status:** draft — pending implementation
**Date:** 2026-05-23
**Session:** SuperEzio_Scanner_MRI_Design

## 0. Why this exists

The current scanner (`collector.py:_run_scan`) is a single asynchronous function
that fetches tickers, enriches price/profile/catalyst, gates, and ranks in one
monolithic pass. It blocks until everything completes or fails silently. The UI
receives `[SCANNER] INIT` / `[SCANNER] LOADING` and then nothing until the final
`[SCAN_SUMMARY]` — which can mean 30–120 seconds of frozen UI.

This contract defines the target architecture: every scan has a `scan_id`, every
stage emits `started` / `heartbeat` / `completed` / `failed`, no provider can block
the entire scan, and the UI receives structured partial progress in real time.

## 1. SCAN_EVENT — Universal Event Schema

Every scanner event emitted to the UI and logged to the registry MUST conform to:

```python
SCAN_EVENT = {
    "type": "SCAN_EVENT",  # discriminator for UI routing
    "scan_id": str,  # unique per scan, generated at INIT
    "stage": str,  # stage name (see §2)
    "provider": str | None,  # provider name for per-provider events
    "status": str,  # "started" | "heartbeat" | "completed" | "failed"
    "elapsed_ms": int,  # milliseconds since scan INIT
    "counts": {  # stage-specific counters
        "total": int | None,
        "done": int | None,
        "errors": int | None,
    },
    "error": str | None,  # human-readable error if status=failed
    "data": dict | None,  # stage-specific payload (optional)
}
```

### Rules

- `scan_id` is generated at INIT, carried through every event.
- `stage` MUST be one of the stages in §2.
- `provider` is non-null for `enrich_*` stages; null for orchestration stages.
- `counts` MUST be present in `heartbeat` and `completed` events.
- `elapsed_ms` is wall-clock time from INIT, measured server-side.
- Events flow to the UI via the existing `get_stream_writer()` channel.
- Events are logged to the MRI Registry (§6) for post-mortem.

## 2. Stages

| # | Stage | What happens | Provider |
|---|-------|-------------|----------|
| 0 | `init` | Scan created, parameters resolved | — |
| 1 | `fetch_tickers` | Call scanner module to get raw tickers | scanner module |
| 2 | `enrich_price` | Price/liquidity data per ticker | yfinance, finnhub, twelve_data |
| 3 | `enrich_profile` | Company profile per ticker | finnhub |
| 4 | `enrich_catalyst` | Short-term catalyst per ticker | finnhub |
| 5 | `gate` | Apply candidate quality gates | — |
| 6 | `rank` | Rank candidates by quality score | — |
| 7 | `finalize` | Build final result, emit summary | — |

### Stage lifecycle

```
started ──→ heartbeat* ──→ completed
  │
  └───────── heartbeat* ──→ failed
```

- `started`: emitted exactly once when stage begins.
- `heartbeat`: emitted at least every N items or M ms (see §3). Zero or more.
- `completed`: stage finished successfully.
- `failed`: stage failed with error. Error field MUST be populated.

## 3. Heartbeat Contract

Per-stage heartbeat intervals:

| Stage | Heartbeat trigger |
|-------|------------------|
| `fetch_tickers` | every 5 tickers received |
| `enrich_price` | every 3 items processed, or every 5000ms |
| `enrich_profile` | every 2 items processed, or every 5000ms |
| `enrich_catalyst` | every 2 items processed, or every 5000ms |
| `gate` | every 10 items gated |
| `rank` | single heartbeat at sort complete |
| `finalize` | no heartbeat (instant) |

Heartbeats are emitted to the UI **even if the stage is not yet complete.**
The UI uses heartbeat `counts.done` / `counts.total` to render a progress bar.

## 4. Provider Contract

Every enrichment stage (`enrich_price`, `enrich_profile`, `enrich_catalyst`)
operates under these rules:

### 4.1 Timeout

| Parameter | Default | Env override |
|-----------|---------|-------------|
| `per_item_timeout_ms` | 12000 | `SUPEREZIO_SCAN_ENRICH_TIMEOUT_MS` |
| `stage_deadline_ms` | 30000 | `SUPEREZIO_SCAN_STAGE_DEADLINE_MS` |

- Per-item timeout: individual ticker call cannot exceed this.
- Stage deadline: the entire stage (all items) cannot exceed this.
- If stage deadline fires before all items complete, remaining items are marked
  `failed: "stage_deadline"` and the stage emits `failed`.
- Partial results (items that completed before deadline) are preserved and
  forwarded to the next stage.

### 4.2 Retry Budget

| Parameter | Default | Env override |
|-----------|---------|-------------|
| `max_retries_per_item` | 1 | `SUPEREZIO_SCAN_RETRIES` |
| `retry_backoff_ms` | 500 | `SUPEREZIO_SCAN_RETRY_BACKOFF_MS` |

- Retries are per-item, not per-stage.
- Only transient errors are retried (timeout, connection refused, 429, 5xx).
- Non-transient errors (404, invalid ticker, auth failure) are NOT retried.

### 4.3 Circuit Breaker

```python
CIRCUIT_BREAKER = {
    "failure_threshold": 5,  # consecutive failures to open
    "success_threshold": 2,  # consecutive successes to close (half-open)
    "half_open_cooldown_ms": 10000,  # time before attempting half-open
    "scope": "per_provider",  # each provider has its own breaker
}
```

- When a provider exceeds `failure_threshold` consecutive failures, the breaker
  OPENS and subsequent calls to that provider are skipped with `failed: "circuit_open"`.
- After `half_open_cooldown_ms`, the breaker transitions to HALF-OPEN and allows
  one test call. If it succeeds, CLOSED. If it fails, OPEN again.
- Circuit state is logged to the registry.
- If all providers for a stage have open circuits, the stage emits `failed` with
  all accumulated partial results.

## 5. Partial Result Contract

If a stage fails (timeout, circuit open, or exception), the scan produces a
**partial result** rather than silence:

```python
PARTIAL_RESULT = {
    "scan_id": str,
    "status": "partial",  # "complete" | "partial" | "failed"
    "failing_stage": str,  # which stage caused partial result
    "failing_provider": str | None,
    "failing_reason": str,  # human-readable
    "candidates": [...],  # candidates that passed before failure
    "candidate_count": int,
    "rejected": [...],
    "rejected_count": int,
    "stages_completed": [str],  # list of stages that finished
    "stages_failed": [str],  # list of stages that failed
    "events": [SCAN_EVENT, ...],  # full event log for this scan
}
```

The UI renders partial results with a clear indicator: "Results incomplete —
price data succeeded, profile timeout. Showing what we have."

## 6. MRI Registry — Source of Truth

The registry is an in-memory append-only log of all `SCAN_EVENT`s for the
current scan, exposed as:

```python
class ScanEventRegistry:
    """Append-only event log for a single scan."""

    scan_id: str
    events: list[dict]  # all SCAN_EVENTs in order
    started_at: float  # time.monotonic() at INIT
    finished_at: float | None  # time.monotonic() at FINALIZE

    def emit(self, event: dict) -> None: ...
    def snapshot(self) -> dict: ...  # full state for debugging
    def failing_stage(self) -> str | None: ...
    def elapsed_ms(self) -> int: ...
```

### Rules

- Registry is created at `init` stage.
- Every stage pushes events via `registry.emit()`.
- Registry is serialized into `scan_trace` in the final/partial result.
- Registry is the **source of truth** for "onde o sangue parou" (where the
  blood stopped). Any scan that fails or times out can be diagnosed by reading
  its event log.
- Registry lives only for the duration of the scan (not persisted to disk).
  For persistent audit, the entire scan result including `scan_trace.events`
  is stored in the runtime log.

## 7. UI Contract

The UI receives `SCAN_EVENT`s via the existing SSE channel and MUST:

1. Show a progress bar per stage using `counts.done / counts.total`.
2. Show elapsed time from `elapsed_ms`.
3. Show provider-level status: green (ok), yellow (slow/retrying), red (failed/circuit open).
4. On partial result, render the candidates with a "Partial — X stage incomplete" banner.
5. Never show a frozen spinner for more than 10 seconds without a heartbeat.

## 8. Migration Path (3 Phases)

### Phase 1: MRI Registry (instrumentation only)

- Add `ScanEventRegistry`.
- Wrap existing `_run_scan` stages with `started`/`completed`/`failed` events.
- Wire events to the existing `writer()` channel.
- **No behavior change.** Scan still blocks. UI still freezes. But every stage
  emits events that prove the pipeline is alive.

### Phase 2: Circuit Breaker + Partial Result

- Add per-provider circuit breaker.
- Add stage deadline to enrichment phases.
- On deadline/breaker-open, produce `PARTIAL_RESULT` instead of exception.
- **Behavior change:** scan never produces silence. Always returns something.

### Phase 3: Provider Queues

- Replace `asyncio.gather` with `asyncio.Queue` per provider.
- Providers run independently — if one stalls, others keep producing.
- UI receives per-ticker results as they arrive (true streaming).
- **Behavior change:** scan is truly asynchronous.

## 9. Non-Goals (for now)

- Persistent event log to disk (use runtime log for audit)
- NATS JetStream / Temporal (asyncio.Queue is sufficient for Phase 3)
- Horizontal scaling of provider workers (single process, async I/O)
- Dead-letter queue for failed items (registry event log is sufficient)

## 10. Validation Gates (Before any PR)

- [ ] Ruff format + lint clean on all touched files.
- [ ] `python -m pytest tests/ -q` passes (or pre-existing failures documented).
- [ ] `python scripts/browser_smoke.py` passes against live server.
- [ ] Scanner emits at least one heartbeat per stage when scanning real tickers.
- [ ] Partial result produced when enrichment deadline fires (manual test with
  `SUPEREZIO_SCAN_STAGE_DEADLINE_MS=3000`).
- [ ] Circuit breaker opens after 5 consecutive failures from a provider.
- [ ] UI renders partial result with "Partial" banner (browser screenshot).
