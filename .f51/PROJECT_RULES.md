# F51 Project Rules

## REGRA CRITICA: GITHUB BLOQUEADO

Fonte mandataria: `.f51/GITHUB_POLICY.json`

Este projeto esta em modo **DISK ONLY**.

Regra clara:
- NUNCA usar GitHub neste projeto.
- NUNCA executar `git push`, `git pull`, `git fetch` ou `gh`.
- NUNCA usar GitHub Actions, pull requests, GitHub API, conector GitHub ou MCP GitHub.
- Commits locais sao permitidos quando Marco pedir para salvar, mas sem push.
- Se uma tarefa exigir GitHub, parar e reportar bloqueio.

## Objetivo operacional

Este projeto deve ser executado com trilhos de entrega, risco e checkpoint.

## Regras obrigatórias

1. Sem feature antes de inventário, contratos, runtime e testes.
2. Toda etapa deve fechar com update em `.f51/checkpoints/latest.json`.
3. Sem mudanças silenciosas de contrato público.
4. Sem refatoração ampla sem plano de rollback.
5. Sem decisões de escopo fora do `MONEY_GATE`.

## Guardrails

- Não alterar código de produto durante bootstrap operacional.
- Não apagar, mover, renomear arquivos sem gate explícito.
- Não instalar dependências sem autorização.

## Entregáveis mínimos por tarefa

- Escopo
- Evidência
- Riscos
- Próximo passo
- Checkpoint atualizado
