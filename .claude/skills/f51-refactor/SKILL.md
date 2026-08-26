---
name: f51-refactor
description: "Use quando fizer simplificação pequena, reversível e sem mudança de comportamento. Triggers: refactor, simplificar, duplicação, cleanup seguro, dívida técnica controlada."
compatibility: "SuperEzio bootstrap layer"
allowed-tools: "Read, Edit, Tests, Diff"
depends-on: [f51-contracts, f51-tests]
related-skills: [f51-runtime]
---

# f51-refactor

## Quando usar

- Redução de complexidade sem mudança de comportamento
- Eliminação de duplicação com cobertura de teste
- Ajuste estrutural mínimo para aumentar legibilidade ou manutenção

## Nunca fazer

- Misturar refatoração com feature nova
- Abrir escopo amplo sem rollback claro
- Refatorar sem contrato validado e teste suficiente

## Workflow

1. Congelar o escopo: o que entra e o que fica fora.
2. Confirmar contratos relevantes e testes mínimos antes da mudança.
3. Aplicar a menor alteração reversível possível.
4. Rodar validações necessárias e comparar comportamento antes/depois.
5. Atualizar checkpoint com evidência de não regressão.

## Portões de decisão

- Sem teste ou validação mínima, refatoração deve ser adiada ou encolhida.
- Se surgir mudança de comportamento, sair do fluxo de refatoração e reclassificar a tarefa.

## Entregáveis mínimos

- Escopo explícito de refatoração
- Diferença de comportamento: nenhuma (com evidência)
- Testes relevantes passando
- Checkpoint atualizado em `.f51/checkpoints/latest.json`

## Regras

- Sem feature, sem redesign amplo.
- Uma refatoração por vez, com rollback claro.
- Refatoração segura é cirurgia, não reforma.
