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

## Política de MCPs

MCP permitido somente se cumprir pelo menos uma função:
1. Reduzir erro operacional
2. Testar produto real
3. Auditar entrega
4. Acessar documentação necessária
5. Preparar venda/demo

**Proibido:**
- Instalar MCP por curiosidade
- Dar acesso amplo ao filesystem
- Usar token com escopo exagerado
- Deixar MCP sem descrição no AGENTS.md/CLAUDE.md

**Stack padrão:**
- Filesystem limitado ao projeto
- Playwright SEMPRE — obrigatório em conjunto com qualquer teste. Toda execução de pytest deve
  ser acompanhada de browser smoke test (scripts/browser_smoke.py) para validar UI real.
  O servidor deve estar live. Se o servidor não estiver reachable, o smoke é skipped com warning visível.
- GitHub quando houver repo remoto/PR (BLOQUEADO neste projeto — modo DISK ONLY)
- Docs/context tool quando houver dependência incerta

## Guardrails

- Não alterar código de produto durante bootstrap operacional.
- Durante bootstrap operacional, não alterar `apps/`, `src/`, `packages/`, `core/` ou `pipelines/`.
- Não apagar, mover, renomear arquivos sem gate explícito.
- Não instalar dependências sem autorização.

## Entregáveis mínimos por tarefa

- Escopo
- Evidência
- Riscos
- Próximo passo
- Checkpoint atualizado
