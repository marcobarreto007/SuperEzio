---
name: f51-money-gate
description: "Avalia se a tarefa aumenta entrega em 7 dias e receita em 30 dias antes de execução."
compatibility: "SuperEzio v3+"
allowed-tools: "Read, Plan, Report"
related-skills: [f51-inventory, f51-audit, f51-release]
---

# f51-money-gate

## Quando usar
- Antes de iniciar nova frente
- Em decisões de prioridade e corte de escopo

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
