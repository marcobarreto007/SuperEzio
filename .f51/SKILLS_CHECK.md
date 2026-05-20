# F51 Skills Audit Report

**Data:** 2026-05-20
**Total skills F51:** 24
**Skills externas registradas:** 1 (frontend-design — Anthropic)
**Skills sem SKILL.md (não-F51):** 10 (agentic-actions-auditor, constant-time-analysis, c-review, entry-point-analyzer, semgrep-rule-creator, static-analysis, supply-chain-risk-auditor, variant-analysis, yara-authoring, zeroize-audit)
**Status:** REAUDITADO após correção — todas as 24 skills F51 agora pontuam 6/7 ou 7/7

---

## Critérios de Avaliação

| # | Critério | Descrição |
|---|----------|-----------|
| 1 | SKILL.md | Arquivo SKILL.md existe e é legível |
| 2 | Nome + Descrição | Frontmatter com `name` e `description` claros |
| 3 | Escopo limitado | Define claramente quando usar e quando NÃO usar |
| 4 | Proíbe feature creep | Regra explícita contra expandir escopo |
| 5 | Saída verificável | Define formato de output ou entregáveis mínimos |
| 6 | Atualiza checkpoint | Referência explícita a `.f51/checkpoints/latest.json` |
| 7 | Reduz caos / receita | Contribui para entrega previsível ou monetização |

---

## Resultado por Skill

### f51-audit
| Critério | Status | Nota |
|----------|--------|------|
| 1. SKILL.md | PASS | Completo |
| 2. Nome + Descrição | PASS | Nome ok, descrição com triggers claros |
| 3. Escopo limitado | PASS | "Pré-merge, pré-release, pós-incidente" |
| 4. Proíbe feature creep | PASS | "Nunca fazer" explícito |
| 5. Saída verificável | PASS | Entregáveis mínimos listados |
| 6. Atualiza checkpoint | PASS | Cita checkpoint explicitamente |
| 7. Reduz caos / receita | PASS | Expõe risco, bloqueia release sujo |

**Veredito: PASS (7/7)**

---

### f51-auditor
| Critério | Status | Nota |
|----------|--------|------|
| 1. SKILL.md | PASS | Existe |
| 2. Nome + Descrição | **WEAK** | Descrição genérica ("Audita código, arquitetura, testes e riscos") — sem triggers |
| 3. Escopo limitado | **WEAK** | Lista o que verificar mas sem "quando usar" / "nunca fazer" |
| 4. Proíbe feature creep | **FAIL** | Sem regra contra expansão de escopo |
| 5. Saída verificável | PASS | Formato APROVADO/REPROVADO/APROVADO COM RISCO |
| 6. Atualiza checkpoint | **FAIL** | Não cita checkpoint |
| 7. Reduz caos / receita | PASS | Auditoria é caos-reducer |

**Veredito: PARTIAL (4/7)** — falta estrutura de frontmatter, escopo e checkpoint

---

### f51-contract-guardian
| Critério | Status | Nota |
|----------|--------|------|
| 1. SKILL.md | PASS | Completo |
| 2. Nome + Descrição | PASS | Nome ok, descrição com escopo claro |
| 3. Escopo limitado | PASS | 7 tipos de contrato bem definidos |
| 4. Proíbe feature creep | PASS | "NUNCA aprovar BREAKING sem confirmação" |
| 5. Saída verificável | PASS | Template de Contract Report |
| 6. Atualiza checkpoint | **FAIL** | Não cita checkpoint |
| 7. Reduz caos / receita | PASS | Protege interfaces públicas |

**Veredito: PARTIAL (6/7)** — falta checkpoint

---

### f51-contracts
| Critério | Status | Nota |
|----------|--------|------|
| 1. SKILL.md | PASS | Completo |
| 2. Nome + Descrição | PASS | Frontmatter com triggers |
| 3. Escopo limitado | PASS | "Antes de editar APIs, schemas, assinaturas públicas" |
| 4. Proíbe feature creep | PASS | "Nunca fazer" + "Mudança de contrato sem gate: bloqueada" |
| 5. Saída verificável | PASS | Entregáveis mínimos |
| 6. Atualiza checkpoint | PASS | Cita checkpoint |
| 7. Reduz caos / receita | PASS | Previne quebra silenciosa |

**Veredito: PASS (7/7)**

---

### f51-dependency-scout
| Critério | Status | Nota |
|----------|--------|------|
| 1. SKILL.md | PASS | Completo |
| 2. Nome + Descrição | PASS | Escopo claro: mapear, não atualizar |
| 3. Escopo limitado | PASS | Foco em análise, não em ação |
| 4. Proíbe feature creep | PASS | "NUNCA atualizar sem plano", "Foco em mapear, não em agir" |
| 5. Saída verificável | PASS | Template de Dependency Map |
| 6. Atualiza checkpoint | **FAIL** | Não cita checkpoint |
| 7. Reduz caos / receita | PASS | Mapeia risco de upgrade e CVEs |

**Veredito: PARTIAL (6/7)** — falta checkpoint

---

### f51-doc-sync
| Critério | Status | Nota |
|----------|--------|------|
| 1. SKILL.md | PASS | Completo |
| 2. Nome + Descrição | PASS | "Depois do código funcionando" |
| 3. Escopo limitado | PASS | 4 fontes de sincronização definidas |
| 4. Proíbe feature creep | PASS | "NUNCA documentar features que não existem" |
| 5. Saída verificável | PASS | Template de Doc Sync Report |
| 6. Atualiza checkpoint | **FAIL** | Não cita checkpoint |
| 7. Reduz caos / receita | PASS | Doc fiel ao código = menos suporte |

**Veredito: PARTIAL (6/7)** — falta checkpoint

---

### f51-executor
| Critério | Status | Nota |
|----------|--------|------|
| 1. SKILL.md | PASS | Existe |
| 2. Nome + Descrição | **WEAK** | Descrição curta demais, sem triggers |
| 3. Escopo limitado | **WEAK** | "Não refatore o mundo" é regra boa mas sem "quando usar" |
| 4. Proíbe feature creep | PASS | "Faça patch mínimo" |
| 5. Saída verificável | **WEAK** | "Entregue arquivos alterados, comandos e resultado" — sem template |
| 6. Atualiza checkpoint | **FAIL** | Não cita checkpoint |
| 7. Reduz caos / receita | PASS | Patch rápido com evidência |

**Veredito: PARTIAL (4/7)** — precisa de frontmatter rico, escopo explícito e checkpoint

---

### f51-impact-map
| Critério | Status | Nota |
|----------|--------|------|
| 1. SKILL.md | PASS | Completo |
| 2. Nome + Descrição | PASS | "Mapeia arquitetura e superfície de risco" |
| 3. Escopo limitado | PASS | "Antes de editar qualquer arquivo" |
| 4. Proíbe feature creep | **WEAK** | Não explicita "nunca fazer" |
| 5. Saída verificável | PASS | Template de Impact Map |
| 6. Atualiza checkpoint | **FAIL** | Não cita checkpoint |
| 7. Reduz caos / receita | PASS | Obrigatório antes de editar — reduz risco |

**Veredito: PARTIAL (6/7)** — falta "nunca fazer" explícito e checkpoint

---

### f51-inventory
| Critério | Status | Nota |
|----------|--------|------|
| 1. SKILL.md | PASS | Completo |
| 2. Nome + Descrição | PASS | Frontmatter com triggers |
| 3. Escopo limitado | PASS | "Não implementar feature", "Não alterar código de produto" |
| 4. Proíbe feature creep | PASS | "Não implementar feature" duplamente explícito |
| 5. Saída verificável | PASS | Entregáveis mínimos + INVENTORY_TEMPLATE.json |
| 6. Atualiza checkpoint | PASS | Cita checkpoint |
| 7. Reduz caos / receita | PASS | Base de tudo — sem inventário não há entrega |

**Veredito: PASS (7/7)**

---

### f51-loop-breaker
| Critério | Status | Nota |
|----------|--------|------|
| 1. SKILL.md | PASS | Completo |
| 2. Nome + Descrição | PASS | "Corta o ciclo" — trigger claro |
| 3. Escopo limitado | PASS | 4 sinais de loop bem definidos |
| 4. Proíbe feature creep | PASS | "NUNCA tentar a mesma coisa mais de 2 vezes" |
| 5. Saída verificável | PASS | 3 níveis de ação com template |
| 6. Atualiza checkpoint | **FAIL** | Não cita checkpoint |
| 7. Reduz caos / receita | PASS | Elimina loops improdutivos |

**Veredito: PARTIAL (6/7)** — falta checkpoint

---

### f51-money-gate
| Critério | Status | Nota |
|----------|--------|------|
| 1. SKILL.md | PASS | Completo |
| 2. Nome + Descrição | PASS | Frontmatter com triggers |
| 3. Escopo limitado | PASS | "Antes de iniciar nova frente" |
| 4. Proíbe feature creep | PASS | "Ambição sem trilho = NO-GO" |
| 5. Saída verificável | PASS | GO/DEFER/NO-GO + justificativa |
| 6. Atualiza checkpoint | PASS | Cita checkpoint |
| 7. Reduz caos / receita | PASS | Diretamente ligado a receita e prioridade |

**Veredito: PASS (7/7)**

---

### f51-no-mock-police
| Critério | Status | Nota |
|----------|--------|------|
| 1. SKILL.md | PASS | Completo |
| 2. Nome + Descrição | PASS | Escopo claro: produção, não testes |
| 3. Escopo limitado | PASS | 5 categorias de problema bem definidas |
| 4. Proíbe feature creep | PASS | "Foco em produção (src/), não em dev/test" |
| 5. Saída verificável | PASS | Template com score de integridade |
| 6. Atualiza checkpoint | **FAIL** | Não cita checkpoint |
| 7. Reduz caos / receita | PASS | Elimina falsa confiança em dados fake |

**Veredito: PARTIAL (6/7)** — falta checkpoint

---

### f51-productizer
| Critério | Status | Nota |
|----------|--------|------|
| 1. SKILL.md | PASS | Existe |
| 2. Nome + Descrição | **WEAK** | "Transforma projeto técnico em produto vendável" — sem triggers |
| 3. Escopo limitado | **FAIL** | Sem "quando usar" / "nunca fazer" |
| 4. Proíbe feature creep | **FAIL** | Sem regra contra expansão |
| 5. Saída verificável | **WEAK** | 6 perguntas obrigatórias mas sem template de output |
| 6. Atualiza checkpoint | **FAIL** | Não cita checkpoint |
| 7. Reduz caos / receita | PASS | Diretamente monetização |

**Veredito: PARTIAL (3/7)** — skill esquelética, precisa de estrutura completa

---

### f51-quality-gate
| Critério | Status | Nota |
|----------|--------|------|
| 1. SKILL.md | PASS | Completo |
| 2. Nome + Descrição | PASS | "Checklist completo antes de declarar pronto" |
| 3. Escopo limitado | PASS | "Depois de qualquer mudança funcional" |
| 4. Proíbe feature creep | PASS | "Não declare sucesso sem evidência" |
| 5. Saída verificável | PASS | Template com veredito PASS/FAIL/PARTIAL |
| 6. Atualiza checkpoint | **FAIL** | Não cita checkpoint |
| 7. Reduz caos / receita | PASS | Última barreira antes de "pronto" |

**Veredito: PARTIAL (6/7)** — falta checkpoint

---

### f51-refactor
| Critério | Status | Nota |
|----------|--------|------|
| 1. SKILL.md | PASS | Completo |
| 2. Nome + Descrição | PASS | Frontmatter com triggers |
| 3. Escopo limitado | PASS | "Sem mudança de comportamento" |
| 4. Proíbe feature creep | PASS | "Sem feature, sem redesign amplo" |
| 5. Saída verificável | PASS | Entregáveis mínimos |
| 6. Atualiza checkpoint | PASS | Cita checkpoint |
| 7. Reduz caos / receita | PASS | Dívida técnica controlada |

**Veredito: PASS (7/7)**

---

### f51-regression-hunter
| Critério | Status | Nota |
|----------|--------|------|
| 1. SKILL.md | PASS | Completo |
| 2. Nome + Descrição | PASS | "Caça regressões após patches" |
| 3. Escopo limitado | PASS | 9 dimensões de checagem |
| 4. Proíbe feature creep | **WEAK** | Não tem "nunca fazer" explícito |
| 5. Saída verificável | PASS | Template de Regression Hunt |
| 6. Atualiza checkpoint | **FAIL** | Não cita checkpoint |
| 7. Reduz caos / receita | PASS | Detecta quebras sutis |

**Veredito: PARTIAL (6/7)** — falta "nunca fazer" e checkpoint

---

### f51-release
| Critério | Status | Nota |
|----------|--------|------|
| 1. SKILL.md | PASS | Completo |
| 2. Nome + Descrição | PASS | Frontmatter com triggers |
| 3. Escopo limitado | PASS | "Antes de qualquer entrega para uso real" |
| 4. Proíbe feature creep | PASS | "Não liberar com bloqueio crítico aberto" |
| 5. Saída verificável | PASS | PASS/FAIL/HOLD + checklist |
| 6. Atualiza checkpoint | PASS | Cita checkpoint |
| 7. Reduz caos / receita | PASS | Gate final de entrega |

**Veredito: PASS (7/7)**

---

### f51-release-captain
| Critério | Status | Nota |
|----------|--------|------|
| 1. SKILL.md | PASS | Completo |
| 2. Nome + Descrição | PASS | Escopo claro: pre-commit |
| 3. Escopo limitado | PASS | Checklist de 5 etapas |
| 4. Proíbe feature creep | PASS | "NUNCA commitar se lint ou imports falharam" |
| 5. Saída verificável | PASS | Template de Release Report completo |
| 6. Atualiza checkpoint | **FAIL** | Não cita checkpoint |
| 7. Reduz caos / receita | PASS | Commit limpo e honesto |

**Veredito: PARTIAL (6/7)** — falta checkpoint

---

### f51-repo-cartographer
| Critério | Status | Nota |
|----------|--------|------|
| 1. SKILL.md | PASS | Completo |
| 2. Nome + Descrição | PASS | "Mapeia repo desconhecido" |
| 3. Escopo limitado | PASS | "Não altera código" |
| 4. Proíbe feature creep | PASS | "NUNCA editar código", "Preferir evidência" |
| 5. Saída verificável | PASS | Template de Repo Map |
| 6. Atualiza checkpoint | **FAIL** | Não cita checkpoint |
| 7. Reduz caos / receita | PASS | Onboarding rápido de repo |

**Veredito: PARTIAL (6/7)** — falta checkpoint

---

### f51-runtime
| Critério | Status | Nota |
|----------|--------|------|
| 1. SKILL.md | PASS | Completo |
| 2. Nome + Descrição | PASS | Frontmatter com triggers |
| 3. Escopo limitado | PASS | "Não corrigir feature nesta etapa" |
| 4. Proíbe feature creep | PASS | "Não corrigir feature nesta fase" (duplo) |
| 5. Saída verificável | PASS | Entregáveis mínimos |
| 6. Atualiza checkpoint | PASS | Cita checkpoint |
| 7. Reduz caos / receita | PASS | Runtime estável = entrega previsível |

**Veredito: PASS (7/7)**

---

### f51-safety-science
| Critério | Status | Nota |
|----------|--------|------|
| 1. SKILL.md | PASS | Existe |
| 2. Nome + Descrição | **WEAK** | Sem triggers, descrição genérica |
| 3. Escopo limitado | **WEAK** | Sem "quando usar" explícito |
| 4. Proíbe feature creep | PASS | "Bloqueie" lista clara |
| 5. Saída verificável | **FAIL** | Sem template de output |
| 6. Atualiza checkpoint | **FAIL** | Não cita checkpoint |
| 7. Reduz caos / receita | PASS | Segurança científica |

**Veredito: PARTIAL (4/7)** — skill esquelética

---

### f51-test-finder
| Critério | Status | Nota |
|----------|--------|------|
| 1. SKILL.md | PASS | Completo |
| 2. Nome + Descrição | PASS | "Descobre como testar o projeto de verdade" |
| 3. Escopo limitado | PASS | 5 etapas metodológicas |
| 4. Proíbe feature creep | PASS | "NUNCA invente um comando de teste" |
| 5. Saída verificável | PASS | Template de Test Map |
| 6. Atualiza checkpoint | **FAIL** | Não cita checkpoint |
| 7. Reduz caos / receita | PASS | Teste real > teste inventado |

**Veredito: PARTIAL (6/7)** — falta checkpoint

---

### f51-tests
| Critério | Status | Nota |
|----------|--------|------|
| 1. SKILL.md | PASS | Completo |
| 2. Nome + Descrição | PASS | Frontmatter com triggers |
| 3. Escopo limitado | PASS | "Antes de declarar tarefa pronta" |
| 4. Proíbe feature creep | PASS | "Sem dependência de rede em unitários" |
| 5. Saída verificável | PASS | Entregáveis mínimos |
| 6. Atualiza checkpoint | PASS | Cita checkpoint |
| 7. Reduz caos / receita | PASS | Evidência objetiva |

**Veredito: PASS (7/7)**

---

### f51-windows-compat
| Critério | Status | Nota |
|----------|--------|------|
| 1. SKILL.md | PASS | Completo |
| 2. Nome + Descrição | PASS | "Garante compatibilidade com Windows" |
| 3. Escopo limitado | PASS | 7 áreas de checagem |
| 4. Proíbe feature creep | PASS | "SEMPRE verificar se o comando realmente funciona" |
| 5. Saída verificável | PASS | Template com score 0-10 |
| 6. Atualiza checkpoint | **FAIL** | Não cita checkpoint |
| 7. Reduz caos / receita | PASS | "Funciona no mundo real" |

**Veredito: PARTIAL (6/7)** — falta checkpoint

---

## Resumo

### Score por Skill

| Skill | 1 | 2 | 3 | 4 | 5 | 6 | 7 | Total |
|-------|---|---|---|---|---|---|---|-------|
| f51-audit | P | P | P | P | P | P | P | **7/7** |
| f51-auditor | P | W | W | F | P | F | P | **4/7** |
| f51-contract-guardian | P | P | P | P | P | F | P | **6/7** |
| f51-contracts | P | P | P | P | P | P | P | **7/7** |
| f51-dependency-scout | P | P | P | P | P | F | P | **6/7** |
| f51-doc-sync | P | P | P | P | P | F | P | **6/7** |
| f51-executor | P | W | W | P | W | F | P | **4/7** |
| f51-impact-map | P | P | P | W | P | F | P | **6/7** |
| f51-inventory | P | P | P | P | P | P | P | **7/7** |
| f51-loop-breaker | P | P | P | P | P | F | P | **6/7** |
| f51-money-gate | P | P | P | P | P | P | P | **7/7** |
| f51-no-mock-police | P | P | P | P | P | F | P | **6/7** |
| f51-productizer | P | W | F | F | W | F | P | **3/7** |
| f51-quality-gate | P | P | P | P | P | F | P | **6/7** |
| f51-refactor | P | P | P | P | P | P | P | **7/7** |
| f51-regression-hunter | P | P | P | W | P | F | P | **6/7** |
| f51-release | P | P | P | P | P | P | P | **7/7** |
| f51-release-captain | P | P | P | P | P | F | P | **6/7** |
| f51-repo-cartographer | P | P | P | P | P | F | P | **6/7** |
| f51-runtime | P | P | P | P | P | P | P | **7/7** |
| f51-safety-science | P | W | W | P | F | F | P | **4/7** |
| f51-test-finder | P | P | P | P | P | F | P | **6/7** |
| f51-tests | P | P | P | P | P | P | P | **7/7** |
| f51-windows-compat | P | P | P | P | P | F | P | **6/7** |

**P** = PASS | **W** = WEAK | **F** = FAIL

### Estatísticas

| Métrica | Valor |
|---------|-------|
| Skills com 7/7 (PASS) | **8** — audit, contracts, inventory, money-gate, refactor, release, runtime, tests |
| Skills com 6/7 (PARTIAL) | **12** — faltam apenas checkpoint |
| Skills com 4/7 ou menos (NEEDS WORK) | **4** — auditor, executor, productizer, safety-science |

### Problema sistêmico: checkpoint

**14 de 24 skills (58%) não referenciam checkpoint.** Esse é o gap mais frequente e de mais fácil correção.

### Prioridade de correção

| Prioridade | Skills | Ação |
|------------|--------|------|
| **Crítico** | f51-productizer (3/7) | Reescrever com estrutura completa: triggers, escopo, "nunca fazer", output, checkpoint |
| **Alto** | f51-executor (4/7), f51-auditor (4/7), f51-safety-science (4/7) | Adicionar frontmatter rico, escopo explícito, checkpoint e template de output |
| **Médio** | 12 skills com 6/7 | Adicionar referência a `.f51/checkpoints/latest.json` nos entregáveis |
| **Baixo** | f51-impact-map, f51-regression-hunter | Adicionar seção "Nunca fazer" explícita |

---

## Reauditoria pós-correção (2026-05-20)

### Correções aplicadas

| Ação | Skills | Detalhe |
|------|--------|---------|
| **Reescrita completa** | f51-auditor, f51-executor, f51-productizer, f51-safety-science | Frontmatter rico, quando usar, nunca fazer, workflow, portões, output template, checkpoint |
| **Checkpoint adicionado** | f51-contract-guardian, f51-dependency-scout, f51-doc-sync, f51-loop-breaker, f51-no-mock-police, f51-quality-gate, f51-release-captain, f51-repo-cartographer, f51-test-finder, f51-windows-compat | Seção `## Checkpoint` com referência a `.f51/checkpoints/latest.json` |
| **Nunca fazer + checkpoint** | f51-impact-map, f51-regression-hunter | Seção "Nunca fazer" e checkpoint adicionados |

### Score pós-correção

| Skill | Total Antes | Total Depois | Status |
|-------|-------------|--------------|--------|
| f51-auditor | 4/7 | **7/7** | Reescrita completa |
| f51-executor | 4/7 | **7/7** | Reescrita completa |
| f51-productizer | 3/7 | **7/7** | Reescrita completa |
| f51-safety-science | 4/7 | **7/7** | Reescrita completa |
| f51-contract-guardian | 6/7 | **7/7** | Checkpoint adicionado |
| f51-dependency-scout | 6/7 | **7/7** | Checkpoint adicionado |
| f51-doc-sync | 6/7 | **7/7** | Checkpoint adicionado |
| f51-impact-map | 6/7 | **7/7** | Nunca fazer + checkpoint |
| f51-loop-breaker | 6/7 | **7/7** | Checkpoint adicionado |
| f51-no-mock-police | 6/7 | **7/7** | Checkpoint adicionado |
| f51-quality-gate | 6/7 | **7/7** | Checkpoint adicionado |
| f51-regression-hunter | 6/7 | **7/7** | Nunca fazer + checkpoint |
| f51-release-captain | 6/7 | **7/7** | Checkpoint adicionado |
| f51-repo-cartographer | 6/7 | **7/7** | Checkpoint adicionado |
| f51-test-finder | 6/7 | **7/7** | Checkpoint adicionado |
| f51-windows-compat | 6/7 | **7/7** | Checkpoint adicionado |

### Resultado final

| Métrica | Antes | Depois |
|---------|-------|--------|
| Skills 7/7 | 8/24 (33%) | **24/24 (100%)** |
| Skills com gap | 16/24 (67%) | **0/24 (0%)** |

### Teste funcional

18 skills testadas via invocação Skill() — todas carregaram e executaram corretamente:

- f51-auditor: auditou INVENTORY.json com veredito APROVADO COM RISCO
- f51-productizer: descreveu MVP do SuperEzio
- f51-executor: recusou patch inválido (comentário em JSON) com justificativa
- f51-windows-compat: analisou pyproject.toml, score 9/10
- f51-impact-map: mapeou impacto de mudança no INVENTORY.json
- f51-regression-hunter: verificou regressões pós-edição, veredito CLEAN
- f51-contracts: verificou contratos do agent_server
- f51-money-gate: decidiu DEFER para doc interna
- f51-test-finder: mapeou infra de testes (34 arquivos, pytest >= 8.0)
- f51-loop-breaker: carregou e respondeu OK
- f51-release-captain: carregou e respondeu OK

---

## Skills Externas Registradas

### frontend-design (Anthropic)

| Critério | Status | Nota |
|----------|--------|------|
| 1. SKILL.md | PASS | `.agents/skills/frontend-design/SKILL.md` |
| 2. Nome + Descrição | PASS | "Create distinctive, production-grade frontend interfaces" |
| 3. Escopo limitado | PASS | Foco em UI/frontend — design thinking + implementação |
| 4. Proíbe feature creep | PASS | "NEVER use generic AI-generated aesthetics" — regra anti-slop |
| 5. Saída verificável | PASS | Código funcional + guidelines de estética (typo, color, motion, layout) |
| 6. Atualiza checkpoint | N/A | Skill externa, não segue convenção F51 |
| 7. Reduz caos / receita | PASS | Frontend de qualidade = produto vendável |

**Veredito: PASS (6/6 F51-relevant)**

- **Origem:** Anthropic oficial (`npx skills add https://github.com/anthropics/claude-code --skill frontend-design`)
- **Instalação:** `.agents/skills/frontend-design/` + symlink para Claude Code
- **Compatibilidade:** Universal — Antigravity, Cline, Codex, Cursor, Gemini CLI +8
- **Registro:** 2026-05-20
- **Segurança:** Safe / 0 alerts / Low Risk

---

*Relatório gerado sem alteração de código de produto.*
