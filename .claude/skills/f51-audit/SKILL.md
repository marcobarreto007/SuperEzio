---
name: f51-audit
description: "Use quando auditar risco, regressão, conformidade operacional e bloqueios antes de release ou handoff. Triggers: audit, auditoria, regressão, conformidade, blocker, pre-release."
compatibility: "SuperEzio bootstrap layer"
allowed-tools: "Read, Diff, Tests, Logs, JSON"
depends-on: [f51-contracts, f51-runtime, f51-tests]
related-skills: [f51-release, f51-money-gate]
---

# f51-audit

## Quando usar

- Pré-merge, pré-release, pós-incidente
- Antes de handoff para outro agente ou operador

## Nunca fazer

- Aprovar release sem classificar severidade
- Esconder risco em linguagem vaga

## Workflow

1. Consolidar o que mudou, o que foi testado e o que não foi validado.
2. Caçar regressões, riscos operacionais e desvios de regra.
3. Classificar achados por severidade e impacto.
4. Separar bloqueadores de riscos aceitos conscientemente.
5. Atualizar checkpoint com parecer objetivo.

## Portões de decisão

- Sem evidência, o achado vira hipótese e deve ser rotulado como tal.
- Bloqueador crítico aberto impede aprovação final.

## Entregáveis mínimos

- Lista de riscos por severidade
- Regressões potenciais e mitigação
- Itens bloqueadores de release
- Checkpoint atualizado em `.f51/checkpoints/latest.json`

## Regras

- Sem evidência, sem aprovação.
- Reporte objetivo, sem linguagem vaga.
- Auditoria serve para expor risco, não para maquiar estado.
