---
name: f51-runtime
description: "Use quando validar boot, health checks, variáveis de ambiente, portas, logs e runbooks operacionais. Triggers: runtime, boot, health check, env, portas, logs, runbook."
compatibility: "SuperEzio bootstrap layer"
allowed-tools: "Read, Terminal, Logs, JSON"
depends-on: [f51-inventory]
related-skills: [f51-tests, f51-contracts]
---

# f51-runtime

## Quando usar

- Falha de inicialização
- Diferença entre ambiente local e esperado
- Antes de declarar sistema pronto para execução
- Quando o runbook operacional estiver incompleto ou desatualizado

## Nunca fazer

- Corrigir feature nesta etapa
- Instalar dependência sem autorização
- Ocultar falha de boot com workaround silencioso

## Workflow

1. Confirmar comando principal, alternativo, portas, envs e health checks esperados.
2. Reproduzir o estado de runtime real: start, health, logs e erro observável.
3. Diferenciar erro de configuração, erro de ambiente e erro de produto.
4. Atualizar `docs/runbooks/` com start, diagnóstico rápido, recovery e escalonamento.
5. Registrar evidência e atualizar `.f51/checkpoints/latest.json`.

## Portões de decisão

- Se o sistema não iniciar, documentar primeiro; corrigir só com gate apropriado.
- Se faltar variável ou porta documentada, registrar risco operacional.

## Entregáveis mínimos

- Matriz de runtime (comando, env, portas, health)
- Evidência de execução ou erro reproduzível
- Atualização de runbook em `docs/runbooks/`
- Checkpoint atualizado em `.f51/checkpoints/latest.json`

## Regras

- Não corrigir feature nesta fase.
- Primeiro reproduzir, depois diagnosticar.
- Toda afirmação de runtime deve vir com evidência observável.
