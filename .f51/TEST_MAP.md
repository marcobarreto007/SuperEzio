# Test Map — SuperEzio

> Atualizado: 2026-05-17 | Branch: main | 510 testes coletados

## Suite Principal (22 arquivos, 510 testes)

### Smoke & Pipeline (3)
| Arquivo | Escopo | Tipo |
|---------|--------|------|
| `test_pipeline_smoke.py` | Pipeline completo | Smoke |
| `test_rag_engine_smoke.py` | RAG engine | Smoke |
| `test_gateway.py` | Model gateway + fallback | Unitario |

### Componentes (4)
| Arquivo | Escopo |
|---------|--------|
| `test_components_crisis.py` | CrisisMath (12 modelos) |
| `test_components_data.py` | Data providers + collector |
| `test_components_f51.py` | F51 engine, formulas, SpiderSense |
| `test_components_pennylab.py` | PennyLab (4 experts) |

### Motor F51 (3)
| Arquivo | Escopo |
|---------|--------|
| `test_f51_engine.py` | F51Engine.run() — contrato publico |
| `test_f51_formulas.py` | Formulas matematicas canonicas |
| `test_math.py` | Indicadores tecnicos (SMA, MACD, RSI, BB) |

### Experts (3)
| Arquivo | Escopo |
|---------|--------|
| `test_crisis.py` | Crisis expert models |
| `test_pennylab.py` | PennyLab experts |
| `test_neural_decision.py` | Neural decision expert |

### Contratos (5)
| Arquivo | Escopo |
|---------|--------|
| `contracts/test_contract_endpoints.py` | API endpoints |
| `contracts/test_contract_explanation.py` | Explanation engine |
| `contracts/test_contract_main.py` | Agent server main |
| `contracts/test_contract_rag.py` | RAG forense |
| `contracts/test_trading_losses.py` | Trading losses math |

### Trading/RL (5)
| Arquivo | Escopo | Status |
|---------|--------|--------|
| `test_trading_loop1.py` | Trading loop 1 | Experimental |
| `test_trading_loop2.py` | Trading loop 2 | Experimental |
| `test_trading_loop3.py` | Trading loop 3 | Experimental |
| `test_trading_loop4.py` | Trading loop 4 | Experimental |
| `test_trading_loop5.py` | RL reward + LoRA training | Experimental |

### Sanitizer (1)
| Arquivo | Escopo |
|---------|--------|
| `test_model_sanitizer.py` | Model output sanitizer |

### Helpers (1)
| Arquivo | Escopo |
|---------|--------|
| `helpers.py` | Funcoes auxiliares compartilhadas |

### Config (1)
| Arquivo | Escopo |
|---------|--------|
| `conftest.py` | Fixtures pytest (session, event loop) |

## Cobertura por Modulo

| Modulo | Testes | Status |
|--------|--------|--------|
| `src/f51/` | test_f51_engine, test_f51_formulas, test_components_f51 | Coberto |
| `src/core/math/` | test_math, contracts/test_trading_losses | Coberto |
| `src/core/pipeline/` | test_pipeline_smoke | Coberto |
| `src/core/model_serving/` | test_gateway, test_model_sanitizer | Coberto |
| `src/core/rag/` | test_rag_engine_smoke | Coberto |
| `src/experts/crisis/` | test_crisis, test_components_crisis | Coberto |
| `src/experts/pennylab/` | test_pennylab, test_components_pennylab | Coberto |
| `src/experts/neural_decision/` | test_neural_decision | Coberto |
| `src/data/` | test_components_data | Coberto |
| `src/agent_server/` | contracts/* | Coberto |
| `src/core/trading/` | test_trading_loop1-5 | Experimental |
| `src/core/investor/` | — | Nao testado diretamente |
| `src/core/config/` | — | Nao testado diretamente |
| `src/core/observability/` | — | Nao testado |
| `src/core/security/` | — | Nao testado |
| `src/core/explanation/` | contracts/test_contract_explanation | Coberto |
| `src/core/f51_adapter/` | test_components_f51 | Coberto |
| `src/experts/technical_neural/` | — | Nao testado |

## Politica de Testes
- Deterministicos (sem random seed nao fixada)
- Sem mock de LLM
- Sem dependencia de rede para unitarios
- CEO tests requerem modelo local (podem falhar se offline)
