---
name: f51-audit
description: "Audita risco, regressão e conformidade operacional antes de release."
compatibility: "SuperEzio v3+"
allowed-tools: "Read, Diff, Tests, Logs"
related-skills: [f51-contracts, f51-runtime, f51-tests, f51-release]
---

# f51-audit

## Quando usar
- Pré-merge, pré-release, pós-incidente

## Entregáveis mínimos
- Lista de riscos por severidade
- Regressões potenciais e mitigação
- Itens bloqueadores de release
- Checkpoint atualizado em `.f51/checkpoints/latest.json`

## Regras
- Sem evidência, sem aprovação.
- Reporte objetivo, sem linguagem vaga.
