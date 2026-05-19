# Test Map — SuperEzio

> Atualizado: 2026-05-19 | Branch: main | Session: f51-inventory-full-scan
> Total: 32 test files, ~530 test functions

---

## Suite Principal — `tests/` (23 files)

### Smoke & Pipeline (3 files)

| Arquivo | Escopo | Tipo | Testes |
|---------|--------|------|--------|
| `test_pipeline_smoke.py` | Pipeline v4 completo | Smoke | ~8 |
| `test_rag_engine_smoke.py` | ForensicRAG engine | Smoke | ~5 |
| `test_gateway.py` | ModelGateway routing + fallback | Unitário | ~28 |

### Componentes (4 files)

| Arquivo | Escopo | Testes |
|---------|--------|--------|
| `test_components_crisis.py` | CrisisMath ensemble (12 modelos) | ~20 |
| `test_components_data.py` | Data providers + ModelProvider + DataHub | ~22 |
| `test_components_f51.py` | F51 engine, formulas, SpiderSense, gates, scoring | ~28 |
| `test_components_pennylab.py` | PennyLab 4 experts + scoring + RAG | ~15 |

### Motor F51 (3 files)

| Arquivo | Escopo | Testes |
|---------|--------|--------|
| `test_f51_engine.py` | F51Engine.run() — graph execution | ~17 |
| `test_f51_formulas.py` | Fórmulas canônicas (8 classes) | ~22 |
| `test_math.py` | Indicadores técnicos + risk metrics | ~38 |

### Experts (3 files)

| Arquivo | Escopo | Testes |
|---------|--------|--------|
| `test_crisis.py` | Crisis expert models detalhado | ~35 |
| `test_pennylab.py` | PennyLab experts detalhado | ~54 |
| `test_neural_decision.py` | NeuralDecisionExpert + API | 20 |

### SDCA / Risk Firewall (1 file)

| Arquivo | Escopo | Testes |
|---------|--------|--------|
| `test_sdca_lite.py` | SDCA-Lite risk firewall + endpoint | 15 |

### Runtime (2 files)

| Arquivo | Escopo | Testes |
|---------|--------|--------|
| `test_runtime_smoke.py` | Runtime smoke (FastAPI, A2A, pipeline, F51, CEO) | ~17 |
| `test_integration_runtime.py` | Integration (requer CEO + API live) | ~8 |

### Trading/RL (5 files) — EXPERIMENTAL

| Arquivo | Escopo | Testes |
|---------|--------|--------|
| `test_trading_loop1.py` | PositionSizer + KillSwitch | ~25 |
| `test_trading_loop2.py` | SimulatedBroker + OrderBuilder | ~22 |
| `test_trading_loop3.py` | ApprovalGate + Alerters | ~22 |
| `test_trading_loop4.py` | ExpertWeightRouter | ~20 |
| `test_trading_loop5.py` | RewardFunction + Dataset + LoRA | ~24 |

### Sanitizer (1 file)

| Arquivo | Escopo | Testes |
|---------|--------|--------|
| `test_model_sanitizer.py` | Model output sanitizer | 2 |

### Market Scanner (1 file)

| Arquivo | Escopo | Testes |
|---------|--------|--------|
| `test_market_scanner.py` | Intent parsing + MarketScanner | 3 |

---

## Suite de Contratos — `tests/contracts/` (9 files)

| Arquivo | Contrato Testado | Testes |
|---------|------------------|--------|
| `test_contract_main.py` | Agent server main — app creation, routes, middleware | 7 |
| `test_contract_endpoints.py` | API endpoints — routes, sanitizers, capabilities | 10 |
| `test_contract_explanation.py` | ExplainEngine — formatting, confidence, LoRA path | 10 |
| `test_contract_rag.py` | ForensicRAG + FraudRAG — search, format, singleton | 10 |
| `test_trading_losses.py` | Trading loss functions — directional, Sharpe, quantile | ~26 |
| `test_contract_a2a.py` | A2A Protocol — messages, types, roundtrip | 16 |
| `test_contract_pipeline.py` | Pipeline state contracts — TypedDicts, reducers | 13 |
| `test_contract_f51_engine.py` | F51 engine invariants — formulas, gates | ~35 |
| `test_contract_ceo.py` | CEO prompt builder — system prompt, modules | ~32 |

---

## Infra de Teste

| Arquivo | Função |
|---------|--------|
| `conftest.py` | Fixtures: canned_technicals, fake_gateway, skip_gateway, env setup |
| `helpers.py` | Utilidades: CANNED_DATA, FakeProvider, FakeGateway, FakeAsyncGenerator |

---

## Cobertura por Módulo

| Módulo | Testes | Status |
|--------|--------|--------|
| `src/f51/` | test_f51_engine, test_f51_formulas, test_components_f51 | COBERTO |
| `src/core/math/` | test_math, test_trading_losses | COBERTO |
| `src/core/pipeline/` | test_pipeline_smoke, test_market_scanner | COBERTO |
| `src/core/model_serving/` | test_gateway, test_model_sanitizer | COBERTO |
| `src/core/rag/` | test_rag_engine_smoke, test_contract_rag | COBERTO |
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

## Scripts de Teste (não-pytest)

| Script | Tipo | Requer |
|--------|------|--------|
| `scripts/eval_pipeline.py` | E2E com juiz GLM | Servidor + proxy :8899 |
| `scripts/financial_quality_benchmark.py` | 50Q financeiro | Servidor :8002 |
| `scripts/trick_questions_test.py` | 20Q raciocínio | Servidor :8002 |
| `scripts/investment_test.py` | 3 cenários | Servidor :8002 |

---

## Comandos

```bash
# Suite completa
python -m pytest tests/ -q

# Smoke
python -m pytest tests/test_pipeline_smoke.py -q

# Contratos
python -m pytest tests/contracts/ -q

# Componentes
python -m pytest tests/test_components_*.py -q

# SDCA
python -m pytest tests/test_sdca_lite.py -q
```

---

## Lacunas

5 módulos sem testes:
1. `src/core/investor/` — lógica de investidor
2. `src/core/config/` — carregamento de config
3. `src/core/observability/` — debug logger, notificações
4. `src/core/security/` — segurança
5. `src/experts/technical_neural/` — expert técnico neural

**Recomendação:** Priorizar testes para `config/` (impacto em runtime) e `security/` (impacto em segurança).
