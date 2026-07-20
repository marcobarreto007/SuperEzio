---
name: f51-release
description: "Use quando fechar o quality gate final, consolidar evidências e decidir PASS ou FAIL para entrega. Triggers: release, prontidão, quality gate, pre-delivery, final check."
compatibility: "SuperEzio bootstrap layer"
allowed-tools: "Read, Tests, Lint, Diff, Git (read), JSON"
depends-on: [f51-tests, f51-audit, f51-money-gate]
related-skills: [f51-contracts, f51-runtime]
---

# f51-release

## Quando usar

- Antes de qualquer entrega para uso real
- Antes de declarar uma frente pronta para handoff, demo ou operação

## Nunca fazer

- Liberar com bloqueio crítico aberto
- Substituir evidência por sensação de confiança

## Workflow

1. Consolidar inventário da mudança, contratos, runtime, testes e auditoria.
2. Verificar checklist final de release e riscos residuais.
3. Determinar recomendação final: PASS, FAIL ou HOLD.
4. Explicitar o que ficou pendente, bloqueado ou conscientemente aceito.
5. Atualizar checkpoint e orientar o próximo passo mínimo seguro.

## Portões de decisão

- Falha crítica em teste, contrato ou runtime = FAIL.
- Risco alto sem mitigação explícita = HOLD ou FAIL.

## Entregáveis mínimos

- Checklist de release completo
- Evidências de testes/lint
- Riscos residuais documentados
- Recomendação final: PASS/FAIL/HOLD
- Checkpoint atualizado em `.f51/checkpoints/latest.json`

## Regras

- Não liberar com bloqueio crítico aberto.
- Sem "parece ok": somente com evidência.
- Release bom é o que pode ser defendido em auditoria.
