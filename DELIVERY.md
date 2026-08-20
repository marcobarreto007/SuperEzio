# DELIVERY — SuperEzio Personal Financial Copilot

> **HISTORICO / SUPERSEDED.** Este handoff registra o estado da entrega de 2026-05-21 e deve permanecer como evidência histórica. Ele não é um runbook do runtime atual; comandos, portas, modelos e fallbacks descritos abaixo podem estar obsoletos. Para operação e release atuais, use `docs/runbooks/RUNBOOK.md` e `docs/runbooks/DELIVERY_CHECKLIST_v3.md`. O contrato atual é zero-cloud: Qwen3.8-27B local em `:8080`, API/UI em `:8002`, sem fallback de LLM em nuvem.

**Release Tag:** Zero-Garbage-Runtime v1
**Audit Pass:** Pre-Delivery Quality Gate
**Date of Final Pass:** 2026-05-21
**Owner / Operator:** Marco
**Status:** Cleared for delivery, conditional on local execution of `scripts/verify_zero_garbage_runtime.ps1`.

> This document is the consolidated handoff. It is the **final document the operator reads before shipping**. It records what was audited, what was changed, what was deliberately left alone, what remains a known limitation, and how to prove the system is healthy on the target machine.

---

## 1. Scope of This Release

This release is a **stabilization, audit, and product-quality pass** on the existing SuperEzio runtime. It is explicitly **not** a feature release.

In scope (delivered):
- Eliminate empty assistant responses end-to-end (`/task/submit` + frontend).
- Eliminate garbage market-scan candidates (data-quality gate + universe routing).
- Eliminate fake precision in macro/personal-finance answers.
- Eliminate accidental ticker/chart-context leak on complex-finance intents.
- Eliminate refusal-wall behaviour for personal-capital-allocation questions.
- Eliminate broken runtime import (`collect_experts`).
- Eliminate silent broker fallbacks (logged warnings on Alpaca exceptions).
- Add structured runtime trace on every `/task/submit` response.
- Add Finnhub provider with mocked-contract tests and graceful degradation.
- Add a master pre-delivery verification script (`scripts/verify_zero_garbage_runtime.ps1`).

Out of scope (deliberately untouched):
- New agents, new providers, new dependencies.
- Cloud deployment, GitHub publishing, or any non-local runtime.
- UI redesign or new product surfaces.
- Reorganisation of `src/experts/*` model trees.

---

## 2. Pre-Delivery Audit — What Was Done

The full audit was run as a **static analysis pass** under sandbox constraints. The verification script below is the proof-of-life that turns the static findings into a runtime gate on the operator's machine.

### 2.1 Audited dimensions

| # | Dimension | Method | Result |
| - | --- | --- | --- |
| 1 | Secret hygiene (Finnhub key) | Tracked-file grep + `.env.example` guard | Clean; guard added to verify script |
| 2 | Boot sequence | Static import trace + boot-smoke probe | Clean; smoke probe added to verify script |
| 3 | Import landmines beyond `collect_experts` | Cross-reference imports vs filesystem | Clean; shim covers legacy paths |
| 4 | Silent fallbacks ("mock-in-production") | Grep for `_HAS_*=False`, bare returns | `broker.py` patched (see §2.2) |
| 5 | Broad-except swallowing in finance paths | AST-level scan of `src/core/trading` and `src/data` | `broker.py` patched (see §2.2) |
| 6 | Logging hygiene | Grep for `print(`, `pprint(`, secret-in-log risk | Clean in production paths |
| 7 | Frontend (`console.log`, hardcoded `localhost`) | Grep + read | All `console.log` are guarded error/trace, not spam |
| 8 | README ↔ code parity | Side-by-side read | Patched: Finnhub env var, verify-script reference, flexible test counts |
| 9 | `.env.example` completeness | Diff against `os.getenv` call-sites in `src/` | Patched: added Alpaca, IBKR, SMTP, SCAN_ENRICH, A2A, OTEL placeholders |
| 10 | Dead-code dry-run | Reverse-import graph from production entrypoints | Only `src/tools/` is unreferenced; retained as plugin template (see §4.3) |
| 11 | TODO / FIXME / HACK / XXX | Grep across `src/` and `tests/` | One benign placeholder; no production debt comment |

### 2.2 Changes applied this pass

| File | Change | Reason |
| --- | --- | --- |
| `src/core/trading/broker.py` | Added `logger.warning(...)` before fallback returns in `get_order`, `get_positions`, `get_account_equity`. The `0.0` equity return is now annotated as a sentinel that callers must check. | Eliminate silent broker failures in finance-critical paths. |
| `.env.example` | Added `FINNHUB_API_KEY`, `SUPEREZIO_SCAN_ENRICH`, `A2A_AGENT_NAME`, `SUPEREZIO_OTEL_CONSOLE`, `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `IBKR_HOST`, `IBKR_PORT`, `IBKR_CLIENT_ID`, `SMTP_HOST`, `SMTP_USER`, `SMTP_PASS`, `SMTP_FROM`, `SMTP_TO`. | Keep template in sync with `os.getenv` call-sites. |
| `README.md` | Added pre-delivery section, Finnhub env var, flexible test counts, reference to `DELIVERY.md`. | README must match runtime. |
| `scripts/verify_zero_garbage_runtime.ps1` | Added `.env.example` placeholder guard, boot-smoke probe, ASCII-safe console output. | Make the verify script the single pre-delivery gate. |

### 2.3 P0 hotfix — market_scan skipped collector (2026-05-22)

**Symptom in UI:** Prompt *"What stock would you recommend if I want to profit within the next 2 weeks?"* returned the structured fallback with `scanner_invoked: False`, `ceo_called: True`, `candidate_count: 0`.

**Root cause:** `src/core/pipeline/graph.py` wired `orchestrator_primary → agent` and **skipped the `data` collector node**, even though `route_after_orchestrator()` always returns `"data"`. Market scans only ran when the CEO ReAct loop explicitly called the `market_scan` tool — so scan state was empty and the deterministic answer path never fired.

**Fix (saved on disk):**

| File | Change |
| --- | --- |
| `src/core/pipeline/graph.py` | Insert `data` node (`node_collector`); edges `orchestrator_primary → data → agent`. |
| `src/core/pipeline/nodes/agent.py` | Deterministic `market_scan` answer runs **before** `ceo_primary` starts; blank CEO `final_answer` content replaced with a retry hint. |
| `src/agent_server/endpoints.py` | Trace marks `scanner_invoked` when `PIPELINE_STEP data/started` or `DATA_COLLECTED` fires on `market_scan`. |
| `tests/test_pipeline_smoke.py`, `tests/test_runtime_smoke.py` | Expect `data` node in compiled graph / status. |

**Operator action:** Restart the API after pulling these changes (graph is compiled at boot). Retest the same prompt; trace should show `scanner_invoked: True`, `ceo_called: False`, and a structured scan answer (candidates or explicit no-candidate report with rejection reasons).

### 2.4 P0 hotfix — DataHub/Finnhub 100% `missing_price` (2026-05-22)

**Symptom:** After §2.3, scans correctly used `US_CANADA_LIQUID` but rejected all ~60 candidates with `missing_price` / *"latest price unavailable from data hub"*.

**Root causes:**

1. **Finnhub rate-limit burst** — `_run_scan` fired ~72 parallel hub calls (24× price + profile + catalyst), exceeding the free-tier 60 req/min cap → mass `no_quote` / timeouts.
2. **Symbol mismatch** — FinanceDatabase tickers (e.g. `BRK-B`, bare `RY` vs `RY.TO`) were passed to Finnhub without normalization.
3. **Opaque errors** — Non-200 Finnhub responses collapsed to `no_quote`; aggregate failures were not surfaced in `source_errors` / trace `provider_error`.
4. **Partial price enrichment** — Only the first `SUPEREZIO_SCAN_ENRICH` (24) rows got price lookups; the rest always failed `missing_price`.
5. **No keyless fallback** — When Finnhub/Twelve/Alpha were all missing or failed, hub returned `no_provider_result_for_price` for every row (trace: `price_provider: no_provider_result_for_price=60`).
6. **kwargs breakage on fallbacks** — `market=` was passed to Twelve Data / Alpha Vantage `get_price`, causing `TypeError` after Finnhub failed.

**Fix:**

| File | Change |
| --- | --- |
| `src/data/finnhub_symbols.py` | Symbol variant resolver (class shares, `.TO` / Canada). |
| `src/data/finnhub_provider.py` | Per-request rate limit (`FINNHUB_MIN_INTERVAL_SEC`), HTTP error codes, multi-variant quote/profile/catalyst. |
| `src/data/stooq_provider.py` | **NEW** — keyless delayed quotes (`aapl.us`, `ry.to`) as last-resort price source. |
| `src/data/data_hub.py` | `load_local_env()` on hub init; Stooq route (priority 50); `_kwargs_for_method()` so only compatible kwargs reach each provider. |
| `src/core/pipeline/nodes/collector.py` | `load_local_env()` before hub import; price enrich for all scan rows (configurable); bounded concurrency; `price_provider:` / `price_routes_active` / `price_attempts_sample` in `source_errors`. |
| `desktop/SuperEzio.bat` | RETIRED — use `serve_agent_llamacpp.ps1` + `python -m agent_server.main` directly. |
| `scripts/smoke_datahub_price.py` | Live smoke: `hub.get_price("AAPL")` + `list_active()` / `price_routes` (no secrets printed). |

**Verify locally:**

```powershell
python scripts/smoke_datahub_price.py
pwsh -File scripts/verify_zero_garbage_runtime.ps1
```

Smoke must show `price_routes` including `stooq` and a numeric `price` for AAPL (`source` may be `finnhub` or `stooq`).

Then restart via `runtime/do_restart.ps1` and rerun the 2-week profit prompt. Rejection summary should **not** be 100% `missing_price`; expect mixed reasons (`missing_short_term_thesis`, `missing_liquidity`, etc.) for rows that received a Stooq/Finnhub price.

> Every code edit above is **surgical**. No refactors, no renames, no API changes.


---

## 3. How to Verify Before Shipping (mandatory)

On the operator's Windows machine, from the repo root:

```powershell
pwsh -File scripts/verify_zero_garbage_runtime.ps1
```

What this script does, in order:

1. **Secret leak guard** — scans tracked files for Finnhub-style keys. Exit 99 if any hit outside `.env*` / lockfiles.
2. **`.env.example` placeholder guard** — fails if the template lost a required placeholder or accidentally holds a real-looking key. Exit 96–98.
3. **Boot smoke** — `import agent_server.main` to catch any new `ImportError`. Exit 95.
4. **Contract + runtime suites** — `tests/test_collect_experts_shim.py`, `tests/test_finnhub_provider.py`, `tests/test_no_empty_response_and_trace.py`, `tests/test_market_scan_candidate_gate.py`, `tests/test_market_scanner.py`, `tests/test_agent_market_scan_loop.py`, `tests/contracts/test_contract_complex_finance.py`, `tests/test_runtime_bob_fixes.py`, `tests/test_integration_runtime.py -k task_submit`.
5. **Lint + format** — `python -m ruff check .` and `python -m ruff format --check .` unless `-SkipLint` is passed.

**Exit 0 is the only acceptable signal for delivery.** Any non-zero exit blocks the release.

Live integration check after `verify_zero_garbage_runtime.ps1` exits clean:

```powershell
# In one terminal — start the runtime
powershell -ExecutionPolicy Bypass -File scripts\serve_agent_llamacpp.ps1 -Port 8082

# In another — confirm endpoints respond healthy
curl.exe -fsS http://127.0.0.1:8082/health
curl.exe -fsS http://127.0.0.1:8082/v1/models
curl.exe -fsS http://127.0.0.1:8002/health
curl.exe -fsS http://127.0.0.1:8002/health/details
```

For the full operational map, see `docs/runbooks/RUNBOOK.md`.

---

## 4. Known Limitations & Deliberate Non-Goals

### 4.1 Sandbox could not execute tests in this final pass
The pre-delivery audit was conducted under a sandboxed shell that returned 0-byte outputs for `pytest`, `ruff`, and `git` commands. **All findings in §2 are based on static analysis and reading the source.** The verification script in §3 is the deterministic runtime proof. **The operator must run it on the target machine before delivery.** A green run there is the only signal that closes the loop.

### 4.2 Finnhub key is operator-supplied
The Finnhub key the user pasted earlier in the build session must live **only** in the operator's local `.env` file. The verify script will fail if a key matching that signature is found in any tracked file. The script does not test live Finnhub calls — Finnhub tests are mocked to avoid burning rate limits.

### 4.3 `src/tools/custom_tools.py` retained as plugin template
This package is **not referenced by any production entrypoint**. It is the LangChain-style "extra tools" example. It was deliberately retained as a documented extension point so future tools can be added without re-inventing the scaffold. Treat it as living documentation, not as live code.

### 4.4 Broker equity sentinel
`broker.AlpacaBroker.get_account_equity()` returns `0.0` when the Alpaca SDK raises. This is now logged. Any caller that sizes positions from equity **must check** for upstream provider error before using the value. The sentinel is preserved (instead of raising) so the dashboard does not crash when Alpaca is offline; sizing logic must treat `0.0` as "no equity known" and refuse to size.

### 4.5 CEO is local-only
The CEO (`models/Huihui-Qwen3-Next-80B-A3B-Instruct-abliterated.IQ4_XS.gguf`) runs against the local `llama.cpp` server on `127.0.0.1:8082` with F51 Nitro MoE acceleration. Cloud experts (DeepSeek, Finnhub) are optional and degrade gracefully. **The CEO never calls a cloud LLM.** This is intentional and is the product's privacy guarantee.

### 4.6 `.env` never ships
`.env` is gitignored. The operator must create it from `.env.example` on the target machine. The verify script asserts the template is complete; it does not (and must not) inspect `.env`.

---

## 5. Operator Quickstart

```powershell
# 1. Pre-delivery verification (the one gate that matters)
pwsh -File scripts/verify_zero_garbage_runtime.ps1

# 2. Bring up local runtime (CEO + API + browser)
powershell -ExecutionPolicy Bypass -File scripts\serve_agent_llamacpp.ps1 -Port 8082

# 3. Smoke the four health endpoints (see §3)
```

To stop:

```powershell
# The launcher's own cleanup handles ports 8082 and 8002. For manual cleanup:
Get-NetTCPConnection -LocalPort 8082,8002 -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
```

---

## 6. Risk Register (delivery-relevant subset)

| Risk | Severity | Mitigation Shipped |
| --- | --- | --- |
| Finnhub key leaks into tracked files | High | Verify-script secret guard (exit 99) |
| Broker SDK silently masks errors | High | `logger.warning` on every Alpaca exception path |
| Empty Bob response (blank bubble) | High | Backend fallback + frontend structured-error renderer + Test K |
| Garbage market-scan candidates | High | Universe gate (`US_CANADA_LIQUID` default) + data-quality gate |
| Macro/personal-finance refusal wall | High | Intent router skips scanner; mandatory 13-section framework |
| Fake precision (exact returns/probabilities) | Medium | Anti-fake-precision rules in prompt builder; tests assert no exact-% promises |
| Chart-context leak across intents | Medium | `chart_context_attached` flag honoured by `node_agent` and traced in runtime metadata |
| `collect_experts` `ImportError` | High (regressed once) | Shim at `src/core/pipeline/nodes/collect_experts.py` + regression test |
| README drift | Medium | This release patched README + DELIVERY.md added |
| Sandbox could not run live tests | Medium | Pre-delivery verify script is the runtime gate on operator hardware |

For the full risk ledger see `.f51/RISK_REGISTER.md`.

---

## 7. Acceptance — Operator Sign-off

The operator (Marco) signs off this release by recording the following on the delivery machine:

```text
DELIVERY ACCEPTANCE — SuperEzio Zero-Garbage-Runtime v1
========================================================
Date:                    ____-__-__
Verify script exit code: ____   (must be 0)
CEO  /health response:   ____
API  /health response:   ____
Live smoke prompt 1:     "What stock would you recommend if I want to profit within the next 2 weeks?"
Live smoke result 1:     [ ] structured, no .SZ, no garbage   [ ] FAIL
Live smoke prompt 2:     "I have CAD 25,000 to allocate. Build a serious framework."
Live smoke result 2:     [ ] 13-section framework, no refusal [ ] FAIL
Operator signature:      _________________________
```

A single FAIL in the live smoke section blocks delivery. Re-run `verify_zero_garbage_runtime.ps1` and consult `docs/runbooks/RUNBOOK.md`.

---

## 8. Reference Documents

- `README.md` — project overview and quickstart.
- `docs/runbooks/RUNBOOK.md` — operational runbook (start, stop, health, troubleshoot).
- `docs/runbooks/DELIVERY_CHECKLIST.md` — short pre-flight checklist (this DELIVERY.md is the long-form companion).
- `.f51/contracts/agent-server.contract.md` — `/task/submit` and health-route contract.
- `.f51/contracts/pipeline.contract.md` — graph and node contract.
- `.f51/RISK_REGISTER.md` — full risk ledger.
- `scripts/verify_zero_garbage_runtime.ps1` — pre-delivery gate.

---

*End of DELIVERY.md. If anything in §2.2 conflicts with the running code, the running code wins and this document must be patched in the next pass.*
