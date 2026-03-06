---
name: f51-refactor
description: "Executa refatoração mínima, segura e reversível sem adicionar feature."
compatibility: "SuperEzio v3+"
allowed-tools: "Read, Edit, Tests, Diff"
related-skills: [f51-contracts, f51-tests, f51-audit]
---

# f51-refactor

## Quando usar
- Redução de complexidade sem mudança de comportamento
- Eliminação de duplicação com cobertura de teste

## Entregáveis mínimos
- Escopo explícito de refatoração
- Diferença de comportamento: nenhuma (com evidência)
- Testes relevantes passando
- Checkpoint atualizado em `.f51/checkpoints/latest.json`

## Regras
- Sem feature, sem redesign amplo.
- Uma refatoração por vez, com rollback claro.
