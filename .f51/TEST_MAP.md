# F51 Test Map

Updated: 2026-05-21T20:30:00-04:00
Session: f51-inventory-full-sweep

## Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 + pytest-asyncio 0.23 |
| Config | pyproject.toml [tool.pytest.ini_options] |
| Async mode | auto |
| Min version | 8.0 |
| Coverage | pytest-cov 5.0 available |
| Total test files | 42 |

## Test Markers

| Marker | Purpose | Approx Count |
|--------|---------|--------------|
| `smoke` | Fast runtime and pipeline liveness tests | ~20 |
| `contract` | Public API surface and data invariant tests | ~15 |
| `integration` | Requires live CEO (:8082) + API (:8002), auto-skips offline | ~7 |
| `slow` | Tests taking > 5 seconds | unknown |

## Smoke Tests

### `test_pipeline_smoke.py` — 7 tests

| Test | Validates | Classification |
|------|-----------|----------------|
| Pipeline graph builds | graph.py compiles | pipeline |
| Has expected agentic nodes | orchestrator_primary, agent, tool_executor, explanation, respond_blocked | pipeline |
| Async streaming | NDJSON output works | pipeline |
| General route reaches CEO | End-to-end casual message | pipeline |

### `test_runtime_smoke.py` — 12 tests

| Test | Validates | Classification |
|------|-----------|----------------|
| FastAPI app imports | main.py loads | app |
| App title | Metadata correct | app |
| Health route | /health responds | app |
| Task/submit route | POST endpoint exists | app |
| A2A message roundtrip | Protocol works | core |
| Pipeline graph builds | graph.py from main | pipeline |
| F51 engine smoke | F51Engine instantiates | core |
| CEO prompt builder | Prompt generation | core |
| NeuralDecisionExpert | Instantiation | core |
| DataHub instantiation | Provider loading | core |
| Protocol enums | MessageType values | core |

## Contract Tests (`tests/contracts/`)

### 15 contract test files

| File | Surface Tested | Classification |
|------|----------------|----------------|
| `test_contract_pipeline.py` | PipelineState, IntentResult, CEORequest, ExpertCall, reducer | pipeline |
| `test_contract_endpoints.py` | Route registration, ticker sanitization, OHLCV builder, error helpers | app |
| `test_contract_ceo.py` | CEO node interface | pipeline |
| `test_contract_a2a.py` | A2A protocol | core |
| `test_contract_explanation.py` | Explanation engine | core |
| `test_contract_experts.py` | Expert fan-in | core |
| `test_contract_orchestrator.py` | Intent classification | pipeline |
| `test_contract_collector.py` | Data collection | core |
| `test_contract_rag.py` | RAG engine | core |
| `test_contract_sdca.py` | SDCA firewall | core |
| `test_contract_guardrails.py` | Pipeline guardrails | pipeline |
| `test_contract_main.py` | Main app lifecycle | app |
| `test_contract_neural.py` | Neural decision | core |
| `test_contract_f51_engine.py` | F51 verdict engine | core |
| `test_contract_runtime_official.py` | Runtime official contract | app |
| `test_trading_losses.py` | Trading loss calculations | core |

## Integration Tests

### `test_integration_runtime.py` — 7 tests (auto-skips if servers offline)

| Test | Requires | Classification |
|------|----------|----------------|
| Health endpoints | API :8002 | app |
| Task/submit SSE stream (casual) | CEO :8082 + API :8002 | pipeline |
| Task/submit SSE stream (ticker analysis) | CEO :8082 + API :8002 | pipeline |
| Capabilities endpoint | API :8002 | app |
| Product manifest | API :8002 | app |

## Domain Tests (top-level)

| File | Domain | Classification |
|------|--------|----------------|
| `test_f51_engine.py` | F51 verdict engine | core |
| `test_f51_formulas.py` | Platinum formula math | core |
| `test_math.py` | Financial math (indicators, risk) | core |
| `test_model_sanitizer.py` | Output sanitization | core |
| `test_crisis.py` | Crisis models ensemble | core |
| `test_neural_decision.py` | Neural decision expert | core |
| `test_gateway.py` | Model gateway + providers | core |
| `test_market_scanner.py` | Market scanner (FinanceDatabase) | core |
| `test_rag_engine_smoke.py` | RAG engine | core |
| `test_sdca_lite.py` | SDCA cognitive firewall | core |
| `test_pennylab.py` | PennyLab experts | core |
| `test_components_data.py` | Data providers | core |
| `test_components_f51.py` | F51 components | core |
| `test_components_crisis.py` | Crisis components | core |
| `test_components_pennylab.py` | PennyLab components | core |
| `test_trading_loop1-5.py` | Trading loops 1-5 | core |

## Test Infrastructure

| File | Purpose | Classification |
|------|---------|----------------|
| `conftest.py` | Shared fixtures: FakeGateway, FakeProvider, canned data, skip_gateway | test |
| `helpers.py` | Canned data dictionaries and fake classes | test |
| `contracts/__init__.py` | Package init | test |

## Test Coverage Gaps

| Area | Has Tests? | Gap |
|------|-----------|-----|
| `src/agent_server/` | Yes (smoke + contract) | Covered |
| `src/core/pipeline/` | Yes (smoke + contract) | Post-refactor alignment needed |
| `src/core/model_serving/` | Yes (test_gateway) | Covered |
| `src/data/` | Yes (test_components_data) | Covered |
| `src/f51/` | Yes (test_f51_engine + formulas) | Covered |
| `src/core/rag/` | Yes (test_rag_engine_smoke) | Covered |
| `src/core/trading/` | Yes (5 trading loop tests) | Covered |
| `src/core/investor/` | No dedicated test | **GAP** |
| `src/core/audit/` | No dedicated test | Low risk |
| `src/core/security/` | test_model_sanitizer covers sanitization | Partial |
| `src/core/storage/` | No dedicated test | Low risk |
| `src/experts/_archive/technical_neural/` | Deleted completely | Deleted |
| `src/tools/` | No dedicated test | **GAP** |
| `src/adapters/` | No dedicated test | Low risk |
| Frontend JS | No automated tests | Known — manual E2E only |
| SSE event sequence | Not verified post-refactor | **GAP** |

## Last Known Test Result

- **Date**: 2026-05-22 (Full clean-up verification)
- **Result**: 788 passed, 8 skipped, 7 warnings, 29.08s
- **Caveat**: All active contract, smoke, and domain tests pass.

