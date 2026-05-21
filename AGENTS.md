# AGENTS — F51 Operational Orchestration

Este arquivo define como **Codex** e agentes compatíveis devem operar neste repositório.

## REGRA CRITICA: GITHUB BLOQUEADO

Fonte mandataria: `.f51/GITHUB_POLICY.json`

Este projeto esta em modo **DISK ONLY**.

Regra clara:
- NUNCA usar GitHub neste projeto.
- NUNCA executar `git push`, `git pull`, `git fetch` ou `gh`.
- NUNCA usar GitHub Actions, pull requests, GitHub API, conector GitHub ou MCP GitHub.
- Commits locais sao permitidos quando Marco pedir para salvar, mas sem push.
- Se uma tarefa exigir GitHub, parar e reportar bloqueio.

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
2. Não tocar código de produto em tarefas de bootstrap operacional, especialmente em `apps/`, `src/`, `packages/`, `core/` e `pipelines/`.
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

## Política F51 de MCPs

MCP permitido somente se cumprir pelo menos uma função:
1. Reduzir erro operacional
2. Testar produto real
3. Auditar entrega
4. Acessar documentação necessária
5. Preparar venda/demo

Proibido:
- Instalar MCP por curiosidade
- Dar acesso amplo ao filesystem
- Usar token com escopo exagerado
- Deixar MCP sem descrição no AGENTS.md/CLAUDE.md

Stack padrão:
- Filesystem limitado ao projeto
- Playwright quando houver UI
- GitHub quando houver repo remoto/PR (se permitido pela GITHUB_POLICY)
- Docs/context tool quando houver dependência incerta

### MCPs Registrados e Autorizados

- `chrome-devtools-plugin` / `chrome_devtools`: Permite rodar e avaliar scripts em sessões do Chrome de forma restrita (essencial para debugar/testar o frontend e UI local do SuperEzio).

