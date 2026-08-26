name: f51-inventory
description: "Use quando precisar mapear estrutura do repo, entrypoints, comandos reais, dependências e baseline operacional antes de qualquer implementação. Triggers: inventário, inventory, map repo, entrypoints, baseline, estado atual."
compatibility: "SuperEzio bootstrap layer"
allowed-tools: "Read, Grep, Glob, LS, Terminal (read-only), JSON"
depends-on: []
related-skills: [f51-contracts, f51-runtime, f51-tests, f51-money-gate]
---

# f51-inventory

## Resultado esperado

Produzir um inventário factual do estado atual do projeto sem tocar no código de produto.

## Quando usar

- Início de tarefa nova
- Checkpoint ausente, antigo ou inconsistente
- Antes de qualquer mudança estrutural ou decisão de execução
- Quando o próximo agente não conhece o baseline do repositório

## Nunca fazer

- Implementar feature
- Corrigir bug de produto nesta etapa
- Alterar `apps/`, `src/`, `packages/`, `core/` ou `pipelines/`
- Inventar comandos, variáveis de ambiente ou entrypoints

## Workflow

1. Ler `AGENTS.md`, `AGENTS.md`, `.f51/checkpoints/latest.json`, `.f51/TASK_BOARD.md` e `.f51/RISK_REGISTER.md`.
2. Mapear entrypoints, comandos de runtime, comandos de teste, arquivos de configuração e superfícies frágeis.
3. Registrar apenas fatos observáveis: caminhos, comandos válidos, dependências, portas, envs esperadas e artefatos operacionais.
4. Materializar ou atualizar o inventário com base em `.f51/INVENTORY_TEMPLATE.json`.
5. Atualizar risco inicial e checkpoint com evidência do que foi observado.

## Portões de decisão

- Se o comando principal não puder ser verificado, registrar risco ou bloqueio.
- Se a tarefa pedir feature antes do baseline, bloquear e redirecionar para inventário.

## Entregáveis mínimos

- Inventário atualizado a partir de `.f51/INVENTORY_TEMPLATE.json`
- Lista de entrypoints, comandos válidos e caminhos críticos
- Riscos iniciais documentados em `.f51/RISK_REGISTER.md`
- Checkpoint atualizado em `.f51/checkpoints/latest.json`

## Regras

- Não implementar feature.
- Não alterar código de produto.
- Priorizar fatos observáveis, comandos executáveis e trilha auditável.
