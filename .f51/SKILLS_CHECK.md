# F51 Skills Check — Auditoria Completa

**Data:** 2026-06-01 (atualizado)
**Auditor:** Arqueologist (consolidação pós-escavação)
**Escopo:** 22 skills em `.claude/skills/`
**Metodo:** Verificacao de 7 criterios por skill + gap analysis + consolidação

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

## Auditoria — Skills Nucleares (8 originais + 3 mandatorias)

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

## Auditoria — Skills de Suporte (11 restantes)

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

## Gaps Encontrados

### GAP-1: Diretorios `scripts/`, `references/`, `assets/` removidos (RESOLVIDO)

**Todas as 22 skills** agora possuem apenas `SKILL.md`. Diretorios `assets/`, `references/`, `scripts/`
foram removidos pois estavam vazios (apenas `.gitkeep`). Skills que precisarem de assets no futuro
devem recriar os diretorios sob demanda.

### GAP-2: `frontend-design` — skill externa deletada (RESOLVIDO)

`frontend-design` foi removida do repositorio em limpeza anterior (commit `178b44a`).

### GAP-3: Skills sobrepostas (RESOLVIDO — 2026-06-01)

- ~~`f51-audit` vs `f51-auditor`~~ → **Removido:** `f51-auditor`. Mantido: `f51-audit`.
- ~~`f51-release` vs `f51-release-captain`~~ → **Removido:** `f51-release-captain`. Mantido: `f51-release`.
- ~~`f51-repo-cartographer` vs `f51-inventory`~~ → **Removido:** `f51-repo-cartographer`. Mantido: `f51-inventory`.

### GAP-4: `f51-contract-guardian` vs `f51-contracts` (RESOLVIDO — 2026-06-01)

Renomeado `f51-contract-guardian` → `f51-contract-watchdog` para clarificar que é um watchdog ativo,
não uma duplicata de `f51-contracts`. Ambas mantidas com propósitos distintos.

---

## Sumario Estatistico

- **Total de skills:** 22 (3 depreciadas, 1 renomeada)
- **APTO:** 22/22 (100%)
- **Gaps encontrados:** 4 → todos RESOLVIDOS
- **Skills com diretorios padrao:** 0/22 (removidos — estrutura limpa, sem skeletons)
- **Skills com saida verificavel:** 22/22 (100%)
- **Skills com checkpoint:** 22/22 (100%)
- **Skills alinhadas ao Blood Pact:** 22/22 (100%)

---

## Veredito Final

**Todas as 22 skills passam nos 7 criterios de auditoria.**
Consolidacao executada em 2026-06-01: 3 skills removidas (f51-auditor, f51-release-captain, f51-repo-cartographer),
1 renomeada (f51-contract-guardian → f51-contract-watchdog).
Diretorios vazios assets/references/scripts removidos de todas as skills.
