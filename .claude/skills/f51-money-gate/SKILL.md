---
name: f51-money-gate
description: "Use quando decidir prioridade, corte de escopo e GO/DEFER/NO-GO com base em entrega em 7 dias, receita em 30 dias e redução de caos operacional. Triggers: money gate, prioridade, ROI, go no-go, corte de escopo."
compatibility: "SuperEzio bootstrap layer"
allowed-tools: "Read, Plan, Report, JSON"
depends-on: []
related-skills: [f51-inventory, f51-audit, f51-release]
---

# f51-money-gate

## Quando usar

- Antes de iniciar nova frente
- Em decisões de prioridade e corte de escopo
- Quando houver disputa entre trabalho operacional, feature e dívida técnica

## Nunca fazer

- Aprovar trabalho por impulso
- Abrir frente sem checkpoint ativo

## Workflow

1. Definir claramente a frente ou tarefa candidata.
2. Avaliar impacto em entrega de 7 dias, receita de 30 dias, caos operacional e proteção financeira/familiar.
3. Verificar se há checkpoint ativo e próximo passo mínimo seguro.
4. Decidir GO, DEFER ou NO-GO com justificativa objetiva.
5. Registrar decisão em `.f51/MONEY_GATE.md` ou artefato derivado e atualizar checkpoint.

## Portões de decisão

- Sem checkpoint ativo: bloqueado.
- Sem próxima ação mínima segura: DEFER ou NO-GO.

## Perguntas obrigatórias
1. Ajuda entrega em 7 dias?
2. Ajuda receita em 30 dias?
3. Reduz caos operacional?
4. Protege estabilidade familiar/financeira?
5. Possui checkpoint ativo?

## Entregáveis mínimos

- Decisão: GO / NO-GO / DEFER
- Justificativa objetiva
- Próxima ação de menor risco
- Checkpoint atualizado em `.f51/checkpoints/latest.json`

## Regras

- Ambição sem trilho = NO-GO.
- Sem checkpoint = bloqueado.
- Prioridade sem critério explícito vira caos operacional.
