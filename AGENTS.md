# AGENTS — F51 Operational Orchestration

Este arquivo define como **Codex** e agentes compatíveis devem operar neste repositório.

## Objetivo

Executar tarefas com previsibilidade, checkpoints obrigatórios e foco em entrega real.

## Mapa de papéis

- **Orchestrator**: define escopo, sequência e gate de execução.
- **Inventory Agent**: mapeia estrutura, entrypoints, dependências, comandos.
- **Contracts Agent**: protege contratos públicos e valida impactos.
- **Runtime Agent**: valida boot, health, logs e execução local.
- **Refactor Agent**: só simplificação segura, sem feature.
- **Tests Agent**: cria/roda matriz de testes e evidências.
- **Audit Agent**: risco, regressão e conformidade operacional.
- **Release Agent**: quality gate final e prontidão de entrega.
- **Money Gate Agent**: avalia impacto em entrega (7d) e receita (30d).

## Regras de execução

1. Sem feature antes de inventário, contratos, runtime e testes.
2. Não tocar código de produto em tarefas de bootstrap operacional.
3. Executar em passos pequenos e checkpoint por etapa.
4. Declarar explicitamente bloqueios e dependências externas.
5. Toda recomendação deve apontar próximo passo executável.

## Regras de checkpoint

Todo agente, ao finalizar seu passo, **deve atualizar**:
- `.f51/checkpoints/latest.json`

Opcionalmente atualizar, conforme escopo:
- `.f51/TASK_BOARD.md`
- `.f51/RISK_REGISTER.md`

Campos mínimos esperados no checkpoint:
- `date_local`
- `session`
- `status`
- `what_was_done`
- `evidence`
- `risks`
- `next_step`

## Regras de relatório

Cada agente deve reportar:
- O que foi alterado
- Evidências de validação
- Riscos encontrados
- Itens não executados e motivo
- Próxima tarefa recomendada

## Regra mandatória

**Todo agente deve atualizar `.f51/checkpoints/latest.json` antes de encerrar sua execução.**
