---
name: f51-contracts
description: "Protege contratos públicos, schemas e interfaces antes de mudanças funcionais."
compatibility: "SuperEzio v3+"
allowed-tools: "Read, Search, Tests, JSON"
related-skills: [f51-inventory, f51-refactor, f51-tests]
---

# f51-contracts

## Quando usar
- Antes de editar APIs, schemas, assinaturas públicas
- Antes de refatoração com potencial de quebra

## Entregáveis mínimos
- Mapa de contratos afetados
- Risco de quebra e plano de rollback
- Evidência de validação de contrato (testes/checagens)
- Checkpoint atualizado em `.f51/checkpoints/latest.json`

## Regras
- Mudança de contrato sem gate explícito: bloqueada.
- Sem mudanças silenciosas em comportamento público.
