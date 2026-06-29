# SuperEzio Agent Operating System

## Diretórios

```text
.claude/
  agents/           # Definições de agentes versionados
    deprecated/     # Agentes aposentados (não deletar)
  commands/         # Comandos reutilizáveis (/swarm, /save, /agent-lab)
  skills/           # F51 skills (inventário, contratos, runtime, etc.)
.agent_bus/
  runtime/          # Memória volátil de execução (gitignored)
```

## Ciclo de vida do agente

```
candidate → active → elite
                ↓
           deprecated
```

## Como criar um agente

1. Criar `.claude/agents/nome-do-agente.md`
2. Seguir template (name, description, tools, missão, regras, nunca, retorne)
3. Testar com tarefa pequena
4. Se passar → promover para active
5. Registrar no AGENTS.md

## Como matar um agente

1. agent-explorer detecta agente fraco (score < 10)
2. Criar candidato melhor
3. Rodar benchmark lado a lado
4. Se candidato vencer → promover, mover antigo para deprecated/
5. Savekeeper registra a troca

## Comandos disponíveis

| Comando | Descrição |
|---------|-----------|
| `/swarm <objetivo>` | Dispara exército completo de 10 agentes |
| `/save` | Salva documentação + checkpoint + commit |
| `/agent-lab` | Testa e melhora agentes |

## Memória volátil (`.agent_bus/runtime/`)

- Ignorada pelo git
- Relatórios temporários de execução
- Limpa automaticamente a cada novo swarm
- NUNCA colocar segredos, tokens ou dados sensíveis
