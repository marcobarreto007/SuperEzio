---
name: f51-release
description: "Executa quality gate final e valida prontidão de entrega com checklist fechado."
compatibility: "SuperEzio v3+"
allowed-tools: "Read, Tests, Lint, Git (read)"
related-skills: [f51-tests, f51-audit, f51-money-gate]
---

# f51-release

## Quando usar
- Antes de qualquer entrega para uso real

## Entregáveis mínimos
- Checklist de release completo
- Evidências de testes/lint
- Riscos residuais documentados
- Recomendação final: PASS/FAIL
- Checkpoint atualizado em `.f51/checkpoints/latest.json`

## Regras
- Não liberar com bloqueio crítico aberto.
- Sem "parece ok": somente com evidência.
