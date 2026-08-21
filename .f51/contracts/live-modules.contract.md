# Live Modules Contract â€” SuperEzio v4.0.0

**Session:** total-system-documentation-sync-2026-08-20
**Status:** CANONICAL
**Source:** `.f51/INVENTORY.json` + live source tree

## Scope

This document defines the public interface contract for every **live module** in
the SuperEzio runtime. Each contract specifies the module's public symbols,
invariants, and test coverage expectations. Modules with zero source files
(init-only) are marked as such.

Contracts that already have dedicated `.f51/contracts/*.md` files are referenced
here with their canonical contract. Modules without dedicated contracts are
defined inline.

---

## 1. Agent Server

- **Canonical:** `.f51/contracts/agent-server.contract.md`
- **Path:** `src/agent_server/` (3 files)
- **Public surface:** FastAPI `app`, routes, A2A `AgentCard`
- **Entrypoint:** `python -m agent_server.main`
- **Port:** 8002

## 2. Pipeline

- **Canonical:** `.f51/contracts/pipeline.contract.md`
- **Path:** `src/core/pipeline/` (18 files)
- **Public surface:** `PipelineState` (TypedDict), `IntentResult`, `CEORequest`, `ExpertCall`, `AgentToolCall`, `PipelineApp`, `build_graph`
- **Graph:** `orchestrator_primary (passthrough) â†’ agent â‡„ tool_executor â†’ explanation/respond_blocked â†’ END`
- **Nodes:** `orchestrator_primary`, `agent`, `tool_executor`, `explanation`, `respond_blocked`
- **Tools:** `collect_data`, `f51_firewall`, `pennylab`, `run_experts`, `neural_decision`, `sdca_firewall`, `rag_forensics`, `market_scan`, `final_answer`
- **Invariants:**
  1. `orchestrator_primary` does not classify intent; it delegates with `route=agent` and `intent=bob_decides`.
  2. Bob and the tool loop determine the operation from the request and collected evidence.
  3. `expert_results` is always a list (never None).
  4. `f51_verdict` contains keys: `confidence`, `passed`, `factors`, `hub_risk_score`.

## 3. CEO

- **Canonical:** `.f51/contracts/ceo.contract.md`
- **Path:** `src/core/pipeline/prompts/_prompts.py`, `src/core/pipeline/prompts/builder.py`
- **Public surface:** `ceo_system_prompt()`, `build_ceo_prompt(state)`, `QWEN_SYSTEM_PROMPT`
- **Model:** operator-supplied `Qwen3.8-27B-Q4_K_M.gguf` (llama.cpp, local `:8080`, context 8192)
- **Invariants:** always returns non-empty string â‰¥ 100 chars; includes `Bob's read` for ticker analysis

## 4. F51 Engine

- **Canonical:** `.f51/contracts/f51-engine.contract.md`
- **Path:** `src/f51/` (5 files)
- **Public surface:**
  - `formulas.py`: `FormulaWeights`, `DecisionFactors`, `unified_decision(factors, weights=None) -> float`, `combined_risk(*risks) -> float`, `proxy_reward(...) -> float`, `heuristic_uncertainty(...) -> float`, `decision_threshold(domain) -> float`, `expand_budget(...) -> bool`
  - `gates.py`: `VeracityGate`, `VeracityResult`, `AdversarialCritic`, `CriticResult`, `ProxyReward`
- **Invariants:**
  1. `unified_decision()` âˆˆ [0, 1] for all valid inputs
  2. `combined_risk(r1, ..., rn)` â‰¥ max(r1, ..., rn)
  3. `VeracityGate.verify()` returns `VeracityResult` with `passed: bool`, `confidence: float`
  4. `DecisionFactors.validate()` raises `AssertionError` on values outside [0, 1]

## 5. DataHub

- **Canonical:** `.f51/contracts/data-hub.contract.md`
- **Path:** `src/data/` (13 files)
- **Public surface:** `DataHub` class with `.get_price(ticker)`, `.get_profile(ticker)`, `.get_candles(ticker, period)`, `.get_quote(ticker)`, `.check_health()`
- **Providers:** `akshare`, `alpha_vantage`, `alphasmo`, `apewisdom`, `boc_macro`, `fed_macro`, `finnhub`, `form4api`, `news_scout`, `newsapi`, `reddit_pulse`, `social_whale`, `twelve_data`, `wolfram`, `yfinance`
- **Invariants:** `check_health()` returns dict with provider key availability

## 6. Neural Decision Expert

- **Canonical:** `.f51/contracts/neural-decision.contract.md`
- **Path:** `src/experts/neural_decision/` (1 source file + 1 config)
- **Public surface:** `NeuralDecisionExpert` with `.predict(ticker, time_horizon, features, context) -> dict`
- **Output keys:** `direction_prob`, `expected_return_signal`, `drawdown_risk`, `uncertainty`, `market_regime`

## 7. A2A Protocol

- **Canonical:** `.f51/contracts/a2a-protocol.contract.md`
- **Path:** `src/core/ports/protocol.py`
- **Public surface:** `A2AMessage`, `MessageType`
- **Message types:** `CAPABILITIES.REQUEST`, `CAPABILITIES.RESPONSE`, `TASK.SUBMIT`, `TASK.RESULT`, `TASK.STREAM`, `EVENT.PUBLISH`, `ERROR`
- **Invariants:**
  1. `A2AMessage.create_response(original, ...)` preserves `correlation_id` and `trace_id`
  2. All messages have `version: "a2a/1.0"`

## 8. Runtime

- **Canonical:** `.f51/contracts/runtime.contract.md`
- **Path:** `runtime/`, `.f51/`, `config/runtime.yml`
- **Processes:** CEO `:8080` (llama.cpp), API/UI `:8002` (FastAPI)
- **Config:** `config/runtime.yml` (UniversalConfig)

---

## 9. Model Serving Gateway

- **Canonical:** this document
- **Path:** `src/core/model_serving/` (3 files: `gateway.py`, `providers.py`, `sanitizer.py`)
- **Public surface:**
  - `ModelGateway(providers, config, audit)` â€” `.generate()`, `.stream_generate()`, `.stream_generate_async()`, `.chat_completion()`, `.unload_all()`, `.warmup()`
  - `ModelProvider(name, base_url, api_key, model, backend, is_local, priority, ...)`
  - `GatewayConfig(max_fallbacks, timeout_s, retry_attempts, retry_delay_s, quality_threshold)`
  - `build_default_providers(config) -> (list[ModelProvider], GatewayConfig)`
  - `create_gateway_from_config(config, audit) -> ModelGateway`
  - `create_gateway(config, audit) -> ModelGateway`
  - Provider names: `AGENT_PROVIDER_NAME`, `PRIMARY_PROVIDER_NAME`, `DEEPSEEK_PROVIDER_NAME`, `DAYTRADE_JUDGE_PROVIDER_NAME`, `DAYTRADE_AUDITOR_PROVIDER_NAME`
- **Invariants:**
  1. CEO/orchestrator resolve only to the canonical local llama-server; experts/judge/auditor resolve only to the authenticated official DeepSeek HTTPS tier. Cross-provider fallback is forbidden.
  2. Loopback is accepted; `bob-ceo:8080` is accepted only under the explicit Docker runtime profile.
  3. `_providers_for_request("ceo")` returns only `[ceo_provider]` (no fallback)
  4. `_max_attempts(providers)` â‰¤ `len(providers)` and â‰¤ `max_fallbacks + 1`
  5. Stream generate yields non-None chunks
  6. `generate()` returns non-empty string or raises `RuntimeError`

## 10. Config System

- **Canonical:** this document
- **Path:** `src/core/config/` (3 files: `schema.py`, `__init__.py`, `secrets.py`)
- **Public surface:**
  - `UniversalConfig` â€” `load(path)`, `from_dict(data)`, `apply_env_overrides()`, `ensure_directories()`
  - `get_config() -> UniversalConfig`
  - `reload_config(path) -> UniversalConfig`
  - Env overrides: `SUPEREZIO_HOST`, `SUPEREZIO_PORT`, `CORS_ORIGINS`
- **Sub-dataclasses:** `ServerConfig`, `ModelConfig`, `GatewayConfig`, `EventHubConfig`, `StorageConfig`, `MemoryConfig`, `ObservabilityConfig`, `TriadeConfig`
- **Invariants:**
  1. `get_config()` returns a singleton (same instance on repeated call)
  2. Server host defaults to `127.0.0.1`, port to `8002`
  3. `from_dict` handles missing sections gracefully with defaults

## 11. SDCA-Lite Firewall

- **Canonical:** this document
- **Path:** `src/core/risk_firewall/` (3 files: `sdca_lite.py`, `sdca_contracts.py`, `experience_memory.py`)
- **Public surface:**
  - `DecisionCandidate(id, asset, action, thesis, risk_context, raw_signals, amount_cad, time_horizon, source)`
  - `GhostTokenReport(expert_name, ghost_tokens, uncertainty, evidence)`
  - `RiskFirewallDecision(decision, confidence, uncertainty, ghost_tokens, ...)`
  - `ConsequenceScore(delivery_7d, revenue_risk, chaos_reduction, truthfulness, cost_risk, utility)`
  - `evaluate_decision_with_sdca(candidate) -> RiskFirewallDecision`
  - `extract_ghost_tokens(candidate) -> list[GhostTokenReport]`
  - `run_rumination(initial_uncertainty, context, ...) -> list[RuminationState]`
  - `score_consequence(candidate, ghost_tokens, experiences) -> ConsequenceScore`
- **Invariants:**
  1. No broker execution â€” purely cognitive
  2. No external API calls
  3. `decision` âˆˆ {`ALLOW`, `BLOCK`, `REVIEW`}
  4. `uncertainty` âˆˆ [0, 1], `confidence` âˆˆ [0, 1], `utility` âˆˆ [0, 1]
  5. Deterministic: same inputs â†’ same outputs

## 12. RAG Forensics

- **Canonical:** this document
- **Path:** `src/core/rag/` (3 files: `fraud_rag.py`, `rag_engine.py`, `macro_dataset.py`)
- **Public surface:**
  - `FraudPatternMatcher(data_dir)` â€” `.search_patterns(query, limit) -> list[str]`, `.search_semantic(query, limit) -> list[str]`
  - `fraud_patterns` (singleton instance)
- **Invariants:**
  1. `search_patterns()` returns at most `limit` results
  2. Falls back to keyword search when sentence-transformers is unavailable
  3. Matches pump_symbols by exact uppercase ticker comparison

## 13. Crisis Models

- **Canonical:** this document
- **Path:** `src/experts/crisis/` (20 files across 6 subdirectories)
- **Public surface:**
  - 12 crisis models in `models/`: `bis_credit_gap`, `credit_asset_growth`, `debt_service_ratio`, `growth_at_risk`, `hawkes_stress`, `imf_mispricing`, `lppls_bubble`, `markov_regime`, `minsky_keen`, `network_contagion`, `shiller_valuation`, `systemic_bank_risk`
  - `CrisisExpert` in `expert/crisis_expert.py`
  - `CrisisEnsemble` in `logic/ensemble.py`
  - `CrisisReport` in `io/report.py`
  - `CrisisSignals` schema in `contracts/schemas.py`
  - `CrisisToolAdapter` in `adapters/tool_adapter.py`
- **Invariants:**
  1. Each model returns a score âˆˆ [0, 1]
  2. `CrisisEnsemble` aggregates 12 models into a single risk signal
  3. `CrisisExpert` exposes a `.predict(data) -> CrisisReport` interface

## 14. PennyLab

- **Canonical:** this document
- **Path:** `src/experts/pennylab/` (14 files, 5 sub-expert agents in `experts/`)
- **Public surface:**
  - 4 experts in `experts/`: `liquidity_risk_expert`, `pump_dump_expert`, `veracity_gate`, `volume_spike_expert`, `whale_print_expert`
  - `PennyLabScoring` in `scoring.py`
  - `PennyLabSchemas` in `schemas.py`
  - `pipeline_hook.py` â€” pipeline integration
  - `rag_hooks.py` â€” fraud RAG integration
  - `cli.py` â€” manual CLI for penny stock analysis
- **Invariants:**
  1. Each expert returns a `PennyLabSignal` with risk level âˆˆ {LOW, MEDIUM, HIGH, CRITICAL}
  2. `PennyLabScoring.composite_score(expert_signals) -> float` âˆˆ [0, 1]
  3. Volume spike detection uses z-score â‰¥ 2.0 as threshold

## 15. Trading Engine

- **Canonical:** this document
- **Path:** `src/core/trading/` (8 files)
- **Public surface:**
  - `BrokerAdapter` interface
  - `KillSwitch` â€” emergency stop
  - `PositionSizer` â€” risk-based position calculation
  - `OrderBuilder` â€” order construction
  - `Alerter` â€” notification system
  - `ApprovalGate` â€” trade approval logic
  - `RewardModel` â€” trade outcome scoring
  - `TradeWeights` â€” risk weights
- **Invariants:**
  1. `KillSwitch` must return `blocked=True` when triggered
  2. `PositionSizer` respects max position â‰¤ 5% of portfolio
  3. No trade executes without `ApprovalGate.passed=True`

## 16. Math Core

- **Canonical:** this document
- **Path:** `src/core/math/` (6 files)
- **Public surface:**
  - `utils.py`: `sigmoid(x)`, `clamp(x, lo, hi)`, `t_norm(a, b)`, `t_conorm(a, b)`
  - `indicators.py`: technical indicators (SMA, EMA, RSI, MACD, Bollinger)
  - `risk.py`: VaR, CVaR, Sharpe, Sortino, max_drawdown
  - `crisis.py`: crisis probability models
  - `financial_engine.py`: DCF, multiples, growth models
  - `trading_losses.py`: loss analysis and recovery planning
- **Invariants:**
  1. `sigmoid(x)` âˆˆ (0, 1) for all finite x
  2. `clamp(x, 0, 1)` âˆˆ [0, 1]
  3. `t_norm(a, b)` â‰¤ min(a, b)
  4. `t_conorm(a, b)` â‰¥ max(a, b)

## 17. Ports (Abstract Interfaces)

- **Canonical:** this document
- **Path:** `src/core/ports/` (5 files)
- **Public surface:**
  - `protocol.py`: `A2AMessage`, `MessageType` (canonical: a2a-protocol contract)
  - `model_gateway.py`: abstract `ModelGatewayPort`
  - `data_collector.py`: abstract `DataCollectorPort`
  - `audit_log.py`: abstract `AuditLogPort`
  - `health_probe.py`: abstract `HealthProbePort`
- **Invariants:**
  1. All ports are abstract (ABC)
  2. Concrete implementations live outside `ports/`

## 18. Explanation Engine

- **Canonical:** this document
- **Path:** `src/core/explanation/` (1 file)
- **Public surface:** `ExplainEngine` with `.generate(final_content, f51_verdict, route) -> str`
- **Invariants:** output is streaming-interpretability text; never empty for non-trivial inputs

## 19. Security

- **Canonical:** this document
- **Path:** `src/core/security/` (1 file)
- **Public surface:** output sanitization, `PRIVATE_CHANNEL_PATTERNS` constants
- **Invariants:** strips known private model channel markers from output

## 20. Observability

- **Canonical:** this document
- **Path:** `src/core/observability/` (3 files)
- **Public surface:**
  - `log_event(domain, action, data)` â€” structured logging
  - `trace_span(name)` â€” context manager / decorator
  - `metrics` â€” counter/increment interface
- **Invariants:** `log_event` never raises; `metrics.increment(key)` is idempotent

## 21. Investor Committee

- **Canonical:** this document
- **Path:** `src/core/investor/` (6 files)
- **Public surface:**
  - 7-agent Family Investor Committee
  - `FraudAnalyst` â€” fraud detection
  - `CostGuard` â€” cost monitoring
  - `Storage` â€” investor data persistence
- **Invariants:** committee decisions require â‰¥ 4/7 majority

## 22. Tool Registry

- **Canonical:** this document
- **Path:** `src/tools/` (1 file)
- **Public surface:** Custom tool registration for LangGraph agent
- **Invariants:** tools are registered with name, description, schema, and handler function

## 23. Adapters

- **Canonical:** this document
- **Path:** `src/adapters/` (4 files in subdirectories)
- **Public surface:**
  - `ibkr_adapter.py`: Interactive Brokers broker adapter
  - `subprocess_collector.py`: external process data collector
  - `health/http_probe.py`: `HttpProbe` â€” TCP/HTTP availability check
  - `quantum_adapter`: quantum computing integration
- **Invariants:** All adapters implement corresponding abstract ports

## 24. Audit

- **Canonical:** this document
- **Path:** `src/core/audit/` (1 file)
- **Public surface:** `record_decision(run_id, step, decision, rationale)` â€” decision audit trail

## 25. Storage

- **Canonical:** this document
- **Path:** `src/core/storage/` (1 file)
- **Public surface:** mem0 client for persistent memory

## 26. F51 Adapter

- **Canonical:** this document
- **Path:** `src/core/f51_adapter/` (1 file)
- **Public surface:** Bridge between pipeline nodes and F51 engine

---

## Init-Only Modules (no source files beyond `__init__.py`)

| Module | Path | Notes |
|--------|------|-------|
| scanner | `src/core/scanner/` | MarketScanner â€” verified as lazily imported in `core.pipeline.nodes` |
| paths | `src/core/paths/` | `PROJECT_ROOT` resolution â€” used across the codebase |
| prompts | `src/core/prompts/` | Single financial prompts file â€” referenced in pipeline |
| data_collector | `src/core/data_collector/` | Has `ProfessionalCollector`, `SubprocessCollector`, scraper (3 files per INVENTORY) |

---

## Contract Test Coverage Matrix

| Module | Dedicated Test | Status |
|--------|---------------|--------|
| agent-server | `test_contract_runtime_official.py` | âœ… Covered |
| pipeline | `test_contract_pipeline.py`, `test_contract_orchestrator.py` | âœ… Covered |
| ceo | `test_contract_ceo.py` | âœ… Covered |
| f51-engine | `test_contract_f51_engine.py` | âœ… Covered |
| data-hub | `test_contract_collector.py` | âœ… Covered |
| neural-decision | `test_contract_neural.py` | âœ… Covered |
| a2a-protocol | `test_contract_a2a.py` | âœ… Covered |
| sdca-firewall | `test_contract_sdca.py` | âœ… Covered |
| rag-forensics | `test_contract_rag.py` | âœ… Covered |
| endpoints | `test_contract_endpoints.py` | âœ… Covered |
| experts | `test_contract_experts.py` | âœ… Covered |
| explanation | `test_contract_explanation.py` | âœ… Covered |
| guardrails | `test_contract_guardrails.py` | âœ… Covered |
| main | `test_contract_main.py` | âœ… Covered |
| **model-serving** | `test_contract_model_serving.py` | ðŸ”´ Missing |
| **config-system** | `test_contract_config.py` | ðŸ”´ Missing |
| **crisis-models** | `test_contract_crisis.py` | ðŸ”´ Missing |
| **pennylab** | via `test_contract_experts.py` | ðŸŸ¡ Partial |
| **trading** | `test_contract_trading.py` | ðŸ”´ Missing |
| **investor** | `test_contract_investor.py` | ðŸ”´ Missing |
| **observability** | via smoke tests | ðŸŸ¡ Partial |
| **math-core** | via `test_contract_f51_engine.py` | ðŸŸ¡ Partial |
| **security** | via `test_contract_guardrails.py` | ðŸŸ¡ Partial |
