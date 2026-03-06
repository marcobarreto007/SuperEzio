# F51 Risk Register — SuperEzio
Generated: 2026-05-15 | Branch: main | Commit: 0dad9f3

## Critical (P0)

| ID | Risk | Module | Detail |
|----|------|--------|--------|
| R01 | Pipeline nodes 100% duplicados | `pipeline/nodes/` | `_mixin.py` tem todas as nodes como metodos de classe; `nodes/*.py` tem as mesmas como funcoes soltas. Qualquer bug fix precisa ser aplicado em dois lugares. |
| R02 | CEO prompts duplicados | `pipeline/ceo_prompts.py` vs `pipeline/prompts/builder.py` | 9 funcoes com logica identica. `ceo_prompts.py` referencia Nemotron-Nano; `builder.py` referencia Gemma-4. Ambos ativos no import graph. |
| R03 | Pipeline sem cobertura de teste | `pipeline/runtime.py`, `pipeline/nodes/`, `pipeline/state.py` | Zero testes. O graph inteiro (orchestrator -> data -> experts -> CEO) nunca e testado end-to-end. |

## High (P1)

| ID | Risk | Module | Detail |
|----|------|--------|--------|
| R04 | `core/engine/` deprecated ainda importado | `core/engine/indicators.py` | Importado por `agent_server/endpoints.py` e `data_collector/collector.py`. Se `core/engine/` for removido, esses dois quebram. |
| R05 | Scanner module missing | `core/scanner/` (empty) | `runtime.py` e `nodes/collector.py` importam `MarketScanner` com `try/except ImportError`. Funcionalidade de market scan esta morta. |
| R06 | 60 modulos sem teste | 60 de 117 modulos src/ | Incluindo: pipeline completo, agent_runtime completo, investor/, data providers, observability/. |
| R07 | `rl/policy.py` scaffold sem teste | `core/rl/policy.py` | 14 linhas, experimental, sem cobertura. |

## Medium (P2)

| ID | Risk | Module | Detail |
|----|------|--------|--------|
| R08 | Diretorios vazios | `core/scanner/`, `core/mathcore/`, `core/evidence/` | Ocupam namespace, podem causar confusao de imports. |
| R09 | `financial_prompts.py` overlap parcial | `core/prompts/financial_prompts.py` | Importado por `ceo_prompts.py` (old) mas nao por `prompts/builder.py` (new). Transicao incompleta. |
| R10 | `math/indicators.py` vs `engine/indicators.py` overlap | `core/math/` vs `core/engine/` | Mesmos 5 indicadores, return types diferentes (scalar vs series). Fonte canonica e `core/math/`. |
| R11 | 55 env vars sem centralizacao | Espalhadas por 20+ arquivos | Nao ha `.env.example` ou schema centralizado. `config/schema.py` parcialmente cobre. |
| R12 | `scripts/server.py` orphan | `scripts/server.py` | Nao referenciado em nenhum lugar. Destino desconhecido. |

## Low (P3)

| ID | Risk | Module | Detail |
|----|------|--------|--------|
| R13 | Docs em `docs/architecture/archives/` | Varios .md | Reports de auditoria antigos. Podem conter info desatualizada. |
| R14 | `docs/internal/SECURITY_LEAKED_KEYS.md` | docs/ | Documenta keys vazadas. Deve estar em .gitignore ou removido se as keys foram rotacionadas. |
