# IBKR Boundary Service — Implementation Plan

## Context

SuperEzio's IBKR integration has critical architectural flaws:
- **9 distinct `IB()` instantiations** across 6 files, each opening its own connection
- **No shared connection or singleton** — every call site connects/disconnects independently
- **clientId collision risk** — 6 sites use `int(time.time()*1000) % 9000 + offset` with overlapping offsets
- **ib_insync event-loop conflicts** on Windows — the library owns its own asyncio loop
- **No caching/cooldown** — positions/equity queried repeatedly, no backoff when TWS is down
- **Inconsistent degradation signals** — some paths return `"IBKR offline"`, others return `0.0`/`[]`/`None`

The project already converged on **subprocess isolation** (`_ibkr_order.py`, `_ibkr_position_check.py`) as the robustness escape hatch — exactly because in-process `ib_insync` + asyncio on Windows fights over the event loop. A boundary service should formalize this pattern.

## Goal

Create an isolated IBKR boundary service that:
1. Owns a single `IB()` connection with a stable clientId
2. Runs in its own thread/process to avoid event-loop conflicts
3. Caches positions/equity with a short TTL (5-15s)
4. Implements cooldown when TWS is unavailable
5. Emits consistent degraded status (`broker_degraded`) instead of hiding errors
6. Preserves the existing `BrokerAdapter` protocol for callers

## Approach

**Reuse existing patterns:**
- `LiveMonitor` (daemon thread with RLock, lifecycle, in-memory snapshots) → structural model
- `broker_readiness_probe.py` (TCP pre-check + structured status) → health template
- `finnhub_provider.py` TTL cache (env-configurable, monotonic, fail-not-cache) → cache template
- `gateway.py` cooldown dict (consecutive errors → timestamp skip-list) → backoff template
- `graph.py:366-444` fresh inner event loop + `run_in_executor` + `wait_for(timeout=8.0)` → IBKR-specific async bridge

**New service structure:**
```
src/adapters/broker/
├── ibkr_service.py          # NEW: IBKRService singleton (daemon thread, cache, cooldown)
├── ibkr_adapter.py          # MODIFY: delegate to IBKRService, remove inline IB()
└── __init__.py              # EXPORT: get_ibkr_service()
```

**Phase 1 — IBKRService Core**
- Thread-safe singleton with `get_ibkr_service()` factory (following `fraud_memory.py` pattern)
- Daemon thread with RLock-guarded state (`_ib`, `_connected`, `_positions_cache`, `_equity_cache`, `_last_cache_time`)
- Stable clientId from env `IBKR_SERVICE_CLIENT_ID` (default 100, outside collision band)
- `start()` / `stop()` lifecycle (connect on start, disconnect on stop)
- Background refresh loop (5-15s interval, runs inside the daemon thread's own event loop)
- Cooldown tracking (`_consecutive_failures`, `_cooldown_until`) — skip calls during cooldown
- Cache TTL from env `IBKR_CACHE_TTL_SEC` (default 10)

**Phase 2 — Cache & Cooldown**
- TTL cache for positions/equity (following `finnhub_provider.py:170-203` pattern)
  - Uses `time.monotonic()` (immune to wall-clock changes)
  - Env-driven TTL (`IBKR_CACHE_TTL_SEC`)
  - **Does not cache failures** — only cache successful reads
- Cooldown on connection failure:
  - 3 consecutive failures → cooldown for 60s (configurable via `IBKR_COOLDOWN_SEC`)
  - During cooldown, return `broker_degraded` status instead of retrying
  - Reset counter on first success

**Phase 3 — API Surface**
- `get_positions()` → cached if within TTL, else trigger refresh (wait up to 2s)
- `get_account_equity()` → cached if within TTL, else trigger refresh (wait up to 2s)
- `get_open_orders()` → live call (no cache, orders change fast)
- `submit_order()` / `cancel_order()` → delegate to subprocess (`_ibkr_order.py`)
- `get_status()` → structured health: `{connected, can_read, can_trade, cache_age_s, cooldown_active, last_error}`
- All methods return fast (cache hit) or block briefly (cache miss, 2s max) — never the 8-30s hangs of today

**Phase 4 — Async Bridge**
- For async callers (pipeline/cockpit), provide `get_positions_async()` / `get_account_equity_async()`
- Uses `asyncio.to_thread()` to call the sync methods (following `endpoints.py:906` pattern)
- No fresh event loop needed — the daemon thread owns the `IB()` instance

**Phase 5 — Refactor Call Sites**
Replace the 9 `IB()` instantiations:

| Current Site | Replacement |
|--------------|-------------|
| `ibkr_adapter.py:45` | Remove inline `IB()`; `InteractiveBrokersAdapter` delegates to `IBKRService` |
| `endpoints.py:187` (`_cockpit_ibkr_open_orders`) | Call `IBKRService.get_open_orders_async()` |
| `endpoints.py:384` (`_cockpit_portfolio_snapshot`) | Call `IBKRService.get_positions_async()` / `get_account_equity_async()` |
| `graph.py:378` (`_fetch_ibkr_snapshot`) | Delete — use `IBKRService` in `_auto_full_analysis` |
| `agent.py:702, 774` (fallbacks) | Call `IBKRService.get_positions_async()` — already error-tolerant |
| `scripts/broker_readiness_probe.py:78` | Keep as-is (standalone probe, not a call site) |
| `scripts/_ibkr_position_check.py:21` | Keep as-is (subprocess, isolated) |
| `scripts/_ibkr_order.py:36` | Keep as-is (subprocess for orders) |

**Health/Degradation Update**
- Update `src/agent_server/main.py` `/health/details` to include IBKR status from `IBKRService.get_status()`
- Distinguish:
  - `status: "ok"` — API healthy, IBKR connected and responding
  - `status: "degraded"` — API healthy, IBKR in cooldown or returning stale cache
  - `status: "degraded_no_backend"` — API healthy, no LLM backend (existing)

## Files to Modify

**New files:**
- `src/adapters/broker/ibkr_service.py` — core service (300-400 lines)

**Modified files:**
- `src/adapters/broker/ibkr_adapter.py` — delegate to service, remove `IB()` instantiations (~50 lines changed)
- `src/agent_server/endpoints.py` — replace `_cockpit_portfolio_snapshot()` IB() inline (~30 lines changed)
- `src/core/pipeline/graph.py` — remove `_fetch_ibkr_snapshot()`, update `_auto_full_analysis` (~80 lines changed)
- `src/core/pipeline/nodes/agent.py` — update fallbacks to call service (~20 lines changed)
- `src/agent_server/main.py` — add IBKR status to `/health/details` (~15 lines added)
- `src/adapters/broker/__init__.py` — export `get_ibkr_service()` (~5 lines added)

**Tests to update:**
- `tests/contracts/test_contract_trading.py` — may mock IBKRAdapter, verify it still works
- Any test that directly imports `ibkr_adapter.py` — verify new delegation

## Verification

**Manual testing:**
```bash
# 1. Start with TWS/Gateway closed
powershell -File .\start.ps1

# 2. Check health shows IBKR degraded
Invoke-RestMethod http://127.0.0.1:8002/health/details | Select-Object -Expand checks | Select-Object -Expand ibkr

# 3. Start TWS/Gateway, wait 15s, check again
# Should show status: "ok" with cache_age_s < 15

# 4. Trigger cooldown (stop TWS for 30s)
# Verify status flips to "degraded" with cooldown_active: true

# 5. Run browser smoke — cockpit portfolio should load (may show stale data)
python scripts\browser_smoke.py --timeout-ms 180000

# 6. Test positions endpoint
Invoke-RestMethod http://127.0.0.1:8002/cockpit/portfolio | Select-Object -Expand positions
```

**Automated tests:**
```bash
# Run existing trading contracts (they mock IBKR, should still pass)
python -m pytest tests/contracts/test_contract_trading.py -q

# Run runtime smoke (tests cockpit endpoint)
python -m pytest tests/test_runtime_smoke.py -q

# Run browser smoke
python scripts/browser_smoke.py --skip-chat --timeout-ms 180000
```

**Verification of fixes:**
- No more `clientId` collision logs in `runtime/logs/api-8002-latest.err.log`
- No more event-loop conflict warnings
- `/health/details` returns consistent `ibkr` status
- Cockpit loads portfolio even when TWS is temporarily down (shows stale cache with `cache_age_s`)

## Rollback

If issues arise, rollback is simple:
- Revert `ibkr_service.py` addition
- Restore original `ibkr_adapter.py`, `endpoints.py`, `graph.py`, `agent.py` from git
- No database migrations, no config changes required

## Next Steps (after this plan)

After IBKR Boundary is verified working:
1. **Fila/Cancelamento** — add `run_id`, TTL, `/task/cancel`, TaskManager
2. **Runtime/Start** — add PID tracking, dono por porta
3. **NewsAPI circuit breaker** — add CircuitBreaker, cache, quota state
4. **CASE enforcement** — make `is_complete` gate before agent
