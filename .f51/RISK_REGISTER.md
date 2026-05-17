# F51 Risk Register — SuperEzio
Generated: 2026-05-15 | Updated: 2026-05-17 | Branch: main

## Critical (P0)

| ID | Risk | Module | Detail |
|----|------|--------|--------|
| R01 | Pipeline nodes 100% duplicados | **[RESOLVIDO 2026-05-17]** | `_mixin.py` ja nao existia. Nodes estao unificados em `nodes/*.py` como funcoes async puras. Graph importa diretamente sem duplicacao. |
| R02 | CEO prompts duplicados | **[RESOLVIDO 2026-05-17]** | `ceo_prompts.py` ja nao existia. Prompts unificados em `prompts/builder.py` + `prompts/gemma.py`. Model branching removido — so Qwen3.6-35B. |
| R03 | Pipeline sem cobertura de teste | `pipeline/` | Zero testes end-to-end. O graph inteiro (orchestrator -> data -> experts -> CEO) nunca e testado integrado. |

## High (P1)

| ID | Risk | Module | Detail |
|----|------|--------|--------|
| R04 | `core/engine/` deprecated ainda importado | **[RESOLVIDO]** | Removido. Todos migrados para `core/math/`. |
| R05 | Scanner module missing | **[RESOLVIDO]** | Removido. Graph agora roda clean com data collectors novos. |
| R06 | 60 modulos sem teste | 60 de 117 modulos src/ | Incluindo: pipeline completo, agent_runtime completo, investor/, data providers, observability/. |
| R07 | `rl/policy.py` scaffold sem teste | **[RESOLVIDO]** | Módulo expurgado da branch main. |
| R15 | Coletores com campos `None` opcionais | `core/f51_adapter/adapter.py`, `core/data_collector/` | Provedores externos (TwelveData, AlphaVantage) podem falhar ou retornar nulo, gerando TypeErrors na coerção de float() durante a montagem de claims e verdicts. |

## Medium (P2)

| ID | Risk | Module | Detail |
|----|------|--------|--------|
| R08 | Diretorios vazios | **[RESOLVIDO]** | `core/scanner/`, `core/mathcore/`, `core/evidence/` totalmente excluídos. |
| R09 | `financial_prompts.py` overlap parcial | **[RESOLVIDO 2026-05-17]** | `ceo_prompts.py` e `financial_prompts.py` removidos. Builder unificado em `prompts/builder.py`. |
| R10 | `math/indicators.py` vs `engine/indicators.py` overlap | **[RESOLVIDO]** | `core/engine/` removido. Fonte canônica agora é apenas `core/math/`. |
| R11 | 55 env vars sem centralizacao | **[RESOLVIDO]** | Centralizado em `.env.example` mapeado e documentado. |
| R12 | `scripts/server.py` orphan | **[RESOLVIDO]** | Arquivo órfão expurgado. |
| R16 | Falso Positivo no Ticker Router | **[RESOLVIDO]** | `intents.py` sequestrava siglas (ITM, XYZ) como tickers. Arrumado com delimitações de Regex. |

## Low (P3)

| ID | Risk | Module | Detail |
|----|------|--------|--------|
| R13 | Docs em `docs/architecture/archives/` | Varios .md | Reports de auditoria antigos. Podem conter info desatualizada. |
| R14 | `docs/internal/SECURITY_LEAKED_KEYS.md` | docs/ | Documenta keys vazadas. Deve estar em .gitignore ou removido se as keys foram rotacionadas. |
