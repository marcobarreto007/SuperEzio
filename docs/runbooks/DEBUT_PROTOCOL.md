# Market Debut Protocol - Bob SuperEzio CEO

**Version:** 1.2.0
**Date:** 2026-06-05
**Status:** Pre-Debut Validation (6/8 criteria proven)

## 1. Overview

Bob is not a generic chatbot. Bob is an educational financial copilot with an
80B-class local model, deterministic analysis pipeline, risk firewall, F51
verdict engine, broker visibility, and gated IBKR paper order submission.

The market debut is not placing an order. The debut is proving that Bob can:

1. Understand the investor request.
2. Collect real data.
3. Separate opportunity from trap.
4. Explain risk.
5. Register a thesis.
6. Track the result.
7. Learn from correct and wrong calls.
8. Never execute live money; submit paper orders only through the gated tool.

## 2. Current State (2026-06-05)

### 2.1 Runtime

| Component | State |
|-----------|-------|
| CEO Server (:8082) | Operational - Qwen3-Next-80B, 79.7B params, MoE 512 experts |
| API Server (:8002) | Operational - FastAPI + LangGraph pipeline v4 |
| Frontend | Operational - SuperEzio UI |
| GPU | RTX 5060 Ti 16 GB VRAM |
| Python | 3.12.10 |

### 2.2 Quality

| Metric | Value |
|--------|-------|
| Test Suite | 1063/1063 passing, 0 warnings |
| Contract Tests | 415/415 passing |
| Lint | All checks passed |
| Browser Smoke | ok=true, AAPL chart 130 candles, chat functional |

### 2.3 Broker / Paper Mode

| Provider | State |
|----------|-------|
| IBKR | TWS Demo/Paper-style API connected on localhost:7497, paper_order_enabled |
| Alpaca | Package present, credentials not configured, read_only_no_orders |

IBKR proof:

```text
scripts/broker_readiness_probe.py --provider ibkr --json
connected_count: 1
provider: ibkr
connected: true
paper_port: true
mode: paper_order_enabled
account_equity: 100000.00
positions_count: 0
can_submit_orders: true
```

Bob may explain this state to users. Bob may submit IBKR paper LMT orders only
through `submit_paper_order` when the execution gate is enabled. Bob must not
claim a broker fill unless the IBKR/tool status proves it.

## 3. Debut Criteria

### C1 - Understand the investor request: PROVEN

Classify intent correctly: ticker analysis, capital allocation, market scan, or
general advisory.

### C2 - Collect real data: PROVEN

Use configured providers for price, fundamentals, technicals, and context. Never
invent data.

### C3 - Separate opportunity from trap: PROVEN

Identify pumps, traps, low liquidity, and FOMO signals before any recommendation
framing.

### C4 - Explain risk: PROVEN

Every investment analysis must explain market, liquidity, concentration, and
timing risk.

### C5 - Register thesis: PROVEN

Document thesis, evidence, verdict, and expected review horizon.

### C6 - Track result: INSTRUMENTED

Revisit past theses and compare expectation with reality.

**Tooling:** `PaperJournal` (`src/core/trading/paper_journal.py`) -
append-only JSONL journal. Tracks thesis, entry/exit, PnL, outcome, and
post-mortem reflection. CLI: `scripts/paper_journal_cli.py`.

**Tests:** `tests/test_paper_journal.py` (10 tests - all passing).

**Acceptance criteria for PROVEN status:**
- >=1 real thesis in the production journal (`data/paper_journal.jsonl`)
- Entry price sourced from IBKR broker feed (not manually typed)
- Trade aged to its declared review horizon before closing
- Closed with exit price from broker feed
- Post-mortem reflection filled (what went right, what went wrong, lesson)

### C7 - Learn from correct and wrong calls: INSTRUMENTED

Identify systematic errors, calibrate experts, and improve confidence.

**Tooling:** `PerformanceEngine` (`src/core/trading/performance_metrics.py`)
- Sharpe ratio, Sortino, max drawdown, profit factor, expectancy, thesis
accuracy, bias detection (5 patterns), improvement suggestions.
CLI: `scripts/paper_journal_cli.py performance`.

**Tests:** `tests/test_paper_journal.py` (6 tests - all passing).

**Acceptance criteria for PROVEN status:**
- >=10 real theses closed in the production journal
- PerformanceEngine detects >=1 bias that is real Bob behavior
  (not an artifact of synthetic fixtures or small sample size)
- Bias must be traceable to a specific pattern in real closed trades

### C8 - Never execute live money: PROVEN

Live-money execution remains prohibited. Paper orders do not require an extra
Marco approval prompt once `SUPEREZIO_ENABLE_PAPER_ORDER_SUBMIT=1`,
`ticket_allowed=true`, and the `submit_paper_order` tool are active. Every paper
order must be LMT and every broker result must be reported from the tool output.

## 4. Summary

| Status | Criteria |
|--------|----------|
| PROVEN | C1, C2, C3, C4, C5, C8 (6/8) |
| INSTRUMENTED | C6, C7 (2/8) |

**Readiness: 6/8 proven, 2/8 instrumented.** C6 and C7 have working tooling
(code + tests + CLI) but await real market evidence. No criteria remain
unimplemented. Progress from here requires time in market, not more code.

### Falsifiable acceptance criteria

| Criterion | Proven when |
|-----------|-------------|
| C6 | >=1 real thesis in production journal, price from broker feed, aged to review horizon, closed, with post-mortem |
| C7 | >=10 real theses closed AND PerformanceEngine detects >=1 bias traceable to real Bob behavior (not fixture noise) |

## 5. Next Phase - Real Paper Trading

Objective: use IBKR paper account visibility and gated paper LMT orders to build
a thesis journal, compare outcomes against benchmarks, and calibrate Bob before
any live-money path.

### 5.1 Two-Week IBKR Paper Brokerage Apprenticeship

From 2026-06-05 through 2026-06-19, Bob's operational role is a supervised
IBKR paper brokerage apprentice. This is role language for training behavior,
not a legal claim that Bob is a registered broker, financial advisor, IBKR
employee, or autonomous execution engine.

During this window Bob must:

1. Read IBKR paper account state when available.
2. Use broker-sourced prices where available for paper theses.
3. Submit paper LMT orders only after explaining thesis, risk, invalidation,
   size, and expected review horizon.
4. Never ask for extra Marco approval for paper submit when the execution gate
   is already enabled; always require separate explicit approval before any
   future live-money path.
5. Record every thesis, order-ticket plan, broker status, outcome, and
   post-mortem in the paper journal.
6. Explain clearly whether the system is read-only, paper order enabled, or
   live order disabled.

Bob must not:

1. Claim to be a registered broker, financial advisor, or IBKR employee.
2. Claim live-money execution capability.
3. Call a journal entry a broker fill unless IBKR order status or execution
   detail proves it.
4. Treat simulated paper fills as proof of live-market edge.

Technical prerequisites:

1. IBKR TWS paper/demo API connected on port 7497 with socket clients enabled.
2. Paper thesis journal implemented.
3. Performance metrics defined: Sharpe, max drawdown, win rate, thesis vs result.
4. Periodic thesis review implemented.

Operational prerequisites:

1. Keep TWS API in read-only mode for validation.
2. Keep live-money ports out of the validation path.
3. Require explicit approval gate before any future paper execution adapter.

## 6. References

- `config/mission_context.json` - context injected into Bob's system prompt.
- `docs/runbooks/RUNBOOK.md` - operational runbook.
- `.f51/checkpoints/latest.json` - latest checkpoint.
- `.f51/RISK_REGISTER.md` - risk register.
- `scripts/broker_readiness_probe.py` - broker readiness CLI.
- `tests/test_broker_readiness_probe.py` - broker probe tests.

Update this runbook after every major validation checkpoint.
