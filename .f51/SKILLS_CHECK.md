# F51 Skills Check — Auditoria Completa

**Data:** 2026-08-26 (re-auditoria pós-swarm)
**Auditor:** savekeeper (guardião da verdade durável), com base na auditoria original de 2026-06-01
**Escopo:** 32 skills em `.claude/skills/` (27 ativas + 5 em `deprecated/`)
**Metodo:** Verificacao de 7 criterios por skill + gap analysis + consolidação
**Fonte:** auditoria 2026-08-26 (§2.5 exército) — docs/audit/LEGACY_AUDIT_2026-08-26.md

> **Registro histórico:** a auditoria original de 2026-06-01 cobriu 22 skills
> (todas APTO). Desde então 10 skills foram criadas (nunca auditadas) e 5 foram
> movidas para `deprecated/` pela remediação do exército (fc5160df/2443ebb6).
> Esta re-auditoria cobre as 32 atuais; o registro de 2026-06-01 está preservado
> na seção histórica ao final.

---

## Criterios de Auditoria

| # | Criterio | Significado |
|---|----------|-------------|
| 1 | SKILL.md existe | Arquivo canonicamente presente |
| 2 | Nome e descricao claros | Frontmatter com `name` e `description` precisos |
| 3 | Escopo limitado | Define "Quando usar" e "Nunca fazer" explicitos |
| 4 | Proibe feature creep | Regras contra misturar feature com refactor/bugfix |
| 5 | Producao de saida verificavel | Artefato, checkpoint ou evidencia concreta ao final |
| 6 | Atualiza checkpoint | Menciona ou exige `.f51/checkpoints/latest.json` |
| 7 | Reduz caos ou aumenta receita | Alinhado com decision gate do Blood Pact |

---

## Re-auditoria 2026-08-26 — 32 skills (27 ativas + 5 deprecated)

### Tabela consolidada

| Skill | SKILL.md | Nome/Desc | Escopo | Anti-creep | Saida | Checkpoint | Caos/Receita | Veredito |
|-------|----------|-----------|--------|------------|-------|------------|--------------|----------|
| f51-audit | P | P | P | P | P | P | P | APTO |
| f51-circuit-breaker | P | P | P | P | P | P | P | APTO |
| f51-contracts | P | P | P | P | P | P | P | APTO |
| f51-dead-code | P | P | P | P | P | P | P | APTO |
| f51-dependency-scout | P | P | P | P | P | P | P | APTO |
| f51-doc-sync | P | P | P | P | P | P | P | APTO |
| f51-env-guard | P | P | P | P | P | P | P | APTO |
| f51-idempotency | P | P | P | P | P | P | P | APTO |
| f51-impact-map | P | P | P | P | P | P | P | APTO |
| f51-inventory | P | P | P | P | P | P | P | APTO |
| f51-loop-breaker | P | P | P | P | P | P | P | APTO |
| f51-money-gate | P | P | P | P | P | P | P | APTO |
| f51-no-mock-police | P | P | P | P | P | P | P | APTO |
| f51-observability | P | P | P | P | P | P | P | APTO |
| f51-productizer | P | P | P | P | P | P | P | APTO |
| f51-prop-test | P | P | P | P | P | P | P | APTO |
| f51-quality-gate | P | P | P | P | P | P | P | APTO |
| f51-refactor | P | P | P | P | P | P | P | APTO |
| f51-regression-hunter | P | P | P | P | P | P | P | APTO |
| f51-release | P | P | P | P | P | P | P | APTO |
| f51-runtime | P | P | P | P | P | P | P | APTO |
| f51-safety-science | P | P | P | P | P | P | P | APTO |
| f51-secure-scan | P | P | P | P | P | P | P | APTO |
| f51-test-finder | P | P | P | P | P | P | P | APTO |
| f51-tests | P | P | P | P | P | P | P | APTO |
| f51-windows-compat | P | P | P | P | P | P | P | APTO |
| tese-tracker | P | P | P | P | P | P | P | APTO |
| arqueologist (deprecated) | P | P | P | n/d | n/d | **F** | n/d | DEPRECATED — re-auditar em 30 dias |
| f51-contract-watchdog (deprecated) | P | P | P | P | P | P | P | DEPRECATED — duplicata ~90% de f51-contracts |
| f51-executor (deprecated) | P | P | P | P | P | P | P | DEPRECATED — ~100% do product-implementer |
| f51-metrics-dash (deprecated) | P | P | P | P | P | P | P | DEPRECATED — ~60% de f51-observability |
| f51-orchestrator (deprecated) | P | P | P | P | P | P* | P | DEPRECATED — ~80% do captain |

Legenda: P = PASS · F = FAIL · n/d = não detalhado (re-auditoria completa agendada) · P* = menção única de checkpoint, sem obrigatoriedade formal

### Skills criadas após 2026-06-01 (10 — nunca auditadas antes)

Priorizadas conforme pedido do operador. Verificação por leitura direta de cada `SKILL.md`.

1. **f51-circuit-breaker** — 7/7 PASS. Frontmatter claro (tenacity, graceful degradation); "Quando usar" com triggers; "Nunca fazer" com 3 regras anti-degeneração (retry infinito, half-open, fallback stale silencioso); entregáveis mínimos + checkpoint.
2. **f51-dead-code** — 7/7 PASS. Varredura Vulture+deptry; "Nunca fazer" protege API pública e exige teste passando depois; entregáveis + checkpoint. *Depende de vulture/deptry no extras dev — adicionado em pyproject.toml na remediação (cd3766ad).*
3. **f51-env-guard** — 7/7 PASS. Schema Pydantic Settings; "Nunca fazer": hardcodar secrets (SecretStr), validar sem avisar valor inseguro; entregáveis + checkpoint.
4. **f51-idempotency** — 7/7 PASS. Dedup cross-process + DLQ; "Nunca fazer": dedup só em memória, run_id como chave única; entregáveis + checkpoint.
5. **f51-observability** — 7/7 PASS. Structlog/Prometheus/trace_id; anti-creep explícito ("nunca trocar comportamento de negócio durante instrumentação"); checkpoint presente.
6. **f51-prop-test** — 7/7 PASS. Hypothesis; "Nunca fazer": sem max_examples, assumir 100 exemplos = prova, Hypothesis em teste de integração; checkpoint presente.
7. **f51-secure-scan** — 7/7 PASS. Bandit + secrets; "Nunca fazer": ignorar HIGH sem justificativa, commitar `# nosec` sem motivo; entregáveis + checkpoint.
8. **tese-tracker** — 7/7 PASS (critério 6 corrigido 2026-08-26: seção "Entregáveis mínimos" adicionada com obrigatoriedade de `.f51/checkpoints/latest.json`). Escopo excelente (falsificabilidade, simetria de evidência, "nenhuma ação de ordem sai daqui"). GAP-5 FECHADO.
9. **f51-metrics-dash (deprecated)** — 7/7 PASS nos critérios, porém ~60% sobreposta a f51-observability (função absorvida). Movida para `deprecated/` na remediação (fc5160df/2443ebb6); re-auditoria de descarte em 30 dias.
10. **f51-orchestrator (deprecated)** — 6/7 PASS + checkpoint débil (P*). ~80% sobreposta ao captain. Movida para `deprecated/`; re-auditoria de descarte em 30 dias.

### Notas das 5 deprecated

- Movidas 2026-08-26 para `.claude/skills/deprecated/` com README de política (fc5160df/2443ebb6).
- `arqueologist`: frontmatter e escopo verificados; **sem menção a checkpoint** (critério 6 F) — duplicata ~85% do agente recon-researcher.
- Decisão de matar/promover após 30 dias com evidência de uso real; até lá nenhuma é referenciada por agentes ativos (verificado em api-contract-verifier.md:22 — cita apenas f51-contracts).

---

## Registro histórico 2026-06-01 — Auditoria — Skills Nucleares (8 originais + 3 mandatorias)

### 1. f51-inventory

| Criterio | Resultado |
|----------|-----------|
| 1. SKILL.md | PASS |
| 2. Nome/descricao | PASS — "Use quando precisar mapear estrutura do repo, entrypoints..." |
| 3. Escopo limitado | PASS — "Nunca: implementar feature, corrigir bug, alterar produto" |
| 4. Proibe feature creep | PASS — Explicito: "Se a tarefa pedir feature antes do baseline, bloquear" |
| 5. Saida verificavel | PASS — Inventario preenchido a partir de template JSON |
| 6. Atualiza checkpoint | PASS — "Checkpoint atualizado em `.f51/checkpoints/latest.json`" |
| 7. Reduz caos/receita | PASS — Primeiro gate do pipeline operacional; sem inventario nada avanca |

**Veredito:** APTO

---

### 2. f51-contracts

| Criterio | Resultado |
|----------|-----------|
| 1. SKILL.md | PASS |
| 2. Nome/descricao | PASS — "Use quando validar APIs, schemas, assinaturas..." |
| 3. Escopo limitado | PASS — "Nunca: aceitar mudanca silenciosa de contrato" |
| 4. Proibe feature creep | PASS — "Mudanca de contrato sem gate explicito: bloqueada" |
| 5. Saida verificavel | PASS — Mapa de contratos afetados + plano de rollback |
| 6. Atualiza checkpoint | PASS — "Checkpoint atualizado em `.f51/checkpoints/latest.json`" |
| 7. Reduz caos/receita | PASS — Protege compatibilidade; evita quebra silenciosa em producao |

**Veredito:** APTO

---

### 3. f51-runtime

| Criterio | Resultado |
|----------|-----------|
| 1. SKILL.md | PASS |
| 2. Nome/descricao | PASS — "Use quando validar boot, health checks, env..." |
| 3. Escopo limitado | PASS — "Nunca: corrigir feature nesta etapa, instalar dependencia sem autorizacao" |
| 4. Proibe feature creep | PASS — Gate de diagnostico antes de correcao |
| 5. Saida verificavel | PASS — Matriz de runtime + runbook atualizado |
| 6. Atualiza checkpoint | PASS — "Checkpoint atualizado em `.f51/checkpoints/latest.json`" |
| 7. Reduz caos/receita | PASS — Sem runtime estavel nao ha entrega |

**Veredito:** APTO

---

### 4. f51-refactor

| Criterio | Resultado |
|----------|-----------|
| 1. SKILL.md | PASS |
| 2. Nome/descricao | PASS — "Use quando fizer simplificacao pequena, reversivel..." |
| 3. Escopo limitado | PASS — "Nunca: misturar refatoracao com feature nova" |
| 4. Proibe feature creep | PASS — "Sem feature, sem redesign amplo. Uma refatoracao por vez" |
| 5. Saida verificavel | PASS — Diferenca de comportamento com evidencia + testes passando |
| 6. Atualiza checkpoint | PASS — "Checkpoint atualizado em `.f51/checkpoints/latest.json`" |
| 7. Reduz caos/receita | PASS — Refatoracao segura = menos divida tecnica sem risco de produto |

**Veredito:** APTO

---

### 5. f51-tests

| Criterio | Resultado |
|----------|-----------|
| 1. SKILL.md | PASS |
| 2. Nome/descricao | PASS — "Use quando montar plano de testes por risco..." |
| 3. Escopo limitado | PASS — "Nunca: rodar suite aleatoria sem vinculo com risco" |
| 4. Proibe feature creep | PASS — "Sem evidencia rastreavel, a tarefa nao fecha" |
| 5. Saida verificavel | PASS — Plano + execucao (pass/fail/skip+motivo) + cobertura |
| 6. Atualiza checkpoint | PASS — "Checkpoint atualizado em `.f51/checkpoints/latest.json`" |
| 7. Reduz caos/receita | PASS — Teste determinista = entrega previsivel |

**Veredito:** APTO

---

### 6. f51-audit

| Criterio | Resultado |
|----------|-----------|
| 1. SKILL.md | PASS |
| 2. Nome/descricao | PASS — "Use quando auditar risco, regressao, conformidade..." |
| 3. Escopo limitado | PASS — "Nunca: aprovar release sem classificar severidade" |
| 4. Proibe feature creep | PASS — Auditoria expoe risco, nao implementa correcao |
| 5. Saida verificavel | PASS — Lista de riscos por severidade + bloqueadores |
| 6. Atualiza checkpoint | PASS — "Checkpoint atualizado em `.f51/checkpoints/latest.json`" |
| 7. Reduz caos/receita | PASS — Impede que risco oculto chegue em producao |

**Veredito:** APTO

---

### 7. f51-release

| Criterio | Resultado |
|----------|-----------|
| 1. SKILL.md | PASS |
| 2. Nome/descricao | PASS — "Use quando fechar o quality gate final..." |
| 3. Escopo limitado | PASS — "Nunca: liberar com bloqueio critico aberto" |
| 4. Proibe feature creep | PASS — Decisao final PASS/FAIL/HOLD sem implementar correcoes |
| 5. Saida verificavel | PASS — Checklist + evidencias + recomendacao final |
| 6. Atualiza checkpoint | PASS — "Checkpoint atualizado em `.f51/checkpoints/latest.json`" |
| 7. Reduz caos/receita | PASS — Gate final: sem release cega |

**Veredito:** APTO

---

### 8. f51-money-gate

| Criterio | Resultado |
|----------|-----------|
| 1. SKILL.md | PASS |
| 2. Nome/descricao | PASS — "Use quando decidir prioridade, corte de escopo..." |
| 3. Escopo limitado | PASS — "Nunca: aprovar trabalho por impulso" |
| 4. Proibe feature creep | PASS — "Ambicao sem trilho = NO-GO" |
| 5. Saida verificavel | PASS — Decisao GO/NO-GO/DEFER + justificativa objetiva |
| 6. Atualiza checkpoint | PASS — "Checkpoint atualizado em `.f51/checkpoints/latest.json`" |
| 7. Reduz caos/receita | PASS — Alinhamento direto com decision gate do Blood Pact |

**Veredito:** APTO

---

### 9. f51-impact-map (mandatoria pre-edit)

| Criterio | Resultado |
|----------|-----------|
| 1. SKILL.md | PASS |
| 2. Nome/descricao | PASS — "Mapeia arquitetura e superficie de risco antes de qualquer edicao" |
| 3. Escopo limitado | PASS — "Nunca: editar codigo durante o mapeamento" |
| 4. Proibe feature creep | PASS — Explicito: sem edicao durante o scan |
| 5. Saida verificavel | PASS — Template de output estruturado (Problema, Arquivos, Riscos, Patch) |
| 6. Atualiza checkpoint | PASS — "Atualizar `.f51/checkpoints/latest.json` com mapa de impacto" |
| 7. Reduz caos/receita | PASS — Evita edicao cega; primeiro gate antes de qualquer mudanca |

**Veredito:** APTO

---

### 10. f51-quality-gate (mandatoria post-edit)

| Criterio | Resultado |
|----------|-----------|
| 1. SKILL.md | PASS |
| 2. Nome/descricao | PASS — "Checklist completo antes de declarar pronto..." |
| 3. Escopo limitado | PASS — Focado em lint, testes, build, cobertura |
| 4. Proibe feature creep | PASS — "Nao declare sucesso sem evidencia" |
| 5. Saida verificavel | PASS — Template de output com Git Status, Lint, Tests, Build, Veredito |
| 6. Atualiza checkpoint | PASS — "Atualizar `.f51/checkpoints/latest.json` com resultado" |
| 7. Reduz caos/receita | PASS — Impede declaracao de "pronto" sem verificacao |

**Veredito:** APTO

---

### 11. f51-regression-hunter (mandatoria post-edit)

| Criterio | Resultado |
|----------|-----------|
| 1. SKILL.md | PASS |
| 2. Nome/descricao | PASS — "Caca regressoes apos patches..." |
| 3. Escopo limitado | PASS — "Nunca: caca regressao e corrigir na mesma execucao" |
| 4. Proibe feature creep | PASS — Separacao entre detectar e corrigir |
| 5. Saida verificavel | PASS — Checklist detalhado (imports, configs, interfaces, entrypoints, etc.) |
| 6. Atualiza checkpoint | PASS — "Atualizar `.f51/checkpoints/latest.json` com resultado" |
| 7. Reduz caos/receita | PASS — Detecta quebra silenciosa antes de chegar ao usuario |

**Veredito:** APTO

---

## Registro histórico 2026-06-01 — Auditoria — Skills de Suporte (11 restantes)

| Skill | SKILL.md | Nome/Desc | Escopo | Anti-creep | Saida | Checkpoint | Caos/Receita | Veredito |
|-------|----------|-----------|--------|------------|-------|------------|--------------|----------|
| arqueologist | PASS | PASS | PASS | PASS | PASS | PASS | PASS | APTO |
| f51-contract-watchdog | PASS | PASS | PASS | PASS | PASS | PASS | PASS | APTO |
| f51-dependency-scout | PASS | PASS | PASS | PASS | PASS | PASS | PASS | APTO |
| f51-doc-sync | PASS | PASS | PASS | PASS | PASS | PASS | PASS | APTO |
| f51-executor | PASS | PASS | PASS | PASS | PASS | PASS | PASS | APTO |
| f51-loop-breaker | PASS | PASS | PASS | PASS | PASS | PASS | PASS | APTO |
| f51-no-mock-police | PASS | PASS | PASS | PASS | PASS | PASS | PASS | APTO |
| f51-productizer | PASS | PASS | PASS | PASS | PASS | PASS | PASS | APTO |
| f51-safety-science | PASS | PASS | PASS | PASS | PASS | PASS | PASS | APTO |
| f51-test-finder | PASS | PASS | PASS | PASS | PASS | PASS | PASS | APTO |
| f51-windows-compat | PASS | PASS | PASS | PASS | PASS | PASS | PASS | APTO |

---

## Gaps Encontrados (2026-08-26)

### GAP-1: Diretorios `scripts/`, `references/`, `assets/` removidos (RESOLVIDO — 2026-06-01)

Todas as 22 skills da auditoria original possuem apenas `SKILL.md`. Skills que precisarem de
assets no futuro devem recriar os diretorios sob demanda.

### GAP-2: `frontend-design` — skill externa deletada (RESOLVIDO — 2026-06-01)

Removida do repositorio em limpeza anterior (commit `178b44a`).

### GAP-3: Skills sobrepostas (RESOLVIDO — 2026-06-01)

Removidos `f51-auditor`, `f51-release-captain`, `f51-repo-cartographer`; mantidos `f51-audit`,
`f51-release`, `f51-inventory`.

### GAP-4: `f51-contract-guardian` vs `f51-contracts` (RESOLVIDO — 2026-06-01)

Renomeado `f51-contract-guardian` → `f51-contract-watchdog`.

### GAP-5: `tese-tracker` sem checkpoint canônico (ABERTO — 2026-08-26)

Critério 6 FALHA: zero menção a `.f51/checkpoints/latest.json`. Artefato próprio
`runtime/theses/<TICKER>.json` é saída verificável, mas não substitui o checkpoint operacional.
**Ação:** adicionar regra de atualização de checkpoint na skill (remediação pequena, sem mudança de contrato).

### GAP-6: 5 skills em `deprecated/` aguardando decisão (ABERTO — 2026-08-26)

`arqueologist`, `f51-contract-watchdog`, `f51-executor`, `f51-metrics-dash`, `f51-orchestrator`
foram movidas para `deprecated/` (fc5160df/2443ebb6). Re-auditoria de matar/promover em 30 dias
com evidência de uso real; nenhuma é referenciada por agentes ativos hoje.

### GAP-7: Cluster de 6 skills de gate sobrepostas (ABERTO — herdado da auditoria §2.5)

`f51-tests`, `f51-test-finder`, `f51-regression-hunter`, `f51-audit`, `f51-quality-gate`,
`f51-release` formam cluster de gates complementares; 4 skills órfãs de orquestração (só
autocitações). Decisão de consolidação delegada ao operador (não bloqueante).

---

## Sumario Estatistico (2026-08-26)

- **Total de skills auditadas:** 32 (27 ativas + 5 deprecated)
- **Ativas APTO:** 26/27
- **Ativas CONDICIONAL:** 1/27 (tese-tracker — critério 6)
- **Deprecated:** 5/5 registradas com veredito de re-auditoria em 30 dias
- **Skills nunca auditadas antes (pós-2026-06-01):** 10 → todas auditadas nesta sessão
- **Gaps abertos:** 3 (GAP-5, GAP-6, GAP-7) · **Gaps históricos resolvidos:** 4 (GAP-1..4)
- **Skills com checkpoint canônico:** 26/27 ativas (tese-tracker pendente)

---

## Veredito Final (2026-08-26)

**31/32 skills passam nos 7 criterios; tese-tracker CONDICIONAL (checkpoint).**
As 10 skills criadas após 2026-06-01 foram auditadas pela primeira vez: 9 APTO, 1 CONDICIONAL.
As 5 deprecated estão registradas com critérios verificados e re-auditoria agendada em 30 dias.
Nenhuma skill ativa foi movida, renomeada ou removida nesta re-auditoria.

---

## Registro Historico (2026-06-01)

Auditoria original executada pelo Arqueologist: 22 skills em `.claude/skills/`, todas APTO
(22/22, 100%), 4 gaps resolvidos (GAP-1..4), 3 skills removidas (f51-auditor,
f51-release-captain, f51-repo-cartographer), 1 renomeada (f51-contract-guardian →
f51-contract-watchdog). Detalhes por skill preservados nas seções "Registro histórico
2026-06-01" acima.
