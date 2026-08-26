name: f51-tests
description: "Use quando montar plano de testes por risco, executar testes determinísticos e registrar evidência objetiva. Triggers: testes, test plan, smoke, regressão, cobertura de escopo, validação final."
compatibility: "SuperEzio bootstrap layer"
allowed-tools: "Read, Terminal, Test Runner, JSON"
depends-on: [f51-contracts, f51-runtime]
related-skills: [f51-audit, f51-release]
---

# f51-tests

## Quando usar

- Antes de declarar tarefa pronta
- Após refatoração ou ajuste de contrato
- Quando a mudança exigir evidência objetiva de não regressão

## Nunca fazer

- Rodar suíte aleatória sem vínculo com risco
- Aceitar teste flaky como validação forte
- Depender de rede externa em unitários

## Workflow

1. Mapear o risco e definir o menor conjunto de testes que valida a mudança.
2. Separar smoke, contrato, integração e regressão quando fizer sentido.
3. Executar e registrar resultado como pass/fail/skip com motivo.
4. Destacar lacunas de cobertura relevantes ao escopo alterado.
5. Atualizar checkpoint com evidência e próximos passos.

## Portões de decisão

- Sem vínculo entre risco e teste, o plano está incompleto.
- Skip sem motivo explícito não vale como evidência.

## Entregáveis mínimos

- Plano de testes por risco
- Execução com resultado (pass/fail/skip + motivo)
- Registro de cobertura de escopo alterado
- Checkpoint atualizado em `.f51/checkpoints/latest.json`

## Regras

- Teste deve ser determinístico.
- Sem dependência de rede em unitários.
- Sem evidência rastreável, a tarefa não fecha.
