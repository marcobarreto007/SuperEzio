---
name: f51-auditor
description: "Audita código, arquitetura, testes e riscos operacionais antes de handoff ou release. Triggers: auditoria, audit, revisar qualidade, check de saúde, código morto, gambiarra, risco de segurança."
compatibility: "SuperEzio bootstrap layer"
allowed-tools: "Read, Grep, Glob, Bash (read-only), JSON"
depends-on: [f51-inventory]
related-skills: [f51-audit, f51-contracts, f51-quality-gate]
---

# f51-auditor

## Quando usar

- Antes de handoff de módulo ou frente
- Quando o operador pede revisão de qualidade
- Antes de refatoração ou release
- Quando há suspeita de teste falso, código morto ou risco oculto

## Nunca fazer

- Aprovar sem evidência objetiva
- Auditar e corrigir na mesma execução — auditar é ler, não editar
- Inventar riscos sem apontar arquivo e linha
- Ignorar risco só porque "deve funcionar"

## Workflow

1. Identificar o escopo da auditoria: módulo, frente ou arquivo específico.
2. Inspecionar código buscando: teste falso, código morto, nome ruim, gambiarra, risco de segurança, risco comercial e regressão.
3. Classificar cada achado por severidade (CRÍTICO / MÉDIO / LEVE).
4. Emitir veredito geral: APROVADO / REPROVADO / APROVADO COM RISCO.
5. Atualizar checkpoint com parecer e riscos encontrados.

## Portões de decisão

- Achado CRÍTICO sem mitigação = REPROVADO.
- Mais de 3 achados MÉDIO sem classificação de impacto = APROVADO COM RISCO com ressalva.

## Entregáveis mínimos

- Lista de achados por severidade com arquivo e linha
- Veredito: APROVADO / REPROVADO / APROVADO COM RISCO
- Riscos pendentes e mitigação sugerida
- Checkpoint atualizado em `.f51/checkpoints/latest.json`

## Regras

- Auditar é ler, não editar.
- Sem evidência, sem aprovação.
- Achado sem arquivo/linha é hipótese, não fato.
