---
name: f51-tests
description: "Define e executa política de testes determinísticos com evidência objetiva."
compatibility: "SuperEzio v3+"
allowed-tools: "Read, Terminal, Test Runner"
related-skills: [f51-contracts, f51-runtime, f51-audit]
---

# f51-tests

## Quando usar
- Antes de declarar tarefa pronta
- Após refatoração ou ajuste de contrato

## Entregáveis mínimos
- Plano de testes por risco
- Execução com resultado (pass/fail/skip + motivo)
- Registro de cobertura de escopo alterado
- Checkpoint atualizado em `.f51/checkpoints/latest.json`

## Regras
- Teste deve ser determinístico.
- Sem dependência de rede em unitários.
