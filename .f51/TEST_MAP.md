# F51 Test Map — SuperEzio

Este arquivo mapeia de forma exaustiva a suíte de testes do ecossistema SuperEzio, classificando por tipo, arquivo e comando canônico de execução.

---

## 1. Testes de Contrato (`test`)

Focados na integridade de contratos públicos, schemas e assinaturas de métodos. Garantem compatibilidade e previnem alterações silenciosas de API.

| Arquivo | Componente / API | Comando Canônico | Descrição |
|---|---|---|---|
| `tests/contracts/test_contract_main.py` | Universal Core Contract | `python -m pytest tests/contracts/test_contract_main.py` | Valida assinaturas e conformidade do Universal Core |
| `tests/contracts/test_contract_endpoints.py` | API Endpoints | `python -m pytest tests/contracts/test_contract_endpoints.py` | Garante integridade do contrato HTTP de `/task/submit` e `/capabilities` |
| `tests/contracts/test_contract_explanation.py` | Explanation Engine | `python -m pytest tests/contracts/test_contract_explanation.py` | Valida a resposta estruturada do Explanation Engine |
| `tests/contracts/test_contract_rag.py` | RAG Engine | `python -m pytest tests/contracts/test_contract_rag.py` | Protege os schemas de saída do FraudRAG e do MacroDataset |

---

## 2. Testes de Componentes e Integração (`test`)

Testes que validam o comportamento e a comunicação inter-módulo de componentes acoplados sem dependência de serviços externos reais (usando mocks controlados de infraestrutura).

| Arquivo | Módulo Alvo | Comando Canônico | Descrição |
|---|---|---|---|
| `tests/test_components_crisis.py` | `experts/crisis/` | `python -m pytest tests/test_components_crisis.py` | Valida a lógica de integração do Comitê de Crise e normalizações |
| `tests/test_components_data.py` | `core/data_collector/` | `python -m pytest tests/test_components_data.py` | Valida o fluxo do coletor de evidências e scrapers locais |
| `tests/test_components_f51.py` | `core/f51_adapter/` | `python -m pytest tests/test_components_f51.py` | Valida o adaptador de regras F51 e conformidade da Tríade |
| `tests/test_components_pennylab.py` | `experts/pennylab/` | `python -m pytest tests/test_components_pennylab.py` | Valida a integração das regras de penny stock e whales do PennyLab |

---

## 3. Testes Unitários de Lógica e Matemática (`test`)

Testes puramente funcionais e determinísticos focados em algoritmos matemáticos, fórmulas, normalização de dados e heurísticas sem efeitos colaterais.

| Arquivo | Módulo Alvo | Comando Canônico | Descrição |
|---|---|---|---|
| `tests/test_math.py` | `core/math/` | `python -m pytest tests/test_math.py` | Valida utilitários matemáticos e desvios de volatilidade |
| `tests/test_crisis.py` | `experts/crisis/logic/` | `python -m pytest tests/test_crisis.py` | Valida a matemática de Minsky Keen, Shiller, LPPs e outros 10 modelos de estresse |
| `tests/test_f51_formulas.py` | `src/f51/formulas.py` | `python -m pytest tests/test_f51_formulas.py` | Valida cálculos e limites de fórmulas F51 |
| `tests/test_f51_engine.py` | `src/f51/` | `python -m pytest tests/test_f51_engine.py` | Valida gates, detectores e pontuação F51 |
| `tests/test_pennylab.py` | `experts/pennylab/experts/` | `python -m pytest tests/test_pennylab.py` | Valida algoritmos de Whale Print, Volume Spike e Pump and Dump |
| `tests/test_model_sanitizer.py` | `core/model_serving/sanitizer.py` | `python -m pytest tests/test_model_sanitizer.py` | Valida a sanitização de inputs de prompt e remoção de injeções |
| `tests/test_gateway.py` | `core/model_serving/gateway.py` | `python -m pytest tests/test_gateway.py` | Valida o gateway de modelos e balanceador de carga |
| `tests/test_rag_engine_smoke.py` | `core/rag/` | `python -m pytest tests/test_rag_engine_smoke.py` | Smoke-test rápido de vetores locais e embeddings |

---

## 4. Testes de Fluxo e Loop de Negócio (`test`)

Simulações completas de trading e pipelines de decisão executando fluxos seqüenciais determinísticos (Trading Loops) para atestar a estabilidade operacional da lógica principal de negócios.

| Arquivo | Escopo | Comando Canônico | Descrição |
|---|---|---|---|
| `tests/test_pipeline_smoke.py` | Pipeline Geral | `python -m pytest tests/test_pipeline_smoke.py` | Smoke-test da execução seqüencial do pipeline |
| `tests/test_trading_loop1.py` | Trading Loop 1 | `python -m pytest tests/test_trading_loop1.py` | Loop básico de decisões determinísticas baseadas em evidências |
| `tests/test_trading_loop2.py` | Trading Loop 2 | `python -m pytest tests/test_trading_loop2.py` | Simulação de trading com comitê de risco P2 |
| `tests/test_trading_loop3.py` | Trading Loop 3 | `python -m pytest tests/test_trading_loop3.py` | Fluxo de estresse macroeconômico com comitê de crise |
| `tests/test_trading_loop4.py` | Trading Loop 4 | `python -m pytest tests/test_trading_loop4.py` | Loop de decisão de penny-stocks sob monitoramento forense |
| `tests/test_trading_loop5.py` | Trading Loop 5 | `python -m pytest tests/test_trading_loop5.py` | Execução integrada com múltiplos coletores assíncronos em concorrência |

---

## 5. Comando Geral de Evidência

Para rodar **toda a suíte de testes de forma concisa** e verificar regressões:
```bash
python -m pytest tests/ -q
```
