---
name: f51-runtime
description: "Valida boot, health checks, variáveis de ambiente e runbooks operacionais."
compatibility: "SuperEzio v3+"
allowed-tools: "Read, Terminal, Env, Logs"
related-skills: [f51-inventory, f51-tests, f51-audit]
---

# f51-runtime

## Quando usar
- Falha de inicialização
- Diferença entre ambiente local e esperado
- Antes de declarar sistema pronto para execução

## Entregáveis mínimos
- Matriz de runtime (comando, env, portas, health)
- Evidência de execução/erro reproduzível
- Atualização de runbook em `docs/runbooks/`
- Checkpoint atualizado em `.f51/checkpoints/latest.json`

## Regras
- Não corrigir feature nesta fase.
- Primeiro reproduzir, depois diagnosticar.
