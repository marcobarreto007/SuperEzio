# Two-Phase Order Design

> **SUPERSEDED (2026-08-26).** Duplicata histórica — a versão canônica deste
> documento é `docs/architecture/TWO_PHASE_ORDER.md` ("Two-Phase Paper Order —
> Execução Imediata + Validação Assíncrona"). Este arquivo é mantido apenas
> como registro; não use este conteúdo como fonte para o contrato atual.

## Problem
Current pipeline takes ~120s to complete a trade request because:
1. Market scan (10-20s)
2. Data enrichment (30-60s timeout)
3. Expert committee (20-40s)
4. Guardrails (5-10s)
5. Bob decision (10-20s)

User waits for ALL of this before getting any feedback.

## Solution: Two-Phase Order

### Phase 1: Quick Approval (< 10s)
1. User requests trade
2. Scanner runs (lightweight, 5-10s) → returns top candidates with price/volume
3. Basic guardrails run (F51, SDCA) → 2-3s
4. System returns: "APPROVED PENDING: SMWB $3.45, waiting expert committee"
5. User sees immediate feedback

### Phase 2: Background Execution (< 30s)
1. System runs expert committee in background
2. System collects professional data
3. Bob makes final decision
4. Order submitted to broker OR rejected with reason
5. User notified via WebSocket/polling

## Implementation

### Current State
- `/trade/execute` creates PENDING_VALIDATION ticket
- Pipeline runs synchronously before submit_paper_order
- Latency: 120s average

### Target State
- `/trade/approve` → immediate approval (< 10s)
- Background pipeline → async execution
- `/trade/status/{order_id}` → polling for updates
- WebSocket push → real-time updates

### Changes Required

1. **Split pipeline into two stages**
   - Stage 1 (sync): scanner + basic guardrails → approve/reject
   - Stage 2 (async): experts + data + Bob → execute

2. **Add WebSocket/Streaming**
   - Stream progress updates to UI
   - Push final decision

3. **Optimize data collection**
   - Reduce timeout from 60s → 30s (DONE)
   - Parallelize scanner + data collection
   - Cache market data

## Current Status

✅ Reduced timeout: 60s → 30s
⏳ Two-phase architecture: NOT IMPLEMENTED
⏳ WebSocket streaming: NOT IMPLEMENTED
⏳ Async background pipeline: NOT IMPLEMENTED

## Quick Win (Current)

For now, user can:
1. Call `/trade/execute` with ticker/action/qty
2. Get order_id immediately
3. Poll `/trade/status/{order_id}` for updates
4. See when pipeline completes

This is already two-phase, but pipeline still runs synchronously before returning.
