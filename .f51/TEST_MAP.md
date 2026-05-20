# Test Map — SuperEzio

> Atualizado: 2026-05-20 | Commit: `02a64ca` | 33 arquivos, 653 testes, 0 falhas

---

## Contratos — `tests/contracts/` (9 arquivos, 159 testes)

| Arquivo | Contrato Testado | Testes | Tipo |
|---------|------------------|--------|------|
| `test_contract_f51_engine.py` | F51 formulas + gates invariants | 42 | Contract |
| `test_contract_ceo.py` | CEO prompt builder, system prompt, modules | 31 | Contract |
| `test_trading_losses.py` | Trading loss functions (directional, Sharpe, quantile) | 25 | Contract |
| `test_contract_a2a.py` | A2A Protocol (messages, types, roundtrip) | 13 | Contract |
| `test_contract_pipeline.py` | Pipeline state contracts (TypedDicts, reducers) | 13 | Contract |
| `test_contract_endpoints.py` | API endpoints (routes, sanitizers, capabilities) | 10 | Contract |
| `test_contract_explanation.py` | ExplainEngine (formatting, confidence, LoRA path) | 9 | Contract |
| `test_contract_rag.py` | ForensicRAG + FraudRAG (search, format, singleton) | 9 | Contract |
| `test_contract_main.py` | Agent server main (app creation, routes, middleware) | 7 | Contract |

---

## Unitários / Componentes — `tests/` (16 arquivos, 374 testes)

| Arquivo | Escopo | Testes | Tipo |
|---------|--------|--------|------|
| `test_pennylab.py` | PennyLab 4 experts + schemas + scoring | 56 | Unit |
| `test_crisis.py` | Crisis 12 models + ensemble + contracts | 51 | Unit |
| `test_math.py` | Math utils, indicators (RSI, MACD, BB), risk | 37 | Unit |
| `test_gateway.py` | ModelGateway routing, fallback, DeepSeek options | 28 | Unit |
| `test_components_data.py` | Config files, model_serving, provider names | 27 | Component |
| `test_components_f51.py` | F51 formulas, SpiderSense, gates, scoring, graph | 27 | Component |
| `test_f51_formulas.py` | F51 formulas canônicas | 26 | Unit |
| `test_components_crisis.py` | Crisis logic, models, contracts validation | 25 | Component |
| `test_neural_decision.py` | NeuralDecisionExpert + API via TestClient | 20 | Unit |
| `test_components_pennylab.py` | PennyLab schemas, experts, RAG hooks | 16 | Component |
| `test_f51_engine.py` | F51Engine.run() graph execution | 15 | Unit |
| `test_sdca_lite.py` | SDCA-Lite risk firewall + experience memory | 14 | Unit |
| `test_pipeline_smoke.py` | Pipeline v4 (build_graph, PipelineApp) | 8 | Unit |
| `test_market_scanner.py` | Intent parsing + MarketScanner | 3 | Unit |
| `test_model_sanitizer.py` | Model output sanitizer (PrivateChannelFilter) | 2 | Unit |

---

## Trading Loop (Experimental) — `tests/` (5 arquivos, 112 testes)

| Arquivo | Escopo | Testes | Status |
|---------|--------|--------|--------|
| `test_trading_loop1.py` | PositionSizer + KillSwitch | 24 | Experimental |
| `test_trading_loop2.py` | SimulatedBroker + OrderBuilder | 20 | Experimental |
| `test_trading_loop3.py` | ApprovalGate + Alerters | 24 | Experimental |
| `test_trading_loop4.py` | ExpertWeightRouter | 20 | Experimental |
| `test_trading_loop5.py` | RewardFunction + DatasetBuilder + LoRATrainer | 24 | Experimental |

---

## Smoke — `tests/` (1 arquivo, 20 testes)

| Arquivo | Escopo | Testes | Tipo |
|---------|--------|--------|------|
| `test_runtime_smoke.py` | FastAPI, config, env, ports, imports, frontend | 20 | Smoke |

---

## Integração — `tests/` (1 arquivo, 7 testes)

| Arquivo | Escopo | Testes | Requer |
|---------|--------|--------|--------|
| `test_integration_runtime.py` | CEO health, API health, task submit, NDJSON | 7 | Servidores live (:8082, :8002) |

---

## Infra de Teste

| Arquivo | Função |
|---------|--------|
| `tests/conftest.py` | Fixtures: canned_technicals, fake_gateway, skip_gateway, env setup |
| `tests/helpers.py` | Canned data, FakeProvider, FakeGateway, FakeAsyncGenerator |
| `tests/contracts/__init__.py` | Torna contracts um pacote Python |

---

## Scripts de Teste Não-Pytest

| Script | Tipo | Requer |
|--------|------|--------|
| `scripts/eval_pipeline.py` | E2E com juiz GLM | Servidor + proxy :8899 |
| `scripts/trick_questions_test.py` | 20Q raciocínio lógico | Servidor :8002 |
| `scripts/investment_test.py` | 3 cenários de investimento | Servidor :8002 |

---

## Cobertura por Módulo

| Módulo | Testes | Status |
|--------|--------|--------|
| `src/f51/` | test_f51_engine, test_f51_formulas, test_components_f51 | COBERTO |
| `src/core/math/` | test_math, test_trading_losses | COBERTO |
| `src/core/pipeline/` | test_pipeline_smoke, test_market_scanner | COBERTO |
| `src/core/model_serving/` | test_gateway, test_model_sanitizer | COBERTO |
| `src/core/rag/` | test_contract_rag | COBERTO |
| `src/core/explanation/` | test_contract_explanation | COBERTO |
| `src/core/risk_firewall/` | test_sdca_lite | COBERTO |
| `src/experts/crisis/` | test_crisis, test_components_crisis | COBERTO |
| `src/experts/pennylab/` | test_pennylab, test_components_pennylab | COBERTO |
| `src/experts/neural_decision/` | test_neural_decision | COBERTO |
| `src/data/` | test_components_data | COBERTO |
| `src/agent_server/` | test_contract_main, test_contract_endpoints | COBERTO |
| `src/core/trading/` | test_trading_loop1-5 | EXPERIMENTAL |
| `src/core/investor/` | — | NÃO TESTADO |
| `src/core/config/` | — | NÃO TESTADO |
| `src/core/observability/` | — | NÃO TESTADO |
| `src/core/security/` | — | NÃO TESTADO |
| `src/experts/technical_neural/` | — | NÃO TESTADO |
| `src/adapters/` | — | NÃO TESTADO |
| `src/core/data_collector/` | — | NÃO TESTADO |

---

## Comandos

```bash
# Suite completa
python -m pytest tests/ -q

# Só contratos
python -m pytest tests/contracts/ -q

# Smoke + componentes
python -m pytest tests/test_pipeline_smoke.py tests/test_components_*.py -q

# SDCA
python -m pytest tests/test_sdca_lite.py -q

# Trading loops (experimental)
python -m pytest tests/test_trading_loop*.py -q
```

---

## Lacunas

7 módulos sem cobertura de teste:
1. `src/core/investor/` — comitê, fraud analyst, storage (deprecated)
2. `src/core/config/` — carregamento de config, secrets
3. `src/core/observability/` — debug logger, event hub, neural log
4. `src/core/security/` — input validation, rate limiting (deprecated)
5. `src/experts/technical_neural/` — expert técnico neural
6. `src/adapters/` — broker, data collector, health probe
7. `src/core/data_collector/` — collector, professional, scraper

**Recomendação**: Priorizar `config/` (impacto em runtime) e `data_collector/` (pipeline dependency).
