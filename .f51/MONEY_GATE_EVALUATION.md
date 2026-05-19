# Money Gate Evaluation — SuperEzio

> Data: 2026-05-19 | Session: f51-money-gate

## Critérios

1. Ajuda entrega em 7 dias?
2. Ajuda receita em 30 dias?
3. Reduz caos operacional?
4. Protege estabilidade?
5. Possui checkpoint ativo?

---

## Frentes Abertas

### F1 — Consolidar configs stale (R1: model_manifest, runtime.yml, pyproject.toml)
| Critério | Resposta |
|----------|----------|
| 7 dias? | Não — cosmetic, não afeta runtime |
| 30 dias? | Não — não gera receita direta |
| Caos? | SIM — referência a modelo errado confunde |
| Estabilidade? | Não — configs não são lidos em runtime |
| Checkpoint? | SIM |
| **Decisão** | **DEFER** — baixa prioridade. Fazer quando for mexer no config anyway. |

### F2 — Consolidar GatewayConfig duplicado (R9)
| Critério | Resposta |
|----------|----------|
| 7 dias? | Não — já funciona |
| 30 dias? | Indiretamente — reduz chance de bug futuro |
| Caos? | SIM — dois arquivos com mesma classe |
| Estabilidade? | SIM — elimina shadowing |
| Checkpoint? | SIM — **FEITO nesta sessão** |
| **Decisão** | **DONE** — resolvido em f51-refactor. |

### F3 — Consolidar indicadores técnicos duplicados (R10)
| Critério | Resposta |
|----------|----------|
| 7 dias? | Não |
| 30 dias? | Indiretamente |
| Caos? | SIM |
| Estabilidade? | SIM — mas comportamento diverge, precisa teste dedicado |
| Checkpoint? | SIM |
| **Decisão** | **DEFER** — risco de quebra > ganho. Fazer com testes dedicados. |

### F4 — Integrar core/trading/ ao pipeline (R4)
| Critério | Resposta |
|----------|----------|
| 7 dias? | Não — trabalho grande |
| 30 dias? | **SIM** — trading funcional = produto vendável |
| Caos? | Não — código já existe e está testado |
| Estabilidade? | Não — desconectado |
| Checkpoint? | SIM |
| **Decisão** | **GO** — mas com plano. É a maior alavanca de receita. |

### F5 — Integrar technical_neural (R5)
| Critério | Resposta |
|----------|----------|
| 7 dias? | Não |
| 30 dias? | Talvez — se melhorar qualidade de análise |
| Caos? | Não |
| Estabilidade? | Não — código morto |
| Checkpoint? | SIM |
| **Decisão** | **DEFER** — baixa alavancagem vs trading. |

### F6 — Testar 5 módulos sem cobertura (R12)
| Critério | Resposta |
|----------|----------|
| 7 dias? | Não |
| 30 dias? | Indiretamente — protege contra regressão |
| Caos? | Não |
| Estabilidade? | **SIM** — cobre lacunas |
| Checkpoint? | SIM |
| **Decisão** | **GO para config/ e security/** — prioridade de estabilidade. |

### F7 — Liquidez penny-stock no terminal (backlog item)
| Critério | Resposta |
|----------|----------|
| 7 dias? | **SIM** — feature direta para usuário |
| 30 dias? | **SIM** — produto mais atrativo |
| Caos? | Não |
| Estabilidade? | Neutral |
| Checkpoint? | SIM |
| **Decisão** | **GO** — alavanca de entrega imediata. |

### F8 — Limpar .f51/tmp/ stale artifacts (Nemotron)
| Critério | Resposta |
|----------|----------|
| 7 dias? | Não |
| 30 dias? | Não |
| Caos? | Marginalmente |
| Estabilidade? | Não |
| Checkpoint? | SIM |
| **Decisão** | **NO-GO** — perda de tempo. Arquivo morto não incomoda. |

---

## Decisões Consolidadas

| Frente | Decisão | Prioridade |
|--------|---------|------------|
| F7: Penny-stock liquidity | **GO** | P1 — entrega 7d |
| F4: Trading pipeline integration | **GO** | P2 — receita 30d |
| F6: Testes config/security | **GO** | P3 — estabilidade |
| F1: Configs stale | DEFER | P4 |
| F3: Indicadores duplicados | DEFER | P5 |
| F5: Technical neural | DEFER | P6 |
| F8: Limpeza tmp | NO-GO | — |
| F2: GatewayConfig | **DONE** | — |

## Próximo passo executável

**F7: Penny-stock liquidity** — integrar novas frentes de liquidez no terminal. Isso entrega valor direto ao usuário em 7 dias e fortalece o produto para venda em 30 dias.
